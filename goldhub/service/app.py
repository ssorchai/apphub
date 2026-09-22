"""goldhub — daemon ตัวเดียวแทน cron (เฟส 1)

เฟสนี้ตั้งใจให้ "พฤติกรรมเหมือนเดิมทุกอย่าง" เปลี่ยนแค่ตัวขับเคลื่อน:
  - งาน cme ยังคาบ 1 ชั่วโมง นาทีที่ :07 เท่ากับบรรทัด cron เดิม
  - ยังเขียนไฟล์ /tmp ชุดเดิมครบ (cme_putcall.json / clip / chart / curve / eventvol)
  - HTTP API ที่ 127.0.0.1:8787 (เฟส 2, 22 ก.ย.) อ่านจากไฟล์อย่างเดียว ดู api.py
  - cme ทุก 5 นาทีที่ :02 :07 :12 … (เฟส 3, 22 ก.ย.) แต่ **แตะ QuikStrike แค่รอบ :07**
    รอบอื่นเป็น Barchart ล้วน (2 request) + ticker ต่อท้ายในรอบเดียวกัน ดู job_cme()
  - งาน gold คาบ 5 วินาทีต่อเนื่อง (21 ก.ย.) — เดิม cron ปลุกทุก 5 นาทีให้รันรอบละ 290 วิ
    แล้วเงียบไป ~10 วินาทีต้นรอบ ตอนนี้ไม่ขาดช่วงแล้ว ดูรายละเอียดใน gold_job.py

รัน:  python3 app.py            (foreground ไว้ทดสอบ)
      launchctl load ...plist   (ของจริง ดู deploy/)
"""
import json
import os
import sys
import time
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)                                   # cme_fetcher.py อยู่โฟลเดอร์เดียวกัน
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))  # apphub/ -> common.hub

import api  # noqa: E402
import cme_fetcher  # noqa: E402
import gold_job  # noqa: E402
import ticker  # noqa: E402
from common.hub import (Health, Job, Scheduler, Store, err, holder_pid,  # noqa: E402
                        log, single_instance)

SERVICE = "goldhub"
CME_INTERVAL = 300         # snapshot Barchart ทุก 5 นาที
CME_OFFSET = 120           # กริด :02 :07 :12 … ให้รอบ :07 ตรงกับนาทีเดิมของ cron
CME_AT_MINUTE = 7          # รอบที่แตะ QuikStrike (ยึดนาทีเดิม เทียบ log ยุคเก่า-ใหม่ได้ตรงๆ)
QS_MIN_GAP = 20 * 60       # รอบ :07 จะยิง QuikStrike ก็ต่อเมื่อห่างจากครั้งก่อนอย่างน้อยเท่านี้
QS_MAX_GAP = 65 * 60       # ห่างเกินนี้ (หลับข้าม :07) = ยิงรอบนี้เลยไม่ต้องรอ :07
CME_TIMEOUT = 120          # แค่เตือนใน log — เส้นตายจริงคือ MAX_RUNTIME ใน cme_fetcher
HOUSEKEEPING_INTERVAL = 24 * 3600
RETENTION_DAYS = 7
RETENTION_CAP_MB = 200

store = Store(SERVICE)
health = Health(store)


_qs = {"ts": 0.0, "series": None}     # QuikStrike ครั้งล่าสุดที่ daemon สั่ง
_ticker_err = {"msg": None}


def want_qs(now):
    """รอบนี้แตะ QuikStrike ไหม -- กติกาคือ "ชั่วโมงละครั้งที่ :07" แบบเดิม
    ข้อยกเว้น: รอบแรกหลัง start / หลับข้าม :07 ไปแล้ว (ห่างเกิน 65 นาที ยิงเลย)
    และกันยิงถี่: รอบ :07 ที่เพิ่งยิงไปไม่ถึง 20 นาที (เพิ่ง restart) ข้ามไปก่อน
    -> ห่างกันอย่างน้อย 20 นาทีเสมอ request ไป CME ไม่มีทางมากกว่าเดิม"""
    gap = now - _qs["ts"]
    if _qs["ts"] == 0 or gap > QS_MAX_GAP:
        return True
    return datetime.fromtimestamp(now).minute == CME_AT_MINUTE and gap >= QS_MIN_GAP


def _fetch(use_qs):
    if use_qs:
        _qs["ts"] = time.time()       # นับเป็น "ยิงแล้ว" แม้พัง/โดนเบรก -- ไม่วนยิงซ้ำทุก 5 นาที
    # baseline ของ "Δ CHANGES SINCE" ขยับเฉพาะรอบรายชั่วโมง ให้ยังเทียบกับชั่วโมงก่อนเหมือนเดิม
    res = cme_fetcher.main(use_qs=use_qs, baseline=use_qs)
    if use_qs and res:
        _qs["series"] = res["series"]
    return res


def job_cme():
    """snapshot ทุก 5 นาที (QuikStrike เฉพาะรอบ :07) แล้วต่อด้วย ticker
    ข้อผิดพลาดฝั่งแหล่งข้อมูล (SourceDown/timeout) ไม่ใช่บั๊กของเรา: log แล้วปล่อยให้รอบหน้าลองใหม่
    cme_fetcher จะไม่เขียนทับไฟล์เดิมเมื่อพัง widget จึงขึ้น STALE เองตามกลไกที่มีอยู่"""
    try:
        res = _fetch(want_qs(time.time()))
        if res and res["series"] != _qs["series"]:
            # series roll ระหว่างรอบ Barchart-only: cache ของ QuikStrike เป็นของ series เก่า
            # ใช้ไม่ได้ -> ดึงของ series ใหม่ทันที (วันละครั้ง) ไม่รอ :07
            log("cme: series เปลี่ยนเป็น {} — ดึง QuikStrike ของ series ใหม่เลย", res["series"])
            res = _fetch(True)
    except cme_fetcher.SourceDown as e:
        err("cme: แหล่งข้อมูลล่ม ({}) — ข้ามรอบนี้", str(e)[:120])
        return
    if res:
        try:
            msg = ticker.update(res, store)
            if " | " in msg:                      # มีเหตุการณ์พิเศษ (ล้าง/ขาดช่วง) ค่อย log
                log("{}", msg)
            _ticker_err["msg"] = None
        except Exception as e:                    # ticker พังต้องไม่ลาก snapshot ล่ม
            m = "{}: {}".format(type(e).__name__, str(e)[:160])
            if m != _ticker_err["msg"]:
                err("ticker พัง {}", m)
                _ticker_err["msg"] = m
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
        Job("cme", job_cme, CME_INTERVAL, timeout=CME_TIMEOUT, align=True, offset=CME_OFFSET),
        # ราคาสด: คาบสั้นมาก งานนี้พังบ่อยได้ (investing/Cloudflare) scheduler จะ log
        # ซ้ำเฉพาะตอนข้อความ error เปลี่ยน ไม่งั้นท่วม log ทุก 5 วินาที
        Job("gold", gold.tick, gold_job.POLL, timeout=gold_job.TIMEOUT),
        # ล้างของเก่า: รันตอน start แล้ววันละครั้ง (ไฟล์เล็ก ไม่ต้องเลือกเวลา)
        Job("housekeeping", job_housekeeping, HOUSEKEEPING_INTERVAL),
    ).run_forever()


if __name__ == "__main__":
    main()
