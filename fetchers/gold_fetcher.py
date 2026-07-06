import json
import os
import sys
import time
import warnings
warnings.filterwarnings("ignore")  # กัน NotOpenSSLWarning ของ urllib3 เปื้อน log
import requests
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

# ราคา realtime (last/change) จาก investing.com mobile app API — แหล่งเดียวกับเว็บที่เคย scrape
# ราคาเปิดของ Futures ใช้ Yahoo Finance (GC=F) เพราะแม่นกว่า
# ไม่ใช้ Playwright/Chromium — HTTP ล้วนๆ
JSON_PATH = "/tmp/gold_data.json"

INVESTING_URL = "https://aappapi.investing.com/get_screen.php?screen_ID=22&pair_ID={}&lang_ID=1"
PAIR_FUTURES = 8830  # Gold Futures (GC)
PAIR_SPOT = 68       # XAU/USD
YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/GC=F?interval=1d&range=1d"

RUN_SECONDS = 290   # ทำงานเกือบเต็มรอบ cron 5 นาที
POLL_SECONDS = 5

# Theory Diff (cost of carry): F = S * (1 + net_rate * t)
# net carry = ดอกเบี้ย USD - gold lease rate — ปรับค่านี้ให้ตรงกับ basis curve จริงได้
CARRY_RATE = 0.02
THEORY_STEP = 2.5   # ปัดเป็นขั้นละ 2.5 ตาม convention (2.5, 5, 7.5, 10, 12.5, ...)

UA_HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
INVESTING_HEADERS = dict(UA_HEADERS, **{"x-meta-ver": "14"})


def get_market_zone():
    hour = datetime.now().hour
    if 7 <= hour < 14: return "ASIA Session"
    if 14 <= hour < 19: return "LONDON Session"
    if 19 <= hour < 23: return "GOLDEN TIME (LDN+NY)"
    if 23 <= hour or hour < 5: return "NEW YORK Session"
    return "Quiet Session"


def atomic_write(path, obj):
    temp = path + ".tmp"
    with open(temp, "w") as f:
        json.dump(obj, f)
    os.replace(temp, path)


def to_float(s):
    return float(str(s).replace(",", ""))


def fetch_yahoo_futures(session):
    """ดึงราคาเปิดวัน + Last Price (LP) ของ GC=F จาก Yahoo — เรียกครั้งเดียวต่อรอบ
    open ของ Yahoo แม่นกว่า investing / LP ดีเลย์ ~10 นาที เก็บไว้ cross-check + fallback"""
    r = session.get(YAHOO_URL, headers=UA_HEADERS, timeout=15)
    r.raise_for_status()
    result = r.json()["chart"]["result"][0]
    meta = result["meta"]
    quote = result["indicators"]["quote"][0]
    # range=1d อาจได้หลายแท่งช่วงรอยต่อวันเทรด — เอาแท่งล่าสุด (วันปัจจุบัน) เสมอ
    opens = [v for v in quote.get("open", []) if v is not None]
    last = meta.get("regularMarketPrice")
    return {
        "open": round(opens[-1], 2) if opens else None,
        "last": round(last, 2) if last is not None else None,
    }


def fetch_investing(session, pair_id):
    r = session.get(INVESTING_URL.format(pair_id), headers=INVESTING_HEADERS, timeout=15)
    r.raise_for_status()
    d = r.json()["data"][0]["screen_data"]["pairs_data"][0]
    overview = {row["key"]: row["val"] for row in d.get("overview_table", [])}
    return {
        "last": to_float(d["last"]),
        "change": round(float(d["change_val"]), 2),
        "percent": round(float(d["change_percent_val"]), 2),
        "time": datetime.fromtimestamp(d["last_timestamp"]).strftime("%H:%M:%S"),
        "open": to_float(overview["Open"]) if overview.get("Open") else None,
        "month": overview.get("Month"),  # เช่น "Aug 26" (มีเฉพาะ futures)
        "settlement": overview.get("Settlement Day"),  # เช่น "2026-08-27" (มีเฉพาะ futures)
    }


def theory_diff(fut, spot):
    """basis ตามทฤษฎี = spot * carry * เวลาที่เหลือถึงวัน settlement ปัดเป็นขั้นละ 2.5"""
    if not (fut and spot and fut.get("settlement")):
        return None
    try:
        expiry = datetime.strptime(fut["settlement"], "%Y-%m-%d").date()
        days = (expiry - datetime.now().date()).days
        if days < 0:
            return None
        raw = spot["last"] * CARRY_RATE * days / 365.0
        return {
            "diff": round(round(raw / THEORY_STEP) * THEORY_STEP, 2),
            "raw": round(raw, 2),
            "days": days,
        }
    except Exception:
        return None


def tick(executor, sessions, yahoo_ref):
    # ยิง request ทั้ง 2 ตัวพร้อมกัน (คนละ thread) เพราะ diff ต้องมาจากราคา ณ เวลาเดียวกัน
    job_fut = executor.submit(fetch_investing, sessions[0], PAIR_FUTURES)
    job_spot = executor.submit(fetch_investing, sessions[1], PAIR_SPOT)

    fut = spot = None
    errors = []
    try:
        fut = job_fut.result(timeout=20)
    except Exception as e:
        errors.append("futures {}: {}".format(type(e).__name__, e))
    try:
        spot = job_spot.result(timeout=20)
    except Exception as e:
        errors.append("spot {}: {}".format(type(e).__name__, e))

    # future: open ใช้ Yahoo (แม่นกว่า) / change,percent = เทียบ prev close (จาก investing)
    # เพิ่ม change_open,percent_open = last price เทียบ open ของวัน (เฉพาะ future)
    fut_future = None
    if fut:
        fut_open = yahoo_ref["open"] if yahoo_ref.get("open") is not None else fut["open"]
        change_open = round(fut["last"] - fut_open, 2) if fut_open else None
        percent_open = round(change_open / fut_open * 100, 2) if change_open is not None else None
        fut_future = {
            "name": "Gold Futures ({})".format(fut["month"]) if fut["month"] else "Gold Futures",
            "price": fut["last"],
            "open": fut_open,
            "change": fut["change"],
            "percent": fut["percent"],
            "change_open": change_open,
            "percent_open": percent_open,
            "yahoo_last": yahoo_ref.get("last"),
            "time": fut["time"],
        }

    # ห้ามใช้ค่าเก่า: ฝั่งไหนดึงไม่ได้เขียนเป็น null และ diff เป็น null (widget แสดง N/A)
    output = {
        "future": fut_future,
        "spot": {
            "name": "XAU/USD Spot",
            "price": spot["last"],
            "change": spot["change"],
            "percent": spot["percent"],
            "time": spot["time"],
        } if spot else None,
        "diff": round(fut["last"] - spot["last"], 2) if fut and spot else None,
        "theory": theory_diff(fut, spot),
        "zone": get_market_zone(),
        "system_time": datetime.now().strftime("%H:%M:%S"),
        "ts": int(time.time()),
    }
    atomic_write(JSON_PATH, output)
    if errors:
        raise RuntimeError("; ".join(errors))


def main():
    once = "--once" in sys.argv
    # แยก session คนละ thread (requests.Session ไม่การันตี thread-safe)
    sessions = (requests.Session(), requests.Session())
    executor = ThreadPoolExecutor(max_workers=2)
    print("🚀 gold_fetcher (HTTP mode) started {}".format(datetime.now().strftime("%H:%M:%S")))

    try:
        yahoo_ref = fetch_yahoo_futures(sessions[0])
    except Exception as e:
        print("⚠️ yahoo fetch failed, fallback to investing open: {}".format(e))
        yahoo_ref = {"open": None, "last": None}

    start = time.time()
    last_error = None
    while True:
        try:
            tick(executor, sessions, yahoo_ref)
            last_error = None
        except Exception as e:
            msg = "{}: {}".format(type(e).__name__, e)
            if msg != last_error:  # log error ซ้ำแค่ครั้งเดียว กัน log บวม
                print("❌ {}".format(msg))
                last_error = msg
        if once or time.time() - start >= RUN_SECONDS:
            break
        time.sleep(POLL_SECONDS)
    executor.shutdown()


if __name__ == "__main__":
    main()
