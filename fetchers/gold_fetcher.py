import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime

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
# carry อ่านจาก curve จริงของ CME (/tmp/cme_curve.json ที่ cme_fetcher.py เขียนรายชั่วโมง)
# CARRY_RATE เหลือเป็น fallback เมื่ออ่าน curve ไม่ได้เท่านั้น
CARRY_RATE = 0.02
CURVE_FILE = "/tmp/cme_curve.json"
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
        # "Gold Dec 26" -> "Dec 26" เอาไว้เช็คว่า open เป็นของสัญญาไหน (Yahoo roll ตาม volume)
        "month": meta.get("shortName", "").replace("Gold ", "").strip() or None,
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


PUTCALL_FILE = "/tmp/cme_putcall.json"
MONTH_OF_CODE = {"F": "Jan", "G": "Feb", "H": "Mar", "J": "Apr", "K": "May", "M": "Jun",
                 "N": "Jul", "Q": "Aug", "U": "Sep", "V": "Oct", "X": "Nov", "Z": "Dec"}


def sym_label(sym):
    """GCV6 -> 'Oct 26' (รูปแบบเดียวกับ Month ของ investing/Yahoo)"""
    if sym and len(sym) == 4 and sym[2] in MONTH_OF_CODE and sym[3].isdigit():
        return "{} 2{}".format(MONTH_OF_CODE[sym[2]], sym[3])
    return None


def read_ref_sym():
    """underlying จริงของ 0DTE (เช่น GCV6) ที่ cme_fetcher แกะจาก tooltip QuikStrike รายชั่วโมง
    — สำคัญเพราะ 0DTE ไม่ได้อ้าง front เสมอ (ช่วง ต.ค. daily ย้ายไป GCZ6 ก่อน GCV6 หมดอายุ)"""
    try:
        if os.path.getmtime(PUTCALL_FILE) > datetime.now().timestamp() - 6 * 3600:
            return json.load(open(PUTCALL_FILE)).get("und_sym")
    except Exception:
        pass
    return None


def reanchor(fut, yahoo_ref):
    """ย้าย quote futures ของ investing ไปยังสัญญาอ้างอิง 0DTE ของ CME

    ปัญหา: investing (และ Yahoo) roll ตัว continuous ตาม volume ซึ่งข้ามไป Dec
    ตั้งแต่ 0DTE ยังอ้าง Oct (GCV6) -> spread diff ที่โชว์บวมเกินจริง ~30 จุด
    วิธี: ราคา GCV6 realtime = ราคา Dec realtime - spread(Dec-Oct จาก CME curve)
    spread ภายใน feed QuikStrike เดียวกัน ความช้า 4-5 จุดหักล้างกันหมด ใช้ shift ได้สะอาด
    (ห้ามใช้ราคา QuikStrike ตรงๆ เพราะช้ากว่า feed สด)

    คืน (fut ที่ปรับแล้ว, yahoo_ref สำหรับ tick นี้) — ห้าม mutate yahoo_ref ตัวจริง
    เพราะมันถูก fetch ครั้งเดียวใช้ทั้งรอบ (ปรับซ้ำ = ลบ spread ทบทุก tick)
    พลาด/ไม่มี curve ก็คืนของเดิมโดยไม่แตะ"""
    curve = read_curve()
    if not (fut and curve and fut.get("settlement")):
        return fut, yahoo_ref
    try:
        cons = curve["contracts"]
        ref_sym = read_ref_sym()
        anchor = next((c for c in cons if c["sym"] == ref_sym), cons[0])
        settle = date.fromisoformat(fut["settlement"])
        quoted = next((c for c in cons
                       if abs((date.fromisoformat(c["expiry"]) - settle).days) <= 3), None)
        fut["sym"] = anchor["sym"]
        if quoted is None or quoted["sym"] == anchor["sym"]:
            return fut, yahoo_ref  # quote ตรงสัญญาอ้างอิงอยู่แล้ว / หาไม่เจอ = ไม่แตะ

        adj = round(quoted["price"] - anchor["price"], 2)
        fut["quoted_month"] = fut["month"]
        fut["roll_adj"] = adj
        fut["last"] = round(fut["last"] - adj, 2)
        fut["open"] = round(fut["open"] - adj, 2) if fut.get("open") is not None else None
        fut["month"] = sym_label(anchor["sym"]) or fut["month"]
        fut["settlement"] = anchor["expiry"]
        # change/percent (เทียบ prev close) คงของ investing ไว้: การ shift ด้วย spread
        # ที่ขยับช้าคือ parallel shift การเปลี่ยนแปลงระหว่างวันแทบเท่ากันทุกสัญญา

        # open ของ Yahoo เป็นของสัญญาที่ Yahoo เกาะอยู่ — ปรับเฉพาะเมื่อไม่ใช่สัญญา anchor
        if yahoo_ref.get("open") is not None and yahoo_ref.get("month") != fut["month"]:
            yahoo_ref = dict(yahoo_ref, open=round(yahoo_ref["open"] - adj, 2))
        return fut, yahoo_ref
    except Exception:
        return fut, yahoo_ref


def read_curve():
    """futures curve จริงจาก CME ที่ cme_fetcher.py เขียนไว้รายชั่วโมง (ต้องสดไม่เกิน 3 ชม.)
    — carry เป็นค่าเชิงโครงสร้าง ขยับช้า ใช้ข้ามชั่วโมงได้ (ต่างจากราคาที่ใช้ไม่ได้)"""
    try:
        # cme_fetcher เขียน curve ทุก 12 ชม. -> เกณฑ์สดต้องหลวมกว่ารอบเขียน (12+3)
        if os.path.getmtime(CURVE_FILE) < datetime.now().timestamp() - 15 * 3600:
            return None
        c = json.load(open(CURVE_FILE))
        return c if c.get("contracts") else None
    except Exception:
        return None


def theory_diff(fut, spot):
    """ค่าอ้างอิงของ basis + ข้อมูล curve จริงจาก CME

    diff/raw = basis "สด" ที่วัดได้ (F - S จาก investing ทั้งคู่ ยิงพร้อมกัน) ปัดขั้นละ 2.5
    ตาม convention -- ไม่ใช่โมเดล carry อีกแล้ว เพราะวัดแล้ว basis ของ front นิ่งมาก
    (แกว่ง 0.56 จุดใน 1 นาที) โมเดลค่าคงที่จึงไม่มีอะไรจะเพิ่ม มีแต่จะผิด

    carry       = carry ที่ basis สดตัวนี้ imply (spot -> front contract)
    curve_carry = carry ระหว่างสัญญาจาก CME curve (โครงสร้างจริง ไม่พึ่ง spot)
    curve_fair  = basis ที่ front "ควรเป็น" ถ้า curve ตรง = ใช้ curve_carry
    kink        = basis สด - curve_fair : curve ทองหักศอกที่ front (near-term squeeze)
    next        = diff ที่จะเจอตอน roll = basis สด + spread ของสัญญาถัดไป (จาก CME)
                  ** ต้องบวกแบบ spread เท่านั้น: F ของ QuikStrike ช้ากว่า feed สด ~4-5 จุด
                     เอา F ของมันมาลบ spot ของ investing ตรงๆ จะได้ความช้าปนมาเต็มๆ **
    """
    if not (fut and spot and fut.get("settlement")):
        return None
    try:
        expiry = datetime.strptime(fut["settlement"], "%Y-%m-%d").date()
        days = (expiry - datetime.now().date()).days
        if days < 0:
            return None

        basis = fut["last"] - spot["last"]
        out = {
            "diff": round(round(basis / THEORY_STEP) * THEORY_STEP, 2),
            "raw": round(basis, 2),
            "days": days,
            "carry": round(basis / (spot["last"] * days / 365.0) * 100, 2) if days > 0 else None,
            "source": "live",
        }

        curve = read_curve()
        if curve:
            cons = curve["contracts"]
            me = next((c for c in cons
                       if abs((date.fromisoformat(c["expiry"]) - expiry).days) <= 3), None)
            if me:
                out["source"] = "curve"
                later = [c for c in cons if date.fromisoformat(c["expiry"]) > expiry]
                if later:
                    n = later[0]
                    out["next"] = {
                        "sym": n["sym"], "days": n["days"],
                        # spread ภายใน feed เดียวกัน -> ความช้าหักล้าง บวกกับ basis สดได้เลย
                        "diff": round(basis + (n["spread_vs_front"] - me["spread_vs_front"]), 2),
                    }
            if curve.get("spread_carry"):
                out["curve_carry"] = curve["spread_carry"]
                fair = spot["last"] * curve["spread_carry"] / 100.0 * days / 365.0
                out["curve_fair"] = round(fair, 2)
                out["kink"] = round(basis - fair, 2)
        return out
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

    # ย้าย quote ไปสัญญาอ้างอิง 0DTE ของ CME ก่อนคำนวณทุกอย่าง (diff/theory ตามไปเอง)
    tick_yahoo = yahoo_ref
    if fut:
        fut, tick_yahoo = reanchor(fut, yahoo_ref)

    # future: open ใช้ Yahoo (แม่นกว่า) / change,percent = เทียบ prev close (จาก investing)
    # เพิ่ม change_open,percent_open = last price เทียบ open ของวัน (เฉพาะ future)
    fut_future = None
    if fut:
        fut_open = tick_yahoo["open"] if tick_yahoo.get("open") is not None else fut["open"]
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
            "yahoo_last": tick_yahoo.get("last"),
            "sym": fut.get("sym"),
            "quoted_month": fut.get("quoted_month"),
            "roll_adj": fut.get("roll_adj"),
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
