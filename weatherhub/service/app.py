"""weatherhub — เรดาร์ฝน + แจ้งเตือนฝนเข้า (ย้ายจาก cron 21 ก.ย. 2026)

แยก service กับ goldhub คนละ process คนละ plist: งานคนละเรื่อง แหล่งข้อมูลคนละเจ้า
พังฝั่งหนึ่งอีกฝั่งต้องไม่สะเทือน (และตอนขึ้น cloud จะแยก container ได้เลย)

API อ่านอย่างเดียวที่พอร์ต 8788 (เฟส 4, 25 ก.ย.) รับ lat/lon จากเครื่องที่เรียก ดู api.py

`align=True` สำคัญกับงานคู่นี้: rain_nowcast ตัดสินใจเฉพาะ 16:00/16:15/16:30/16:45
(รับความคลาดเคลื่อนได้ 2 นาที) ถ้านับคาบต่อจากรอบที่แล้วแบบธรรมดา เวลาจะเลื่อนสะสม
จนหลุดหน้าต่างไปทั้งวันโดยไม่มีใครรู้ -- align ยึดนาฬิกาจริงเหมือน cron */5
"""
import json
import threading
import time
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

import api  # noqa: E402
import frames  # noqa: E402
import point_nowcast  # noqa: E402
import verify  # noqa: E402
import rain_nowcast  # noqa: E402
import weather_fetcher  # noqa: E402
from common.hub import (Health, Job, Scheduler, Store, err, holder_pid,  # noqa: E402
                        log, single_instance)

SERVICE = "weatherhub"
RADAR_INTERVAL = 300       # เท่าบรรทัด cron เดิม (*/5)
# ดึงภาพที่ :02:30 :07:30 … ไม่ใช่ :00 :05 -- ภาพของ กทม. ออกช้ากว่าเวลาในภาพ 5-7 นาที
# ดึงตรง :00 พอดีอยู่บนขอบ: 25 ก.ย. 16:00:00 ภาพ 15:55 ยังไม่ออก พอ 16:05 ภาพ 16:00 ทับไปแล้ว
# (เห็นในภาพ 15:50 แล้วโดดไป 16:00) -- จำนวน request เท่าเดิม แค่ย้ายจังหวะ
RADAR_OFFSET = 150
RADAR_TIMEOUT = 60
HOUSEKEEPING_INTERVAL = 24 * 3600
RETENTION_DAYS = 30        # history/forecast + observed ใช้วัดความแม่น (~0.5 MB/วัน)
RETENTION_CAP_MB = 200

store = Store(SERVICE)
health = Health(store)


def job_radar():
    """ดึงภาพเรดาร์รอบเดียว -- พังก็ไม่แตะไฟล์เดิม widget ยังโชว์ภาพล่าสุดที่ดีอยู่"""
    weather_fetcher.main()
    try:
        with open(weather_fetcher.JSON_PATH) as f:
            m = json.load(f)
        summary = {"ts": m.get("ts"), "via": m.get("via"),
                   "kb": len(m.get("img_base64", "")) * 3 // 4096}
        if summary != store.read_json("last_radar", {}):
            store.write_json("last_radar", summary)
            store.append_history("radar", summary)
    except Exception as e:
        err("radar: เก็บสรุปลง store ไม่ได้ ({})", type(e).__name__)
    try:
        fresh, obs_ts, src = frames.save(store.path("frames"), m)   # ให้หน้าเว็บเล่นเป็นภาพเคลื่อนไหว
        if fresh:
            log("radar frame: ภาพเวลา {} ({}) ดึงช้ากว่า {:.1f} นาที", time.strftime("%H:%M", time.localtime(obs_ts)),
                src, (m.get("ts", obs_ts) - obs_ts) / 60)
    except Exception as e:
        err("radar: เก็บเฟรมไม่ได้ ({})", type(e).__name__)
        return
    # nowcast รายจุด: คิดใหม่เฉพาะตอนได้เฟรมใหม่ (หรือยังไม่มี snapshot เช่นเพิ่ง reboot)
    if fresh or not os.path.exists(point_nowcast.SNAP_PATH):
        try:
            res = point_nowcast.update(store.path("frames"))
            if res and fresh:
                # เก็บผลทาย + ฝนจริงของรอบนี้ไว้วัดความแม่น (verify.py) -- ไม่ขวางงานหลักถ้าพัง
                try:
                    with open(point_nowcast.SNAP_PATH) as f:
                        verify.record(store, point_nowcast.load_snapshot(f.read()))
                except Exception as e:
                    err("verify: บันทึกไม่ได้ {}: {}", type(e).__name__, str(e)[:160])
            if res:
                log("point nowcast: rain {} heavy {} px · motion {}", res["rain_px"], res["heavy_px"],
                    "{} {} km/h".format(res["from_dir"], res["speed_kmh"]) if res.get("from_dir") else "-")
        except Exception as e:
            err("point nowcast พัง {}: {}", type(e).__name__, str(e)[:160])


def job_nowcast():
    """แยกงานกับ radar ตั้งใจ: ของเดิมก็เรียกแยกจากกันเพื่อให้ฝั่งหนึ่งพังแล้วอีกฝั่งยังทำงาน
    ตัว run_check เช็คเวลาเองและจำว่าวันนี้เตือนไปแล้ว นอกหน้าต่างเวลาจะ return ทันที"""
    rain_nowcast.run_check()


def job_housekeeping():
    res = store.retention(days=RETENTION_DAYS, cap_mb=RETENTION_CAP_MB)
    log("housekeeping: ลบ {} ไฟล์ เหลือ {:.1f} MB", res["removed"], res["bytes_left"] / 1048576)


def main():
    lockfile = store.path("state", "weatherhub.lock")
    lock = single_instance(lockfile)
    if lock is None:
        err("มี weatherhub ตัวอื่นรันอยู่แล้ว (pid {}) — ออก", holder_pid(lockfile))
        sys.exit(0)
    log("weatherhub start (pid {}) data={}", os.getpid(), store.root)
    api.build(health).start()
    # compile ตัวอ่านเวลาในภาพ (Swift + Vision) ครั้งแรกใช้ ~40 วิ -- ทำเบื้องหลัง ระหว่างนั้นใช้เวลาดึงแทน
    threading.Thread(target=lambda: log("ocr: {}", frames.ensure_ocr(store.path("bin")) or "ใช้ไม่ได้ -- ใช้เวลาดึงแทน"),
                     name="ocr-build", daemon=True).start()
    Scheduler(health).add(
        Job("radar", job_radar, RADAR_INTERVAL, timeout=RADAR_TIMEOUT, align=True, offset=RADAR_OFFSET),
        Job("nowcast", job_nowcast, RADAR_INTERVAL, timeout=RADAR_TIMEOUT, align=True),
        Job("housekeeping", job_housekeeping, HOUSEKEEPING_INTERVAL),
    ).run_forever()


if __name__ == "__main__":
    main()
