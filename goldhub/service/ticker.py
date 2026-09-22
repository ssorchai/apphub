"""ticker — flow ที่เข้ามาราย strike ทุก 5 นาที (เขียนใหม่จาก cme_ticker.py.old, เฟส 3)

กลไกเดิมทั้งหมดอยู่ใน docs/INTRADAY-TICKER-EXPLAINED.md (diff ยอดสะสม / FIFO ตามจำนวน /
Most Active แบบ rate / delta แช่ ณ ตอน log) ที่ต่างจากของเดิม:

  - **แหล่ง = snapshot Barchart ที่ cme_fetcher ดึงอยู่แล้วในรอบเดียวกัน** ส่งต่อกันใน
    หน่วยความจำ = 0 request เพิ่ม (ของเดิมยิง QuikStrike เอง 2-3 ครั้งทุก 5 นาที)
  - Barchart ให้ทั้ง chain ไม่ใช่ "หน้าต่าง" รอบราคาแบบ QuikStrike -> strike ที่ไม่อยู่ใน
    id_rows = ยังไม่มีใครเทรดใน session นี้ = 0 จริง กับดักข้อ 1 ของเดิม (strike เพิ่งโผล่)
    จึงนับจาก 0 ได้ ยกเว้นรอบแรกหลังล้าง state ที่ยังไม่มี baseline เลย
  - **กับดักข้อ 3 (ใหม่): ช่องว่างระหว่างรอบนานเกิน** เครื่องหลับ/ปิดไปหลายชั่วโมง ยอดทั้งช่วง
    จะถูกนับเป็น event ก้อนเดียวที่ไม่เคยเกิด -> ตั้ง baseline ใหม่เฉยๆ
  - Barchart delayed 10-15 นาที: เวลาใน ticker = เวลาที่เราเห็น ไม่ใช่เวลาที่เทรดจริง
  - ATM IV คิดจาก mid bid/ask (iv_live_rows) แทน ATMVol ของ QuikStrike
  - state อยู่ใน Store (Application Support) รอด reboot / widget ล้างได้ด้วยการลบไฟล์นั้น
    (อ่านจากไฟล์ทุกรอบ ไม่ถือไว้ในหน่วยความจำ จะได้ลบแล้วมีผลทันทีรอบถัดไป)

เขียน /tmp/cme_ticker.json รูปแบบเดิม {meta, iv_hist, ticker, active} ให้ widget ตัวเดิมใช้ได้
"""
import json
import os
import time
from datetime import datetime

import cme_fetcher as C
import gold_fetcher as gf

OUT = "/tmp/cme_ticker.json"
STATE_NAME = "ticker_state"

IV_WINDOW_MIN = 120         # กราฟ IV มองยาว 2 ชม.
ACTIVE_WINDOW_MIN = 60      # sliding window ของ Most Active เท่านั้น
TICKER_MIN_CONTRACTS = 10   # เกณฑ์ขึ้น ticker (put+call รวมในรอบนั้น)
TICKER_ROWS = 12
TICKER_KEEP = 50            # FIFO ตามจำนวน ไม่ใช่ตามอายุ
ACTIVE_ROWS = 5
MAX_GAP_SEC = 12 * 60       # เกินนี้ = ขาดช่วง (หลับ/ปิด/แหล่งล่ม) ตั้ง baseline ใหม่ ไม่สร้าง event
LIVE_MAX_AGE = 180          # ราคาสดเก่ากว่านี้ไม่ใช้


def _short(sym):
    return "GC" + sym[2] + sym[-1] if sym and len(sym) == 5 else sym


def live_future(und_sym):
    """ราคาสดจาก gold job -- ต้องเป็นสัญญาเดียวกับ underlying ของ series และยังสด
    (FuturePrice ของแหล่ง option ช้ากว่าราคาจริง ใช้คิด delta ตอนใกล้หมดอายุแล้วเพี้ยน)"""
    try:
        with open(gf.JSON_PATH) as f:
            g = json.load(f)
        fut = g.get("future") or {}
        if (fut.get("price") and fut.get("sym") == _short(und_sym)
                and time.time() - g.get("ts", 0) < LIVE_MAX_AGE):
            return float(fut["price"]), "live"
    except Exception:
        pass
    return None, None


def greeks(iv_rows, F, dte, K):
    """(delta ของฝั่งที่ยัง OTM, p_touch ≈ 2 x delta) จาก smile ของ bid/ask
    smile ไม่พอ / ใกล้หมดอายุเกินไป -> (None, None) เหมือนเส้น delta ในกราฟ"""
    g = C.greeks_rows(iv_rows, F, dte, [K])
    if not g:
        return None, None
    call_delta = g[0][1]
    otm = call_delta if K > F else 1.0 - call_delta
    return round(otm, 3), round(min(2.0 * otm, 1.0), 2)


def update(snap, store):
    """เรียกหลัง cme_fetcher.main() ทุกรอบ -- snap คือ dict ที่ main() คืนมา
    คืนข้อความสั้นๆ ไว้ log"""
    ts = snap["ts"]
    series = snap["series"]
    dte = snap["dte"]
    iv_rows = [tuple(r) for r in snap.get("iv_live_rows") or []]
    rows = {int(s): (p, c) for s, p, c in snap["id_rows"]}
    oi_map = {int(s): p + c for s, p, c in snap["oi_rows"]}
    F_live, F_src = live_future(snap.get("und_sym"))
    F = F_live or snap["F"]
    F_src = F_src or "barchart"

    state = store.read_json(STATE_NAME) or {}
    note = ""
    if state.get("series") != series:
        # series roll = ล้างทั้งหมด ห้ามเอา flow คนละ series มาต่อกัน
        note = "series ใหม่ {} (เดิม {}) ล้างประวัติ".format(series, state.get("series"))
        state = {"series": series, "ts": None, "prev": None,
                 "contribs": [], "iv_hist": [], "ticker_log": []}
    prev = state.get("prev")
    contribs = state.get("contribs") or []
    iv_hist = state.get("iv_hist") or []
    ticker_log = state.get("ticker_log") or []

    gap = ts - state["ts"] if state.get("ts") else None
    if prev is not None and gap is not None and gap > MAX_GAP_SEC:
        note = "ขาดช่วง {:.0f} นาที ตั้ง baseline ใหม่ (ไม่นับยอดช่วงที่หายไปเป็น event)".format(gap / 60)
        prev = None

    new_contribs = []
    if prev is not None:
        for k, (p, c) in rows.items():
            base = prev.get(str(k), (0, 0))       # ไม่อยู่ในรอบก่อน = ยังไม่มีเทรด = 0 จริง
            dp, dc = p - base[0], c - base[1]
            if dp < 0 or dc < 0:
                continue                           # ยอดสะสมลด = ข้อมูลรีเซ็ต (session ใหม่) ไม่ใช่เทรด
            tot = dp + dc
            if tot <= 0:
                continue
            d_otm, p_touch = greeks(iv_rows, F, dte, k)
            new_contribs.append({
                "ts": ts, "strike": k, "n": tot, "dp": dp, "dc": dc,
                "d": d_otm, "pt": p_touch, "dist": round(k - F, 1),
                "oi": oi_map.get(k),
                "intra": p + c - tot,              # ยอดที่ strike นี้ "ก่อน" ก้อนนี้เข้า
            })

    contribs = [x for x in contribs + new_contribs if x["ts"] > ts - ACTIVE_WINDOW_MIN * 60]
    ticker_log = (ticker_log + [x for x in new_contribs if x["n"] >= TICKER_MIN_CONTRACTS])[-TICKER_KEEP:]

    iv = C.iv_at(iv_rows, F) if iv_rows and F else None
    iv = round(iv, 2) if iv else None
    iv_chg = snap.get("iv_settle_chg")
    if iv is not None and (not iv_hist or iv_hist[-1]["iv"] != iv or ts - iv_hist[-1]["ts"] >= 240):
        iv_hist.append({"ts": ts, "iv": iv, "chg": iv_chg})
    iv_hist = [x for x in iv_hist if x["ts"] > ts - IV_WINDOW_MIN * 60]

    ticker = sorted(ticker_log, key=lambda x: -x["ts"])[:TICKER_ROWS]

    agg = {}
    for x in contribs:
        a = agg.setdefault(x["strike"], {"sum": 0, "first_ts": x["ts"]})
        a["sum"] += x["n"]
        a["first_ts"] = min(a["first_ts"], x["ts"])
    active = []
    for k, a in agg.items():
        age_min = (ts - a["first_ts"]) / 60.0
        d_otm, p_touch = greeks(iv_rows, F, dte, k)
        active.append({
            "strike": k, "sum": a["sum"], "age": round(age_min),
            # rate ไม่ใช่ sum: 30 ไม้ใน 5 นาทีมีนัยกว่า 30 ไม้ใน 65 นาที (ก้อนเดียวใช้พื้น 5 นาที)
            "rate": round(a["sum"] / max(age_min, 5.0), 1),
            "d": d_otm, "pt": p_touch, "dist": round(k - F, 1), "oi": oi_map.get(k),
        })
    active.sort(key=lambda x: -x["rate"])
    active = active[:ACTIVE_ROWS]

    store.write_json(STATE_NAME, {
        "series": series, "ts": ts,
        "prev": {str(k): [p, c] for k, (p, c) in rows.items()},
        "contribs": contribs, "iv_hist": iv_hist, "ticker_log": ticker_log,
    })
    out = {
        "meta": {
            "series": series, "dte": round(dte, 4) if dte else None,
            "iv": iv, "iv_chg": iv_chg,
            "F": round(F, 2) if F else None, "F_src": F_src, "src_F": snap["F"],
            "src": "barchart", "delay": "10-15m",
            "iv_window_min": IV_WINDOW_MIN, "active_window_min": ACTIVE_WINDOW_MIN,
            "threshold": TICKER_MIN_CONTRACTS,
            "system_time": datetime.fromtimestamp(ts).strftime("%H:%M"), "ts": ts,
            "baseline": prev is None,          # รอบนี้แค่ตั้ง baseline (ยังไม่มี event ให้เทียบ)
        },
        "iv_hist": iv_hist,
        "ticker": ticker,
        "active": active,
    }
    tmp = OUT + ".tmp"
    with open(tmp, "w") as f:
        json.dump(out, f)
    os.replace(tmp, OUT)
    msg = "ticker {} new={} win={} tick={} act={} IV={} F={}({})".format(
        series, len(new_contribs), len(contribs), len(ticker), len(active), iv, F, F_src)
    return (note + " | " + msg) if note else msg
