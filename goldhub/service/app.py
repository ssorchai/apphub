"""goldhub — daemon ตัวเดียวแทน cron (เฟส 1)

เฟสนี้ตั้งใจให้ "พฤติกรรมเหมือนเดิมทุกอย่าง" เปลี่ยนแค่ตัวขับเคลื่อน:
  - งาน cme ยังคาบ 1 ชั่วโมง นาทีที่ :07 เท่ากับบรรทัด cron เดิม
  - ยังเขียนไฟล์ /tmp ชุดเดิมครบ (cme_putcall.json / clip / chart / curve / eventvol)
  - HTTP API ที่ 127.0.0.1:8787 (เฟส 2, 22 ก.ย.) อ่านจากไฟล์อย่างเดียว ดู api.py
  - ยังไม่เปลี่ยนคาบ cme เป็น 5 นาที (เฟส 3)
  - งาน gold คาบ 5 วินาทีต่อเนื่อง (21 ก.ย.) — เดิม cron ปลุกทุก 5 นาทีให้รันรอบละ 290 วิ
    แล้วเงียบไป ~10 วินาทีต้นรอบ ตอนนี้ไม่ขาดช่วงแล้ว ดูรายละเอียดใน gold_job.py

รัน:  python3 app.py            (foreground ไว้ทดสอบ)
      launchctl load ...plist   (ของจริง ดู deploy/)
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)                                   # cme_fetcher.py อยู่โฟลเดอร์เดียวกัน
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))  # apphub/ -> common.hub

import api  # noqa: E402
import cme_fetcher  # noqa: E402
import gold_job  # noqa: E402
from common.hub import (Health, Job, Scheduler, Store, err, holder_pid,  # noqa: E402
                        log, single_instance)

SERVICE = "goldhub"
CME_INTERVAL = 3600
CME_AT_MINUTE = 7          # ยึดนาทีเดิมของ cron ไว้ เทียบ log ยุคเก่า-ใหม่ได้ตรงๆ
CME_TIMEOUT = 120          # แค่เตือนใน log — เส้นตายจริงคือ MAX_RUNTIME ใน cme_fetcher
HOUSEKEEPING_INTERVAL = 24 * 3600
RETENTION_DAYS = 7
RETENTION_CAP_MB = 200

store = Store(SERVICE)
health = Health(store)


def job_cme():
    """รอบเดียวกับที่ cron เคยรัน — เขียนไฟล์ /tmp ชุดเดิมทั้งหมด
    ข้อผิดพลาดฝั่งแหล่งข้อมูล (SourceDown/timeout) ไม่ใช่บั๊กของเรา: log แล้วปล่อยให้รอบหน้าลองใหม่
    cme_fetcher จะไม่เขียนทับไฟล์เดิมเมื่อพัง widget จึงขึ้น STALE เองตามกลไกที่มีอยู่"""
    try:
        cme_fetcher.main()
    except cme_fetcher.SourceDown as e:
        err("cme: แหล่งข้อมูลล่ม ({}) — ข้ามรอบนี้", str(e)[:120])
        return
    snap = store.read_json("last_cme", {})
    try:
        with open(cme_fetcher.JSON_OUT) as f:
            data = json.load(f)
        summary = {
            "ts": data.get("ts"), "series": data.get("series"), "F": data.get("F"),
            "dte": data.get("dte"), "iv_event": data.get("iv_event"),
            "intraday": data.get("intraday", {}).get("put"),
            "smile_src": data.get("smile_src"),
        }
        if summary != snap:
            store.write_json("last_cme", summary)
            store.append_history("cme", summary)
    except Exception as e:                       # สรุปพังไม่ใช่เรื่องใหญ่ ข้อมูลหลักเขียนไปแล้ว
        err("cme: เก็บสรุปลง store ไม่ได้ ({})", type(e).__name__)


def job_housekeeping():
    res = store.retention(days=RETENTION_DAYS, cap_mb=RETENTION_CAP_MB)
    log("housekeeping: ลบ {} ไฟล์ เหลือ {:.1f} MB", res["removed"], res["bytes_left"] / 1048576)


def main():
    # กันรันซ้อน: ถ้ามีตัวอื่นถืออยู่ให้ออกเงียบๆ (launchd จะไม่ restart รัวเพราะ exit 0)
    lockfile = store.path("state", "goldhub.lock")
    lock = single_instance(lockfile)
    if lock is None:
        err("มี goldhub ตัวอื่นรันอยู่แล้ว (pid {}) — ออก", holder_pid(lockfile))
        sys.exit(0)
    log("goldhub start (pid {}) data={}", os.getpid(), store.root)
    api.build(health).start()
    gold = gold_job.GoldPoller()
    Scheduler(health).add(
        Job("cme", job_cme, CME_INTERVAL, timeout=CME_TIMEOUT, at_minute=CME_AT_MINUTE),
        # ราคาสด: คาบสั้นมาก งานนี้พังบ่อยได้ (investing/Cloudflare) scheduler จะ log
        # ซ้ำเฉพาะตอนข้อความ error เปลี่ยน ไม่งั้นท่วม log ทุก 5 วินาที
        Job("gold", gold.tick, gold_job.POLL, timeout=gold_job.TIMEOUT),
        # ล้างของเก่า: รันตอน start แล้ววันละครั้ง (ไฟล์เล็ก ไม่ต้องเลือกเวลา)
        Job("housekeeping", job_housekeeping, HOUSEKEEPING_INTERVAL),
    ).run_forever()


if __name__ == "__main__":
    main()
