"""gold — poller ราคาสด (เดิมเป็น cron ทุก 5 นาที รันรอบละ 290 วินาทีแล้วจบ)

อยู่ใน daemon แล้วไม่ต้องจบรอบให้ cron ปลุกใหม่: scheduler เรียก tick() ทุก POLL_SECONDS
ต่อเนื่องไปเรื่อยๆ ผลพลอยได้คือ gold_live.js ไม่ขาดช่วงตอนต้นรอบ cron อีก

ของที่เดิมทำ "ครั้งเดียวต่อรอบ cron" เพราะ process เริ่มใหม่ทุก 5 นาที ต้องย้ายมาทำเองตามเวลา
(REFRESH) ไม่งั้นค้างข้ามวัน:
  - open ของวันจาก Yahoo — เปลี่ยนตอน session ใหม่เปิด 05:00 ไทย
  - เช็คว่าถึงรอบอัปเดตสัญญาอ้างอิง/spread รายวันหรือยัง (ตัว due() ใน gold_fetcher)

anchor (สัญญาที่ 0DTE อ้างอิง เช่น GCV6) เลิกยิง QuikStrike เอง — ใช้ `und_sym` ที่
cme_fetcher resolve ไว้แล้ว ถ้าไม่มีไฟล์ค่อยคำนวณเองด้วย underlying_for() ซึ่งเป็นการ
คิดจากปฏิทินล้วนๆ ไม่แตะเน็ต => gold ไม่ต่อตรงไป CME อีกต่อไป เหลือทางเดียวคือผ่าน
cme_fetcher ที่มีตัวเบรกของมันเอง
"""
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

import cme_fetcher                      # noqa: E402
import gold_fetcher as gf               # noqa: E402
from common.hub import err, log         # noqa: E402

REFRESH = 300          # วินาที — เท่ารอบ cron เดิม
POLL = gf.POLL_SECONDS  # 5 วินาที — คาบเดิมของ tick
TIMEOUT = 25           # tick รอ investing ฝั่งละ 20 วิ (ขนานกัน) แค่เตือนใน log


def _short(sym):
    """'GCV26' (รูปแบบของ cme_fetcher) -> 'GCV6' (รูปแบบที่ gold_fetcher/widget ใช้)"""
    if sym and len(sym) == 5 and sym[:2] == "GC":
        return "GC" + sym[2] + sym[-1]
    return sym


def anchor_sym():
    """สัญญาที่ 0DTE อ้างอิง โดยไม่ยิงเน็ต: เอาค่าที่ cme_fetcher หาไว้แล้วเป็นหลัก
    ไม่มีไฟล์ (เช่น หลัง reboot ก่อนรอบ cme แรก) ค่อยคำนวณจากปฏิทินเอง"""
    try:
        with open(cme_fetcher.JSON_OUT) as f:
            und = json.load(f).get("und_sym")
        if und:
            return und
    except Exception:
        pass
    return cme_fetcher.underlying_for(date.today())


class GoldPoller:
    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=2)
        self.state = gf.load_state()       # cache รายวัน: สัญญาอ้างอิง + spread ระหว่างสัญญา
        self.anchor = None
        self.yahoo_ref = {"open": None, "last": None, "month": None}
        self.roll_state = {}
        self.refreshed = 0.0

    def refresh(self):
        prev = (self.anchor or {}).get("sym")
        sym = _short(anchor_sym())
        if sym:
            # ปั๊ม anchor_ts ให้ ensure_anchor เห็นว่า "เพิ่งอัปเดต" จะได้ไม่ยิง QuikStrike เอง
            self.state["sym"] = sym
            self.state["anchor_ts"] = time.time()
        self.anchor = gf.ensure_anchor(self.state)
        cur = (self.anchor or {}).get("sym")
        if cur != prev:
            log("gold: สัญญาอ้างอิง {} -> {}", prev, cur)
            # spread ที่คิดไว้เป็นของสัญญาคู่เดิม ใช้กับสัญญาใหม่ไม่ได้ ต้องคิดใหม่
            self.roll_state = {}

        try:
            ref = gf.fetch_yahoo_futures(self.anchor["month"] if self.anchor else None)
            if ref.get("open") is None and self.anchor:
                log("gold: Yahoo ยังไม่มี open ของ {} (ยังไม่มีเทรดแรก?) — ใช้ front แทน",
                    self.anchor["month"])
                ref = gf.fetch_yahoo_futures()
            self.yahoo_ref = ref
        except Exception as e:
            err("gold: ดึง open จาก Yahoo ไม่ได้ ({}) — ใช้ open ของ investing แทน",
                "{}: {}".format(type(e).__name__, str(e)[:80]))
            self.yahoo_ref = {"open": None, "last": None, "month": None}
        self.refreshed = time.time()

    def tick(self):
        """หนึ่งรอบ = เขียน /tmp/gold_data.json + /tmp/gold_live.js
        ฝั่งไหนดึงไม่ได้ gf.tick จะ raise เอง -> scheduler บันทึกเป็น fail (log ไม่ซ้ำ)"""
        if time.time() - self.refreshed >= REFRESH:
            self.refresh()
        gf.tick(self.executor, self.yahoo_ref, self.state, self.anchor, self.roll_state)
