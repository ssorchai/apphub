"""weatherhub — เรดาร์ฝน + แจ้งเตือนฝนเข้า (ย้ายจาก cron 21 ก.ย. 2026)

แยก service กับ goldhub คนละ process คนละ plist: งานคนละเรื่อง แหล่งข้อมูลคนละเจ้า
พังฝั่งหนึ่งอีกฝั่งต้องไม่สะเทือน (และตอนขึ้น cloud จะแยก container ได้เลย)

เฟสนี้ยัง "เปลี่ยนแค่ตัวขับเคลื่อน": ยังเป็นพิกัดตายตัวของหนองจอก ยังไม่มี API
เรื่องรับ lat/lon จากเครื่องที่เรียก อยู่เฟส 4

`align=True` สำคัญกับงานคู่นี้: rain_nowcast ตัดสินใจเฉพาะ 16:00/16:15/16:30/16:45
(รับความคลาดเคลื่อนได้ 2 นาที) ถ้านับคาบต่อจากรอบที่แล้วแบบธรรมดา เวลาจะเลื่อนสะสม
จนหลุดหน้าต่างไปทั้งวันโดยไม่มีใครรู้ -- align ยึดนาฬิกาจริงเหมือน cron */5
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

import rain_nowcast  # noqa: E402
import weather_fetcher  # noqa: E402
from common.hub import (Health, Job, Scheduler, Store, err, holder_pid,  # noqa: E402
                        log, single_instance)

SERVICE = "weatherhub"
RADAR_INTERVAL = 300       # เท่าบรรทัด cron เดิม (*/5)
RADAR_TIMEOUT = 60
HOUSEKEEPING_INTERVAL = 24 * 3600
RETENTION_DAYS = 7
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
    Scheduler(health).add(
        Job("radar", job_radar, RADAR_INTERVAL, timeout=RADAR_TIMEOUT, align=True),
        Job("nowcast", job_nowcast, RADAR_INTERVAL, timeout=RADAR_TIMEOUT, align=True),
        Job("housekeeping", job_housekeeping, HOUSEKEEPING_INTERVAL),
    ).run_forever()


if __name__ == "__main__":
    main()
