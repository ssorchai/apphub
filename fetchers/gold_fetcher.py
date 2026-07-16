import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

# ราคา realtime (last/change) จาก investing.com mobile app API — แหล่งเดียวกับเว็บที่เคย scrape
# ราคาเปิดของ Futures ใช้ Yahoo Finance (GC=F) เพราะแม่นกว่า
# ประวัติหนี Cloudflare ของ investing (มันไล่จับ TLS fingerprint ขึ้นเรื่อยๆ):
# requests โดน 403 (2026-07-13) → urllib ผ่าน → urllib โดน 403 (2026-07-16)
# → ใช้ curl ของ homebrew (OpenSSL) เพราะ python นี้ผูก LibreSSL 2.8.3 ตายตัว แก้ฝั่ง python ไม่ได้
JSON_PATH = "/tmp/gold_data.json"

# ต้องเป็น path เต็ม: curl เป็น keg-only และ cron เห็นแค่ /usr/bin/curl ซึ่งโดน 403
# (เครื่องนี้ Homebrew prefix = /usr/local แม้เป็น arm64)
CURL_BIN = "/usr/local/opt/curl/bin/curl"

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


def http_get_json(url, headers, timeout=15):
    """ยิงผ่าน curl ของ homebrew ไม่ใช่ urllib — ดู CURL_BIN ข้างบนว่าทำไม
    --compressed ให้ curl จัดการ gzip เอง / -w ต่อ status code ท้าย body เพราะ
    curl ปกติ exit 0 ถึงจะได้ 403 (ต้องอ่าน code เอง ไม่ใช่ดู returncode)"""
    cmd = [CURL_BIN, "-sS", "--compressed", "--max-time", str(timeout), "-w", "\n%{http_code}"]
    for key, val in headers.items():
        cmd += ["-H", "{}: {}".format(key, val)]
    cmd.append(url)
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 5)
    if proc.returncode != 0:
        raise RuntimeError("curl failed: {}".format(proc.stderr.strip() or proc.returncode))
    body, _, code = proc.stdout.rpartition("\n")
    if code != "200":
        raise RuntimeError("HTTP {}".format(code))
    return json.loads(body)


def fetch_yahoo_futures():
    """ดึงราคาเปิดวัน + Last Price (LP) ของ GC=F จาก Yahoo — เรียกครั้งเดียวต่อรอบ
    open ของ Yahoo แม่นกว่า investing / LP ดีเลย์ ~10 นาที เก็บไว้ cross-check + fallback"""
    result = http_get_json(YAHOO_URL, UA_HEADERS)["chart"]["result"][0]
    meta = result["meta"]
    quote = result["indicators"]["quote"][0]
    # range=1d อาจได้หลายแท่งช่วงรอยต่อวันเทรด — เอาแท่งล่าสุด (วันปัจจุบัน) เสมอ
    opens = [v for v in quote.get("open", []) if v is not None]
    last = meta.get("regularMarketPrice")
    return {
        "open": round(opens[-1], 2) if opens else None,
        "last": round(last, 2) if last is not None else None,
    }


def fetch_investing(pair_id):
    payload = http_get_json(INVESTING_URL.format(pair_id), INVESTING_HEADERS)
    d = payload["data"][0]["screen_data"]["pairs_data"][0]
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


def tick(executor, yahoo_ref):
    # ยิง request ทั้ง 2 ตัวพร้อมกัน (คนละ thread) เพราะ diff ต้องมาจากราคา ณ เวลาเดียวกัน
    job_fut = executor.submit(fetch_investing, PAIR_FUTURES)
    job_spot = executor.submit(fetch_investing, PAIR_SPOT)

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
    executor = ThreadPoolExecutor(max_workers=2)
    print("🚀 gold_fetcher (HTTP mode) started {}".format(datetime.now().strftime("%H:%M:%S")))

    try:
        yahoo_ref = fetch_yahoo_futures()
    except Exception as e:
        print("⚠️ yahoo fetch failed, fallback to investing open: {}".format(e))
        yahoo_ref = {"open": None, "last": None}

    start = time.time()
    last_error = None
    while True:
        try:
            tick(executor, yahoo_ref)
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
