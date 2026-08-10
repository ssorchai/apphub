import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

# ราคา realtime (last/change) จาก investing.com mobile app API — แหล่งเดียวกับเว็บที่เคย scrape
# ราคาเปิดของ Futures ใช้ Yahoo Finance (GC=F) เพราะแม่นกว่า
# ประวัติหนี Cloudflare ของ investing (มันไล่จับ TLS fingerprint ขึ้นเรื่อยๆ):
# requests โดน 403 (2026-07-13) → urllib โดน (07-16) → brew curl โดน (08-04)
# → curl_cffi ที่ปลอม JA3 ของ browser จริง ตอนนี้ผ่านเฉพาะ fingerprint รุ่นเก่า
# (chrome110/edge101 ได้ 200 ส่วน chrome124/safari17 โดน 403) — Yahoo กับ CME ยังใช้
# brew curl ตามเดิมเพราะไม่มีปัญหาและ Yahoo แพ้ UA ยาวของ browser จริง
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

# ราคา futures รายสัญญาของ Yahoo (ใช้หา spread ระหว่างสัญญา — ดีเลย์ 10 นาทีแต่หักล้างกันเอง)
YAHOO_CONTRACT_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{}?interval=1d&range=1d"

# สัญญาที่ 0DTE อ้างอิง: ถามจาก CME วันละครั้ง แล้ว cache ไว้ (ค่านี้เปลี่ยนราว 2 เดือนครั้ง)
CME_URL = ("https://cmegroup-tools.quikstrike.net/User/QuikStrikeView.aspx"
           "?pid=40&pf=6&viewitemid=IntegratedV2VExpectedRange")
CME_REFERER = "https://www.cmegroup.com/"
ANCHOR_FILE = "/tmp/gold_anchor.json"
ANCHOR_REFRESH = 24 * 3600   # ดึงใหม่วันละครั้งพอ
ANCHOR_RETRY = 3600          # ถ้าดึงพลาด รออย่างน้อย 1 ชม. ค่อยลองใหม่ (ไม่รบกวน CME ตอนเขาล่ม)

UA_HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
INVESTING_HEADERS = dict(UA_HEADERS, **{"x-meta-ver": "14"})
# QuikStrike ต้องการ UA ตัวยาว + Referer จาก cmegroup (referrer auto-login)
CME_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
    "Referer": CME_REFERER,
}

MONTH_CODE = {"Jan": "F", "Feb": "G", "Mar": "H", "Apr": "J", "May": "K", "Jun": "M",
              "Jul": "N", "Aug": "Q", "Sep": "U", "Oct": "V", "Nov": "X", "Dec": "Z"}
CODE_MONTH = {v: k for k, v in MONTH_CODE.items()}


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


def http_get(url, headers, timeout=15):
    """ยิงผ่าน curl ของ homebrew ไม่ใช่ urllib — ดู CURL_BIN ข้างบนว่าทำไม
    --compressed ให้ curl จัดการ gzip เอง / -w ต่อ status code ท้าย body เพราะ
    curl ปกติ exit 0 ถึงจะได้ 403 (ต้องอ่าน code เอง ไม่ใช่ดู returncode)"""
    cmd = [CURL_BIN, "-sSL", "--compressed", "--max-time", str(timeout), "-w", "\n%{http_code}"]
    for key, val in headers.items():
        cmd += ["-H", "{}: {}".format(key, val)]
    cmd.append(url)
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 5)
    if proc.returncode != 0:
        raise RuntimeError("curl failed: {}".format(proc.stderr.strip() or proc.returncode))
    body, _, code = proc.stdout.rpartition("\n")
    if code != "200":
        raise RuntimeError("HTTP {}".format(code))
    return body


def http_get_json(url, headers, timeout=15):
    return json.loads(http_get(url, headers, timeout))


# fingerprint ที่ Cloudflare ของ investing ยังยอม — ไล่ลองตามลำดับ ตัวไหนผ่านจำไว้ใช้ต่อ
IMPERSONATE = ["chrome110", "edge101", "chrome107", "chrome104"]
_ok_profile = None


def investing_get_json(url, timeout=15):
    """ยิง investing ผ่าน curl_cffi (ปลอม TLS fingerprint) — curl/urllib ธรรมดาโดน 403 หมด"""
    global _ok_profile
    from curl_cffi import requests as cr
    last = None
    order = ([_ok_profile] if _ok_profile else []) + [p for p in IMPERSONATE if p != _ok_profile]
    for prof in order:
        try:
            r = cr.get(url, headers=INVESTING_HEADERS, impersonate=prof, timeout=timeout)
            if r.status_code == 200:
                if prof != _ok_profile:
                    print("🔓 investing ผ่านด้วย fingerprint {}".format(prof))
                    _ok_profile = prof
                return r.json()
            last = "HTTP {} ({})".format(r.status_code, prof)
        except Exception as e:
            last = "{} ({})".format(e, prof)
    raise RuntimeError(last or "investing ไม่ตอบ")


def fetch_yahoo_futures(month=None):
    """ราคาเปิดวัน + Last Price (LP) จาก Yahoo — เรียกครั้งเดียวต่อรอบ

    ระบุ month = ดึงของสัญญานั้นตรงๆ (เช่น 'Oct 26' -> GCV26.CMX) ใช้กับสัญญาที่ 0DTE
    อ้างอิง เพราะ open ของแต่ละสัญญาเป็นเทรดแรกของ session ซึ่งเกิดคนละวินาทีกัน
    (วัดแล้ว: Dec เปิด 05:00 ที่ 4135.2 / Oct เทรดแรก 05:10 ที่ ~4100 ตอนราคาไหลลงแล้ว)
    -> คำนวณ open ของ Oct จาก open ของ Dec ไม่ได้ ต้องเอาของสัญญานั้นเอง
    ไม่ระบุ = GC=F (front continuous) ใช้ตอนไม่รู้สัญญาอ้างอิง"""
    url = YAHOO_CONTRACT_URL.format(yahoo_symbol(month)) if yahoo_symbol(month) else YAHOO_URL
    result = http_get_json(url, UA_HEADERS)["chart"]["result"][0]
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
    payload = investing_get_json(INVESTING_URL.format(pair_id))
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


def sym_label(sym):
    """GCV6 -> 'Oct 26' (รูปแบบเดียวกับ Month ของ investing/Yahoo)"""
    if sym and len(sym) == 4 and sym[2] in CODE_MONTH and sym[3].isdigit():
        return "{} 2{}".format(CODE_MONTH[sym[2]], sym[3])
    return None


def yahoo_symbol(label):
    """'Oct 26' -> 'GCV26.CMX' (สัญลักษณ์รายสัญญาของ Yahoo)"""
    m = re.match(r"([A-Za-z]{3})\s*'?(\d{2})$", (label or "").strip())
    if not m or m.group(1).title() not in MONTH_CODE:
        return None
    return "GC{}{}.CMX".format(MONTH_CODE[m.group(1).title()], m.group(2))


def contract_alive(label):
    """สัญญาเดือนนั้นยังไม่หมดอายุไหม (กันใช้ค่า cache ค้างข้ามรอบ roll ตอน CME ล่มยาว)"""
    m = re.match(r"([A-Za-z]{3})\s*'?(\d{2})$", (label or "").strip())
    if not m or m.group(1).title() not in MONTH_CODE:
        return False
    now = datetime.now()
    year, month = 2000 + int(m.group(2)), list(MONTH_CODE).index(m.group(1).title()) + 1
    return (year, month) >= (now.year, now.month)


def fetch_cme_anchor():
    """สัญญาที่ options รายวัน (0DTE) อ้างอิงอยู่ เช่น GCV6 — อ่านจาก tooltip หน้า QuikStrike

    ทำไมต้องถาม CME: 0DTE ไม่ได้อ้าง front futures เสมอ ช่วง ต.ค. daily จะย้ายไป GCZ6
    ก่อน GCV6 หมดอายุ -> เดาจากปฏิทินไม่ได้ ต้องอ่านของจริง
    แตะ CME แค่ GET เดียว ไม่มี postback (ทั้งรายการวันหมดอายุและ tooltip อยู่ในหน้าแรกแล้ว)"""
    html = http_get(CME_URL, CME_HEADERS, timeout=45)
    exp_pat = (r"__doPostBack\(&#39;(ctl00\$ucSelector\$lvGroupsExpirations\$[^&]+?\$lbExpiration)"
               r"&#39;[^>]*>\s*<div class=\"bold\">\s*(\S+)\s*</div>\s*"
               r"<div[^>]*>\s*(\d{1,2} \w{3} \d{4})")
    best = None
    for target, _code, date_s in re.findall(exp_pat, html):
        d = datetime.strptime(date_s, "%d %b %Y").date()
        if d >= datetime.now().date() and (best is None or d < best[1]):
            best = (target, d)
    if not best:
        raise RuntimeError("หาวันหมดอายุใกล้สุดในหน้า QuikStrike ไม่เจอ")
    m = re.search(r'Underlying Symbol:\s*(GC\w+)"[^>]*href="javascript:__doPostBack\(&#39;'
                  + re.escape(best[0]), html)
    if not m:
        raise RuntimeError("หา Underlying Symbol ของ {} ไม่เจอ".format(best[1]))
    return m.group(1)


def load_state():
    try:
        return json.load(open(ANCHOR_FILE))
    except Exception:
        return {}


def due(state, key):
    """ถึงรอบดึงใหม่หรือยัง (วันละครั้ง) และเว้นจากครั้งที่พลาดอย่างน้อย 1 ชม."""
    now = time.time()
    return (now - state.get(key + "_ts", 0) > ANCHOR_REFRESH
            and now - state.get(key + "_try", 0) > ANCHOR_RETRY)


def ensure_anchor(state):
    """สัญญาที่ 0DTE อ้างอิง — ถาม CME วันละครั้ง (ค่านี้เปลี่ยนราว 2 เดือนครั้ง)

    CME ล่ม/ดึงไม่ได้ = ใช้ค่า cache ต่อ (ยังถูกอยู่เกือบตลอด เพราะเปลี่ยนนานๆ ที)
    ไม่มี cache เลย หรือสัญญาใน cache หมดอายุไปแล้ว -> คืน None = ไม่ anchor
    (widget โชว์ diff ของสัญญาที่ investing quote ตรงๆ แบบเดิม)"""
    if due(state, "anchor"):
        state["anchor_try"] = time.time()
        try:
            state["sym"] = fetch_cme_anchor()
            state["anchor_ts"] = time.time()
            print("⚓ anchor จาก CME: {}".format(state["sym"]))
        except Exception as e:
            print("⚠️ ดึง anchor จาก CME ไม่ได้ ใช้ค่าเดิม: {}".format(e))
        atomic_write(ANCHOR_FILE, state)

    label = sym_label(state.get("sym"))
    if not label or not contract_alive(label):
        return None
    return {"sym": state["sym"], "month": label}


def settle_price(month_label):
    """ราคา settlement ล่าสุดของสัญญานั้น (chartPreviousClose ของ Yahoo)"""
    sym = yahoo_symbol(month_label)
    if not sym:
        return None
    meta = http_get_json(YAHOO_CONTRACT_URL.format(sym), UA_HEADERS)["chart"]["result"][0]["meta"]
    return meta.get("chartPreviousClose")


def ensure_roll(state, anchor, quoted_month):
    """ส่วนต่างที่ต้องหักจาก quote ของ investing เพื่อให้เป็นราคาสัญญาที่ 0DTE อ้างอิง

    ใช้ราคา settlement ของทั้งสองสัญญา (ไม่ใช่ last) เพราะปิดที่วินาทีเดียวกันจริง
    -> ไม่มีปัญหาขาหนึ่งค้าง: สัญญา Oct สภาพคล่องต่ำกว่า Dec ราคา last ช้ากว่า ~1 นาที
    ทำให้ spread แบบ last แกว่ง ±1.5 จุดมั่วๆ (วัดแล้ว 33.0 / 30.1 / 30.3 ใน 40 วินาที)
    ส่วน spread จาก settlement นิ่งทั้งวันและตรงกับ CME curve (30.4 vs 30.1)

    carry เป็นค่าเชิงโครงสร้าง ขยับช้า -> ดึงวันละครั้งพอ พลาดก็ใช้ค่า cache ต่อ"""
    if not (anchor and quoted_month) or anchor["month"] == quoted_month:
        return None   # investing quote สัญญาเดียวกับที่ 0DTE อ้างอยู่แล้ว ไม่ต้องปรับ

    key = "roll_{}_{}".format(anchor["sym"], quoted_month.replace(" ", ""))
    if due(state, key):
        state[key + "_try"] = time.time()
        try:
            anchor_settle, quoted_settle = settle_price(anchor["month"]), settle_price(quoted_month)
            if anchor_settle is None or quoted_settle is None:
                raise RuntimeError("Yahoo ไม่มีราคา settlement ของสัญญาที่ขอ")
            state[key] = round(quoted_settle - anchor_settle, 2)
            state[key + "_ts"] = time.time()
            print("📐 spread {} -> {} = {}".format(quoted_month, anchor["month"], state[key]))
        except Exception as e:
            print("⚠️ คำนวณ spread ระหว่างสัญญาไม่ได้ ใช้ค่าเดิม: {}".format(e))
        atomic_write(ANCHOR_FILE, state)

    if state.get(key) is None:
        return None
    return {"sym": anchor["sym"], "month": anchor["month"], "adj": state[key]}


def apply_roll(fut, roll, yahoo_ref, quoted_month, anchor):
    """ย้าย quote futures ของ investing ไปเป็นสัญญาที่ 0DTE อ้างอิง

    ปัญหา: investing (และ Yahoo) roll ตัว continuous ตาม volume ซึ่งข้ามไป Dec ตั้งแต่
    0DTE ยังอ้าง Oct -> spread diff ที่โชว์บวมเกินจริงเท่ากับ carry ระหว่างสัญญา (~30 จุด)

    คืน (fut ที่ปรับแล้ว, yahoo_ref ของ tick นี้) — ห้าม mutate yahoo_ref ตัวจริง
    เพราะมัน fetch ครั้งเดียวใช้ทั้งรอบ (ปรับซ้ำ = หัก spread ทบทุก tick)"""
    if not fut:
        return fut, yahoo_ref
    if not roll:
        # roll = None ได้สองแบบ: (ก) investing quote สัญญาเดียวกับที่ 0DTE อ้างอยู่แล้ว
        # = ถือว่า anchored ติดรหัสได้ / (ข) หา spread ไม่ได้ = ยังเป็นสัญญาอื่นอยู่
        # ห้ามติดรหัส ไม่งั้น label จะบอกคนละสัญญากับราคา
        already = bool(anchor) and anchor["month"] == quoted_month
        fut["anchored"] = already
        if already:
            fut["sym"] = anchor["sym"]
        return fut, yahoo_ref

    adj = roll["adj"]
    fut["anchored"] = True
    fut["sym"] = roll["sym"]
    fut["quoted_month"] = fut["month"]
    fut["roll_adj"] = adj
    fut["last"] = round(fut["last"] - adj, 2)
    fut["open"] = round(fut["open"] - adj, 2) if fut.get("open") is not None else None
    fut["month"] = roll["month"]
    # change/percent (เทียบ prev close) คงของ investing ไว้: การ shift ด้วย spread ที่ขยับช้า
    # คือ parallel shift การเปลี่ยนแปลงระหว่างวันแทบเท่ากันทุกสัญญา

    # open ของ Yahoo (GC=F) เป็นของสัญญาที่ Yahoo เกาะอยู่ ซึ่งปกติคือตัวเดียวกับที่ investing
    # quote -> หักด้วย adj ตัวเดียวกันได้ แต่ถ้าวันไหนสองเจ้า roll ไม่พร้อมกัน adj จะเป็นของ
    # คนละคู่สัญญา ใช้ไม่ได้ -> ทิ้ง open ของ Yahoo ไปใช้ open ของ investing แทน
    # (ตัวนั้นเป็นสัญญาที่ investing quote แน่นอน จึงถูก shift ถูกคู่เสมอ)
    if yahoo_ref.get("open") is not None:
        if yahoo_ref.get("month") == quoted_month:
            yahoo_ref = dict(yahoo_ref, open=round(yahoo_ref["open"] - adj, 2))
        elif yahoo_ref.get("month") != roll["month"]:
            print("⚠️ Yahoo เกาะ {} แต่ investing quote {} -> ใช้ open ของ investing".format(
                yahoo_ref.get("month"), quoted_month))
            yahoo_ref = dict(yahoo_ref, open=None)
    return fut, yahoo_ref


def tick(executor, yahoo_ref, state, anchor, roll_state):
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

    # ย้าย quote ไปสัญญาที่ 0DTE อ้างอิง ก่อนคำนวณทุกอย่าง (diff ตามไปเอง)
    # หา spread ครั้งเดียวต่อรอบ cron — คิดใหม่เมื่อ investing เปลี่ยนสัญญาที่ quote
    tick_yahoo = yahoo_ref
    if fut:
        if roll_state.get("month") != fut["month"]:
            roll_state["month"] = fut["month"]
            roll_state["roll"] = ensure_roll(state, anchor, fut["month"])
        fut, tick_yahoo = apply_roll(fut, roll_state.get("roll"), yahoo_ref, fut["month"], anchor)

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
            "anchored": fut.get("anchored", False),
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

    state = load_state()        # cache ของที่เปลี่ยนวันละครั้ง: สัญญาอ้างอิง + spread
    anchor = ensure_anchor(state)

    # open ดึงจากสัญญาที่ 0DTE อ้างอิงโดยตรง (ค่านี้ถูกใช้เป็น mean ของกรอบ SD ใน cme_fetcher
    # ด้วย จึงต้องเป็น open ของ series นั้นจริงๆ ไม่ใช่ค่าที่ derive มาจากสัญญาอื่น)
    try:
        yahoo_ref = fetch_yahoo_futures(anchor["month"] if anchor else None)
        if yahoo_ref.get("open") is None and anchor:
            print("⚠️ Yahoo ยังไม่มี open ของ {} (ยังไม่มีเทรดแรก?) -> ใช้ front แทน".format(
                anchor["month"]))
            yahoo_ref = fetch_yahoo_futures()
    except Exception as e:
        print("⚠️ yahoo fetch failed, fallback to investing open: {}".format(e))
        yahoo_ref = {"open": None, "last": None, "month": None}
    roll_state = {}

    start = time.time()
    last_error = None
    while True:
        try:
            tick(executor, yahoo_ref, state, anchor, roll_state)
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
