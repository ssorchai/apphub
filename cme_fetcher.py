#!/usr/bin/env python3
"""
CME QuikStrike Vol2Vol -- Gold 0DTE Put/Call fetcher (Intraday + OI)

HTTP ล้วน ไม่มี headless browser: backend ของ QuikStrike auto-login ให้เมื่อ
request มี Referer จาก cmegroup.com (pid=40/pf=6 = Gold, ไม่ใส่ insid = series
ใกล้หมดอายุสุด) หน้าแรก GET = แท็บ Intraday Volume แล้ว POST (__doPostBack
จำลอง WebForms) สลับไปแท็บ Open Interest -- ข้อมูลฝังใน HTML เป็น
$create(...Chart, {"JSONSettings": "<json>"})

Output (atomic เขียน .tmp แล้ว os.replace เหมือน fetcher ตัวอื่น):
  /tmp/cme_putcall.json      ให้ cme-putcall.jsx (Übersicht) อ่านแสดงผล
  /tmp/cme_putcall_clip.txt  string สำหรับ paste ลงช่อง P/C ของ oi_block.pine:
      F:4187.0|D:2026-07-03 17:55|S:G1MN6|IV:23.57|IVCHG:0.02|DTE:3.419
      ID;4090:12:5;4100:44:10;...        (strike:put:call เฉพาะที่มีของ)
      OI;4000:821:66;...
      VS;3900:31.87;3925:30.12;...       (strike:settle vol% ทุก strike ในชาร์ต ใช้วาด smile)

cron รายชั่วโมง:
  7 * * * * /usr/bin/python3 /Users/sorachai/src/my-cronjob/cme_fetcher.py >> /tmp/cme_cron.log 2>&1
ทดสอบ: python3 cme_fetcher.py --once  (โหมดเดียวที่มี -- รันครั้งเดียวเสมอ)
"""

import calendar
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import http.cookiejar
from datetime import date, datetime, timedelta

URL = ("https://cmegroup-tools.quikstrike.net/User/QuikStrikeView.aspx"
       "?pid=40&pf=6&viewitemid=IntegratedV2VExpectedRange")
REFERER = "https://www.cmegroup.com/"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
OI_TARGET = "ctl00$MainContent$ucViewControl_IntegratedV2VExpectedRange$lbOI"
MARKER = "UserControlsV2.QuikOptionsV2V.Chart, "

JSON_OUT = "/tmp/cme_putcall.json"
CLIP_OUT = "/tmp/cme_putcall_clip.txt"

# SD จากราคาเปิดวัน (Yahoo แม่นกว่า investing — pattern เดียวกับ gold_fetcher.py)
# DTE fix 0.6 = ตัดช่วงเอเชียเช้าทิ้ง / vol ใช้ Vol - Vol Chg = settle ATM vol ทางการ
YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/GC=F?interval=1d&range=1d"
SD_DTE = 0.6

# ⚠️ Yahoo ต้องใช้ UA "สั้น" ตัวนี้เท่านั้น ห้ามใช้ UA ตัวบน (ที่มี Chrome/126...)
# — Yahoo ตอบ 429 ให้ UA ตัวนั้นแบบ deterministic (ยิงสลับ back-to-back วินาทีเดียวกัน:
#   short=200 / chrome126=429 ทั้ง 3 รอบ) ตัวแปรคือ UA string ล้วนๆ ไม่ใช่ TLS
YAHOO_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

# ต้องเป็น path เต็ม: curl เป็น keg-only และ cron เห็นแค่ /usr/bin/curl ซึ่งโดน 403
# (เครื่องนี้ Homebrew prefix = /usr/local แม้เป็น arm64)
CURL_BIN = "/usr/local/opt/curl/bin/curl"

# state รอบก่อน สำหรับหา "ของที่เติมเข้ามา" ระหว่าง refresh (แบบวงเล็บ +28 ของบอท telegram)
PREV_STATE = "/tmp/cme_putcall_prev.json"

# futures curve จริงจาก QuikStrike -> ให้ gold_fetcher.py ใช้แทน CARRY_RATE คงที่
# (เก็บ "carry" ไม่ใช่ราคา: ราคาเก่า 1 ชม. เอาไปทำ basis กับ spot สดไม่ได้ แต่ carry ขยับช้า)
CURVE_OUT = "/tmp/cme_curve.json"
CURVE_N = 3            # จำนวน contract ใกล้สุดที่ดึง
CURVE_MAX_AGE = 12 * 3600   # carry เป็นค่าเชิงโครงสร้าง ขยับช้า -- ดึงวันละ 2 ครั้งพอ
                            # (ดึงทีนึง = 3 page load ตอนเซิร์ฟช้าคือตัวถ่วงหลัก)
MONTH_CODE = {"F": 1, "G": 2, "H": 3, "J": 4, "K": 5, "M": 6,
              "N": 7, "Q": 8, "U": 9, "V": 10, "X": 11, "Z": 12}

# ---- fallback chain: QuikStrike -> pageth (mirror ท่อเดียวกัน) -> Barchart (feed อิสระ) ----
# pageth ตาย พร้อม QuikStrike เสมอ (พิสูจน์ 17 ก.ค.: commit สุดท้าย = นาทีที่ QS ล่ม)
# แต่ช่วยเคส "ฝั่งเราพัง" (IP โดนแบน / referrer trick เสีย / HTML เปลี่ยน)
PAGETH_API = "https://api.github.com/repos/pageth/Vol2VolData/commits?per_page=1"
PAGETH_RAW = "https://raw.githubusercontent.com/pageth/Vol2VolData/main/"
PAGETH_MAX_AGE = 20 * 60   # commit เก่ากว่านี้ = บอทเขาหยุด (ปกติ sync ทุก ~6 นาที)

# Barchart: feed CME ที่ license เอง (delayed 10-15 นาที) — รอดตอน QuikStrike ล่มจริง
# ใช้ API ภายในของหน้าเว็บ: โหลดหน้าเอา cookie แล้วยิง core-api ด้วย XSRF token จาก cookie
BC_BASE = "https://www.barchart.com"
BC_CHAIN_FIELDS = "optionType,lastPrice,volume,openInterest,strikePrice,symbolName"
# เดือนของ gold futures มาตรฐาน (G J M Q V Z) ใช้หา front contract
GC_MONTHS = [2, 4, 6, 8, 10, 12]


# เพดานเวลารวมทั้งรอบ: urllib นับ timeout ต่อ socket ไม่ใช่ต่อ request -- ตอนเซิร์ฟช้า
# redirect หลาย hop x retry ทบกันได้ถึง 4 นาที (วัดจริง 17 ก.ค. 2026) cron รายชั่วโมง
# ไม่ควรค้างขนาดนั้น หมดเวลาก็ยอมแพ้ไปรอบหน้า ข้อมูลเดิมยังอยู่
# หมายเหตุ: กันได้แค่ "ก่อนยิง request ถัดไป" -- ตัวที่ยิงค้างอยู่ยังกินได้อีก
# (per-socket timeout x จำนวน redirect hop) จริงจึงจบราว MAX_RUNTIME + ~40s
MAX_RUNTIME = 100          # งบของ QuikStrike (แหล่งหลัก)
# งบ "ต่อแหล่ง" -- ถ้าเป็นงบรวม แหล่งแรกที่ช้าจะกินหมดคนเดียวแล้วตัดสิทธิ์แหล่งสำรอง
# (เจอจริง: QS ใช้ 95s -> pageth/barchart โดน "เกินงบ" ทั้งที่ยังไม่ได้ลอง)
SOURCE_BUDGET = {"quikstrike": 100, "pageth": 30, "barchart": 75}
_deadline = None


class QuikStrikeDown(Exception):
    """backend ของ QuikStrike เองมีปัญหา ไม่ใช่โค้ดเรา -- retry ในรอบนี้ไม่ช่วย"""


def _budget(cap=45):
    """เวลาที่เหลือในงบ (วินาที) -- ใช้เป็น timeout ของ request ถัดไป"""
    if _deadline is None:
        return cap
    left = _deadline - time.monotonic()
    if left <= 1:
        raise QuikStrikeDown(f"เกินงบเวลา {MAX_RUNTIME}s (เซิร์ฟช้าผิดปกติ)")
    return min(cap, left)


def _check_page(html, url=""):
    """จับหน้า error/login ของ QuikStrike ก่อนเอาไป parse

    ทั้งสองหน้าตอบ HTTP 200 ปกติ ดู status code อย่างเดียวไม่พอ (เจอจริง 17 ก.ค. 2026:
    DB ฝั่งเขา timeout -> เด้งไป ErrorPage.aspx?MSG=Timeout+expired... พร้อม 200 + TTFB 32s)
    """
    if "/Error/ErrorPage.aspx" in url or "<title>QuikStrike Error" in html[:3000]:
        m = re.search(r"MSG=([^&]*)", url)
        msg = urllib.parse.unquote_plus(m.group(1)).strip()[:100] if m else "ไม่ทราบสาเหตุ"
        raise QuikStrikeDown(f"backend ตอบ error page: {msg}")
    if "/Account/Login.aspx" in url:
        raise QuikStrikeDown("โดนเด้งไปหน้า login (referrer auto-login ไม่ทำงาน)")


def _get(op, url, tries=2):
    """GET พร้อม retry: ตอนเซิร์ฟช้า (TTFB 30s+) รอบแรกมักหลุด รอบสองผ่าน"""
    last = None
    for i in range(tries):
        try:
            r = op.open(url, timeout=_budget())
            html = r.read().decode()
            _check_page(html, r.geturl())
            return html, r.geturl()
        except QuikStrikeDown:
            raise
        except Exception as e:
            last = e
            if i + 1 < tries:
                time.sleep(min(3, _budget(3)))
    raise last


def _grab_object(s, start):
    depth, in_str, esc, j = 0, False, False, start
    while j < len(s):
        c = s[j]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return s[start:j + 1]
        j += 1
    raise ValueError("unbalanced braces")


def extract_payload(html):
    """settings dict ของ chart แรกที่เจอในหน้า (แต่ละแท็บมี chart เดียว)"""
    i = html.find(MARKER)
    if i < 0:
        raise ValueError("chart payload not found")
    outer = json.loads(_grab_object(html, html.index("{", i)))
    return json.loads(outer["JSONSettings"])


def series_points(settings, key):
    return {round(p["x"], 4): p["y"] for p in settings.get(key, {}).get("data", [])}


def _postback(op, url, html, target):
    """จำลอง __doPostBack ของ WebForms: ส่ง hidden fields ทั้งหมดกลับ + __EVENTTARGET"""
    fields = dict(re.findall(
        r'<input type="hidden" name="([^"]+)"[^>]*value="([^"]*)"', html))
    fields["__EVENTTARGET"] = target
    fields["__EVENTARGUMENT"] = ""
    req = urllib.request.Request(
        url, data=urllib.parse.urlencode(fields).encode(),
        headers={"User-Agent": UA, "Referer": url,
                 "Content-Type": "application/x-www-form-urlencoded"})
    r = op.open(req, timeout=_budget())
    html = r.read().decode()
    _check_page(html, r.geturl())
    return html


def nearest_expiration(html):
    """(postback_target, code, date) ของ series ที่หมดอายุใกล้สุดจาก selector บนหน้า
    — default ของ QuikStrike บางวันไม่เลือก daily 0DTE ให้ (เช่นไปหยิบ weekly แทน)"""
    pat = (r"__doPostBack\(&#39;(ctl00\$ucSelector\$lvGroupsExpirations\$[^&]+?\$lbExpiration)"
           r"&#39;[^>]*>\s*<div class=\"bold\">\s*(\S+)\s*</div>\s*"
           r"<div[^>]*>\s*(\d{1,2} \w{3} \d{4})")
    best = None
    for target, code, date_s in re.findall(pat, html):
        d = datetime.strptime(date_s, "%d %b %Y").date()
        if d >= datetime.now().date() and (best is None or d < best[2]):
            best = (target, code, d)
    return best


def underlying_of(html, target):
    """Underlying Symbol ของ expiration ที่เลือก — อ่านจาก tooltip บนหน้า selector
    (วิธีเดียวกับที่คนดูด้วยตา: ชี้เมาส์ที่วันที่ แล้วดู Underlying Symbol เช่น GCV6)
    สำคัญเพราะ 0DTE ไม่ได้อ้าง front futures เสมอ เช่นช่วง ต.ค. daily จะย้ายไป GCZ6
    ทั้งที่ GCV6 ยังไม่หมดอายุ"""
    m = re.search(r'Underlying Symbol:\s*(GC\w+)"[^>]*href="javascript:__doPostBack\(&#39;'
                  + re.escape(target), html)
    return m.group(1) if m else None


def futures_expiry(sym):
    """GCQ6 -> วันหมดอายุของ futures = business day ที่ 3 นับถอยหลังจากสิ้นเดือนส่งมอบ
    (ตรงกับ Settlement Day ที่ investing รายงาน — ตรวจแล้วกับ GCQ6 = 2026-08-27)"""
    m = re.match(r"GC([FGHJKMNQUVXZ])(\d)$", sym)
    if not m:
        return None
    month = MONTH_CODE[m.group(1)]
    now = datetime.now()
    year = (now.year // 10) * 10 + int(m.group(2))
    if year < now.year:
        year += 10
    d = date(year, month, calendar.monthrange(year, month)[1])
    n = 0
    while True:
        if d.weekday() < 5:
            n += 1
            if n == 3:
                return d
        d -= timedelta(days=1)


def curve_is_fresh():
    """curve ที่มีอยู่ยังใหม่พอไหม -- ไม่ต้องไปกวนเซิร์ฟซ้ำถ้ายังใช้ได้"""
    try:
        return os.path.getmtime(CURVE_OUT) > datetime.now().timestamp() - CURVE_MAX_AGE
    except Exception:
        return False


def fetch_curve(op, url, html):
    """ราคา futures ของ contract ใกล้หมดอายุสุด CURVE_N ตัว + spread เทียบ contract หน้า

    เก็บเฉพาะ "spread ระหว่างสัญญา" ไม่เก็บ basis เทียบ spot -- เพราะ F ของ QuikStrike
    ช้ากว่า feed realtime ~4-5 จุด (วัดแล้ว: QS ค้างที่ 3989.6 ขณะ investing ไหลถึง 3984.8)
    เอาไปลบ spot ของอีกเจ้าจะได้ค่าความช้าปนมาเต็มๆ ใหญ่กว่า basis จริงเสียอีก
    แต่ spread = ผลต่างภายใน feed เดียวกัน -> ความช้าหักล้างกันหมด ใช้ได้สะอาด
    """
    pat = (r'Underlying Symbol:\s*(GC\w+)"[^>]*href="javascript:__doPostBack\(&#39;'
           r'(ctl00\$ucSelector\$[^&]+?\$lbExpiration)&#39;')
    seen = {}
    for und, target in re.findall(pat, html):
        seen.setdefault(und, target)
    cands = []
    for und, target in seen.items():
        exp = futures_expiry(und)
        if exp and exp >= date.today():
            cands.append((exp, und, target))
    cands.sort()

    out = []
    for exp, und, target in cands[:CURVE_N]:
        try:
            s = extract_payload(_postback(op, url, html, target))
            price = s.get("FuturePrice")
            if price:
                out.append({"sym": und, "price": price, "expiry": exp.isoformat(),
                            "days": (exp - date.today()).days})
        except Exception:
            pass
    if not out:
        return None

    front = out[0]["price"]
    for c in out:
        # spread เทียบ front: บวกเข้ากับ basis สดของ front = basis ของสัญญานั้น (ตอน roll)
        c["spread_vs_front"] = round(c["price"] - front, 2)
    # carry ระหว่างสัญญา = โครงสร้าง curve ล้วนๆ ไม่พึ่ง spot และไม่โดนความช้าของ feed
    spread_carry = None
    if len(out) >= 2:
        import math
        gap = (date.fromisoformat(out[1]["expiry"]) - date.fromisoformat(out[0]["expiry"])).days
        if gap > 0:
            spread_carry = round(math.log(out[1]["price"] / out[0]["price"]) / (gap / 365) * 100, 3)
    return {"ts": datetime.now().timestamp(), "contracts": out, "spread_carry": spread_carry}


def fetch_both_tabs():
    jar = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    op.addheaders = [("User-Agent", UA), ("Referer", REFERER)]
    html, final_url = _get(op, URL)
    base_html = html   # หน้าตั้งต้น: viewstate ของมันใช้ postback ได้ทุกปลายทาง

    curve = None
    if not curve_is_fresh():
        try:
            curve = fetch_curve(op, final_url, base_html)
        except QuikStrikeDown:
            raise
        except Exception:
            curve = None

    # บังคับเลือก series ที่หมดอายุใกล้สุดเสมอ (พลาดก็ใช้ default ของหน้าไป)
    und_ref = None
    try:
        best = nearest_expiration(html)
        if best:
            und_ref = underlying_of(base_html, best[0])
            html = _postback(op, final_url, html, best[0])
    except Exception:
        pass

    intraday = extract_payload(html)
    oi = extract_payload(_postback(op, final_url, html, OI_TARGET))
    return intraday, oi, curve, und_ref


def strike_rows(settings):
    """[(strike, put, call)] เฉพาะ strike ที่มี put+call > 0"""
    put, call = series_points(settings, "Put"), series_points(settings, "Call")
    rows = []
    for k in sorted(set(put) | set(call)):
        p, c = int(put.get(k, 0) or 0), int(call.get(k, 0) or 0)
        if p + c > 0:
            rows.append((int(k) if k == int(k) else k, p, c))
    return rows


def meta_of(settings):
    sub = re.sub("<[^>]+>", "", settings.get("Subtitle", ""))
    sub = sub.replace("&nbsp;", " ").replace("\xa0", " ")
    m = re.search(r"Future Chg:\s*(-?[\d.]+)", sub)
    value_name = settings.get("ValueName", "")
    return {
        "series": settings.get("Title", "").replace(value_name, "").strip(),
        "F": settings.get("FuturePrice"),
        "dte": settings.get("DTE"),
        "iv": round((settings.get("ATMVol") or 0) * 100, 2),
        "future_chg": float(m.group(1)) if m else None,
    }


def top_actives(rows, n=2):
    return [{"strike": s, "total": p + c, "put": p, "call": c}
            for s, p, c in sorted(rows, key=lambda r: -(r[1] + r[2]))[:n]]


def curl_get_json(url, headers, timeout=15):
    """ยิงผ่าน curl ของ homebrew — โค้ดเดียวกับ http_get_json ใน gold_fetcher.py ทุกบรรทัด
    (fetcher แต่ละตัวเป็น script เดี่ยว ไม่มี module กลาง เลยยอม copy — แก้ต้องแก้ทั้งคู่)
    -w ต่อ status code ท้าย body เพราะ curl ปกติ exit 0 ถึงจะได้ 403/429"""
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


def fetch_yahoo_open():
    """ราคาเปิดวันของ GC=F — อ่านจาก /tmp/gold_data.json ที่ gold_fetcher.py (cron 5 นาที)
    เขียนไว้อยู่แล้ว (ไม่ยิง Yahoo ซ้ำ) — ต้องสดไม่เกิน 15 นาที ไม่งั้นยิง Yahoo ตรง
    เป็น fallback ผ่าน brew curl + YAHOO_UA (UA ยาวโดน 429) / พังก็คืน None (ห้ามใช้ค่าเก่า)"""
    try:
        p = "/tmp/gold_data.json"
        if os.path.getmtime(p) > datetime.now().timestamp() - 900:
            open_v = (json.load(open(p)).get("future") or {}).get("open")
            if open_v is not None:
                return round(float(open_v), 2)
    except Exception:
        pass
    result = curl_get_json(YAHOO_URL, {"User-Agent": YAHOO_UA})["chart"]["result"][0]
    opens = [v for v in result["indicators"]["quote"][0].get("open", []) if v is not None]
    return round(opens[-1], 2) if opens else None


def sd_levels(open_price, iv, iv_chg):
    """กรอบ SD: mean = ราคาเปิด Yahoo, DTE 0.6, vol = Vol - Vol Chg (settle ATM ทางการ)
    — คืน None ถ้าขาดส่วนผสม"""
    if open_price is None or iv is None or iv_chg is None:
        return None
    import math
    vol_used = iv - iv_chg
    sd1 = open_price * (vol_used / 100.0) * math.sqrt(SD_DTE / 365.0)
    lv = {f"{side}{n}": round(open_price + (n * sd1 if side == "s" else -n * sd1), 1)
          for n in (1, 2, 3) for side in ("b", "s")}
    return dict(open=open_price, vol_used=round(vol_used, 2), dte=SD_DTE,
                sd1=round(sd1, 1), **lv)


def top_changes(rows_now, prev_map, n=2):
    """เทียบ per-strike กับรอบก่อน คืน n อันดับที่เปลี่ยนมากสุด [{strike, dp, dc}]
    นับเฉพาะ strike ที่อยู่ในรอบปัจจุบัน — ตัวที่หายไปมักเป็นเพราะหน้าต่างชาร์ตเลื่อน
    (จะกลายเป็น delta ลบปลอมก้อนใหญ่) ไม่ใช่การปิดสัญญาจริง"""
    changes = []
    for s, p, c in rows_now:
        p_old, c_old = prev_map.get(str(s), (0, 0))
        dp, dc = p - p_old, c - c_old
        if dp or dc:
            changes.append({"strike": s, "dp": dp, "dc": dc})
    changes.sort(key=lambda x: -(abs(x["dp"]) + abs(x["dc"])))
    return changes[:n]


def snapshot_quikstrike():
    """แหล่งหลัก: QuikStrike Vol2Vol — ครบสุด (P/C สองชุด + smile + curve)"""
    intraday, oi, curve, und_sym = fetch_both_tabs()
    meta = meta_of(oi)
    sub = re.sub("<[^>]+>", "", oi.get("Subtitle", "")).replace("\xa0", " ")
    mv = re.search(r"Vol Chg:\s*(-?[\d.]+)", sub)
    vs = series_points(oi, "VolSettle")
    return {
        "source": "quikstrike", "und_sym": und_sym,
        "series": meta["series"], "F": meta["F"],
        "dte": meta["dte"], "iv": meta["iv"],
        "iv_chg": float(mv.group(1)) if mv else None,
        "future_chg": meta["future_chg"],
        "id_rows": strike_rows(intraday), "oi_rows": strike_rows(oi),
        "vs_rows": [(int(k) if k == int(k) else k, v * 100)
                    for k, v in sorted(vs.items()) if v and v > 0],
        "curve": curve,
    }


def _parse_pageth(txt):
    """ไฟล์ IntradayData/OIData ของ pageth — format เดียวกับที่เราสร้างตอน backtest
    คอลัมน์อ่านตามชื่อ header (ลำดับ Call/Put เคยสลับกันมาแล้วในอดีต)"""
    lines = txt.strip().split("\n")
    m1 = re.search(r"(\S+) \(([\d.]+) DTE\) vs ([\d.]+) \((-?\+?[\d.-]+)\)", lines[0])
    m2 = re.search(r"Vol:\s*([\d.]+)\s+Vol Chg:\s*(-?[\d.]+)", lines[1].replace("\xa0", " "))
    if not m1:
        raise ValueError("pageth header ไม่ตรง format")
    cols = [c.strip().lower() for c in lines[2].split(",")]
    i_s, i_c, i_p = cols.index("strike"), cols.index("call"), cols.index("put")
    i_v = next((i for i, c in enumerate(cols) if c.startswith("vol")), None)
    rows, vs = [], []
    for ln in lines[3:]:
        p = ln.split(",")
        if len(p) < 3:
            continue
        try:
            s = float(p[i_s])
            s = int(s) if s == int(s) else s
            put, call = int(float(p[i_p])), int(float(p[i_c]))
            if put + call > 0:
                rows.append((s, put, call))
            if i_v is not None and float(p[i_v]) > 0:
                vs.append((s, float(p[i_v]) * 100))
        except (ValueError, IndexError):
            pass
    return {
        "series": m1.group(1), "dte": float(m1.group(2)), "F": float(m1.group(3)),
        "future_chg": float(m1.group(4).replace("+", "")),
        "iv": float(m2.group(1)) if m2 else None,
        "iv_chg": float(m2.group(2)) if m2 else None,
        "rows": rows, "vs": vs,
    }


def snapshot_pageth():
    """สำรองชั้น 1: repo mirror ของ pageth — ต้องเช็คความสดก่อน (ตายพร้อม QuikStrike)"""
    req = urllib.request.Request(PAGETH_API, headers={"User-Agent": UA})
    commits = json.loads(urllib.request.urlopen(req, timeout=_budget(20)).read())
    last = datetime.strptime(commits[0]["commit"]["committer"]["date"],
                             "%Y-%m-%dT%H:%M:%S%z")
    age = datetime.now(last.tzinfo) - last
    if age.total_seconds() > PAGETH_MAX_AGE:
        raise RuntimeError(f"pageth ค้าง {age.total_seconds()/60:.0f} นาที")

    def raw(name):
        r = urllib.request.Request(PAGETH_RAW + name, headers={"User-Agent": UA})
        return urllib.request.urlopen(r, timeout=_budget(20)).read().decode()

    idd = _parse_pageth(raw("IntradayData.txt"))
    oid = _parse_pageth(raw("OIData.txt"))
    return {
        "source": "pageth", "series": idd["series"], "F": idd["F"],
        "dte": idd["dte"], "iv": idd["iv"], "iv_chg": idd["iv_chg"],
        "future_chg": idd["future_chg"],
        "id_rows": idd["rows"], "oi_rows": oid["rows"],
        "vs_rows": oid["vs"] or idd["vs"], "curve": None,
    }


def _nth_weekday(year, month, weekday, n):
    d = date(year, month, 1)
    off = (weekday - d.weekday()) % 7
    return d + timedelta(days=off + (n - 1) * 7)


def snapshot_barchart():
    """สำรองชั้น 2: Barchart (feed อิสระจาก QuikStrike จริง — delayed 10-15 นาที)

    discovery: เลือก "ประเภท" ตามวันในสัปดาห์ (label จริงมีชื่อวันเสมอ เช่น
    "Friday Weekly Options") แล้วอ่าน dropdown สัปดาห์ทั้งลิสต์มาคำนวณวันหมดอายุเอง
    -- default ที่ barchart เลือกให้เชื่อไม่ได้ (มัน roll ข้าม series ที่ยังเทรดอยู่วันนี้)
    วันศุกร์แถมรหัสของวันนี้ที่สร้างตรงๆ ได้ (IG{week}{month}{yy}) เข้าไปด้วย
    ไม่มี IV/smile ใน feed นี้ -- ปล่อยว่างแล้ว inherit จาก clip เดิมของวันเดียวกัน
    """
    import html as html_mod
    jar = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    op.addheaders = [("User-Agent", UA), ("Accept", "text/html")]

    # front month ของ gold จากรอบเดือนมาตรฐาน
    today = date.today()
    front = None
    for k in range(0, 15):
        m = (today.month + k - 1) % 12 + 1
        y = today.year + (today.month + k - 1) // 12
        if m in GC_MONTHS:
            code = [c for c, mm in MONTH_CODE.items() if mm == m][0]
            if futures_expiry(f"GC{code}{y % 10}") >= today:
                front = f"GC{code}{str(y)[-2:]}"
                break
    page = op.open(f"{BC_BASE}/futures/quotes/{front}/options",
                   timeout=_budget(30)).read().decode()
    page = html_mod.unescape(page)

    # ประเภทตามวันในสัปดาห์ (เสาร์-อาทิตย์ series ถัดไปคือ daily วันจันทร์)
    want = {0: "Monday Weekly", 1: "Tuesday Weekly", 2: "Wednesday Weekly",
            3: "Thursday Weekly", 4: "Friday Weekly",
            5: "Monday Weekly", 6: "Monday Weekly"}[today.weekday()]
    wd = {"Monday Weekly": 0, "Tuesday Weekly": 1, "Wednesday Weekly": 2,
          "Thursday Weekly": 3, "Friday Weekly": 4}[want]
    kinds = re.findall(r'<option[^>]*value="(/futures/quotes/[^"]+/options/[^"]+)"[^>]*>\s*([^<]*Options[^<]*)</option>', page)
    kind_url = next((u for u, lbl in kinds if lbl.strip().startswith(want)), None)
    if kind_url:
        page = html_mod.unescape(op.open(BC_BASE + kind_url, timeout=_budget(30)).read().decode())

    # candidates จาก dropdown สัปดาห์ทั้งลิสต์ + (ศุกร์) รหัสของวันนี้แบบสร้างตรง
    cands = {}
    for code, week_n, mon_s, year_s in re.findall(
            r'<option[^>]*value="/futures/quotes/[^"]+/options/([A-Z0-9]+)"[^>]*>\s*Week (\d+): (\w{3}) (\d{4})', page):
        try:
            e = _nth_weekday(int(year_s), datetime.strptime(mon_s, "%b").month, wd, int(week_n))
            if e >= today:
                cands.setdefault(e, code)
        except ValueError:
            pass
    if today.weekday() == 4:
        mc = [c for c, mm in MONTH_CODE.items() if mm == today.month][0]
        cands.setdefault(today, f"IG{(today.day - 1) // 7 + 1}{mc}{str(today.year)[-2:]}")
    if not cands:
        raise RuntimeError("barchart: ไม่เจอ series ที่ยังไม่หมดอายุ")

    xsrf = next((c.value for c in jar if c.name == "XSRF-TOKEN"), None)
    if not xsrf:
        raise RuntimeError("barchart: ไม่ได้ XSRF cookie")

    def chain_of(sym):
        api = (f"{BC_BASE}/proxies/core-api/v1/quotes/get?symbol={sym}"
               f"&list=futures.options&fields={BC_CHAIN_FIELDS}"
               f"&groupBy=strikePrice&orderBy=strikePrice&orderDir=asc&raw=1")
        req = urllib.request.Request(api, headers={
            "User-Agent": UA, "Accept": "application/json",
            "x-xsrf-token": urllib.parse.unquote(xsrf),
            "Referer": f"{BC_BASE}/futures/quotes/{front}/options/{sym}"})
        return json.loads(op.open(req, timeout=_budget(30)).read())

    # ไล่จากใกล้หมดอายุสุด: ตัวไหน chain มีของจริงใช้ตัวนั้น (กันรหัสเดา/series ร้าง)
    series = exp = None
    id_rows, oi_rows = [], []
    for e in sorted(cands)[:3]:
        sym = cands[e]
        try:
            chain = chain_of(sym)
        except Exception:
            continue
        idr, oir = [], []
        for strike, legs in (chain.get("data") or {}).items():
            s = float(strike.replace(",", ""))
            s = int(s) if s == int(s) else s
            v = {"Call": {}, "Put": {}}
            for leg in legs:
                r = leg.get("raw", leg)
                v[r["optionType"]] = r
            pv = int(v["Put"].get("volume") or 0)
            cv = int(v["Call"].get("volume") or 0)
            po = int(v["Put"].get("openInterest") or 0)
            co = int(v["Call"].get("openInterest") or 0)
            if pv + cv > 0:
                idr.append((s, pv, cv))
            if po + co > 0:
                oir.append((s, po, co))
        if oir or idr:
            series, exp, id_rows, oi_rows = sym, e, sorted(idr), sorted(oir)
            break
    if series is None:
        raise RuntimeError("barchart: ทุก candidate chain ว่าง")

    # DTE: หมดอายุ 13:30 NY = 00:30 ไทยของวันถัดไป (หน้าร้อน)
    end = datetime(exp.year, exp.month, exp.day) + timedelta(days=1, minutes=30)
    dte = round(max((end - datetime.now()).total_seconds(), 0) / 86400, 3)

    # ราคา futures จาก API เดียวกัน
    fq = json.loads(op.open(urllib.request.Request(
        f"{BC_BASE}/proxies/core-api/v1/quotes/get?symbols={front}&fields=lastPrice&raw=1",
        headers={"User-Agent": UA, "Accept": "application/json",
                 "x-xsrf-token": urllib.parse.unquote(xsrf),
                 "Referer": f"{BC_BASE}/futures/quotes/{front}/options"}),
        timeout=_budget(20)).read())
    F = None
    try:
        F = fq["data"][0]["raw"]["lastPrice"]
    except Exception:
        pass

    return {
        "source": "barchart", "series": series, "F": F, "dte": dte,
        "iv": None, "iv_chg": None, "future_chg": None,
        "id_rows": id_rows, "oi_rows": oi_rows, "vs_rows": [], "curve": None,
    }


def inherit_same_day(snap):
    """แหล่งสำรองไม่มี IV/smile -- ยืมจาก clip เดิมได้ถ้าเป็น "วันเดียวกัน"
    (ทั้ง settle IV และ settle smile นิ่งทั้งวันโดยนิยาม จึงยืมข้ามชั่วโมงได้)"""
    if snap["iv"] is not None and snap["vs_rows"]:
        return snap
    try:
        old = open(CLIP_OUT).read().strip().split("\n")
        hdr = dict(t.split(":", 1) for t in old[0].split("|") if ":" in t)
        if hdr.get("D", "")[:10] != f"{datetime.now():%Y-%m-%d}":
            return snap
        if snap["iv"] is None and hdr.get("IV"):
            snap["iv"] = float(hdr["IV"])
            snap["iv_chg"] = float(hdr["IVCHG"]) if hdr.get("IVCHG") else None
        if not snap["vs_rows"]:
            vs_line = next((l for l in old if l.startswith("VS;")), None)
            if vs_line:
                for tok in vs_line.split(";")[1:]:
                    k, v = tok.split(":")
                    s = float(k)
                    snap["vs_rows"].append((int(s) if s == int(s) else s, float(v)))
    except Exception:
        pass
    return snap


def main():
    global _deadline
    now = datetime.now()

    # fallback chain: ไล่ตามลำดับ แหล่งไหนได้ก็ใช้ (บันทึกเหตุผลของตัวที่พลาดไว้ใน log)
    snap, fails = None, []
    for name, fn in [("quikstrike", snapshot_quikstrike),
                     ("pageth", snapshot_pageth),
                     ("barchart", snapshot_barchart)]:
        _deadline = time.monotonic() + SOURCE_BUDGET[name]
        try:
            snap = fn()
            break
        except Exception as e:
            fails.append(f"{name}: {type(e).__name__}: {str(e)[:80]}")
    if snap is None:
        raise QuikStrikeDown("ทุกแหล่งพัง -> " + " | ".join(fails))
    for f in fails:
        print(f"[{now:%Y-%m-%d %H:%M:%S}] fallback: {f}", file=sys.stderr)
    snap = inherit_same_day(snap)

    meta = {"series": snap["series"], "F": snap["F"], "dte": snap["dte"],
            "iv": snap["iv"], "future_chg": snap["future_chg"]}
    id_rows, oi_rows = snap["id_rows"], snap["oi_rows"]
    iv_chg = snap["iv_chg"]
    curve = snap["curve"]

    try:
        yahoo_open = fetch_yahoo_open()
    except Exception:
        yahoo_open = None
    sd = sd_levels(yahoo_open, meta["iv"], iv_chg)

    # ของที่เติมเข้ามาตั้งแต่ refresh รอบก่อน (นับเฉพาะ series เดียวกัน — วันใหม่เริ่มนับใหม่)
    prev = {}
    try:
        prev = json.load(open(PREV_STATE))
        if prev.get("series") != meta["series"]:
            prev = {}
    except Exception:
        prev = {}
    changes = {
        "since": prev.get("time"),
        "intraday": top_changes(id_rows, prev.get("id", {}), n=4) if prev else [],
        "oi": top_changes(oi_rows, prev.get("oi", {}), n=4) if prev else [],
    }

    header = (f"F:{meta['F'] if meta['F'] is not None else ''}"
              f"|D:{now:%Y-%m-%d %H:%M}|S:{meta['series']}"
              f"|IV:{meta['iv'] if meta['iv'] is not None else ''}"
              f"|IVCHG:{iv_chg if iv_chg is not None else ''}"
              f"|DTE:{round(meta['dte'], 3) if meta['dte'] is not None else ''}")
    vs_rows = snap["vs_rows"]
    clip = "\n".join([
        header,
        "ID;" + ";".join(f"{s}:{p}:{c}" for s, p, c in id_rows),
        "OI;" + ";".join(f"{s}:{p}:{c}" for s, p, c in oi_rows),
        "VS;" + ";".join(f"{s}:{v:.2f}" for s, v in vs_rows),
    ]) + "\n"

    data = {
        "ts": now.timestamp(),
        "system_time": f"{now:%H:%M}",
        "source": snap["source"],
        "series": meta["series"],
        "und_sym": snap.get("und_sym"),  # underlying ของ 0DTE เช่น GCV6 (มีเฉพาะ quikstrike)
        "F": meta["F"],
        "dte": round(meta["dte"], 3) if meta["dte"] is not None else None,
        "iv": meta["iv"],
        "iv_chg": iv_chg,
        "future_chg": meta["future_chg"],
        "intraday": {
            "put": sum(r[1] for r in id_rows),
            "call": sum(r[2] for r in id_rows),
            "top": top_actives(id_rows, n=4),
        },
        "oi": {
            "put": sum(r[1] for r in oi_rows),
            "call": sum(r[2] for r in oi_rows),
            "top": top_actives(oi_rows, n=4),
        },
        "sd": sd,
        "changes": changes,
    }

    new_state = json.dumps({
        "series": meta["series"], "time": f"{now:%H:%M}",
        "id": {str(s): [p, c] for s, p, c in id_rows},
        "oi": {str(s): [p, c] for s, p, c in oi_rows},
    })
    writes = [(JSON_OUT, json.dumps(data, ensure_ascii=False)),
              (CLIP_OUT, clip), (PREV_STATE, new_state)]
    if curve:
        writes.append((CURVE_OUT, json.dumps(curve)))
    for path, content in writes:
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            f.write(content)
        os.replace(tmp, path)

    curve_txt = ""
    if curve:
        c0 = curve["contracts"][0]
        curve_txt = f" curve {c0['sym']} spread_carry {curve['spread_carry']}%"
    print(f"[{now:%Y-%m-%d %H:%M:%S}] ok [{snap['source']}] {meta['series']} F={meta['F']}{curve_txt} "
          f"ID {data['intraday']['put']}/{data['intraday']['call']} "
          f"OI {data['oi']['put']}/{data['oi']['call']} "
          f"strikes {len(id_rows)}/{len(oi_rows)} clip {len(clip)}B")


if __name__ == "__main__":
    try:
        main()
    except (QuikStrikeDown, socket.timeout, urllib.error.URLError) as e:
        # ฝั่ง CME ล่ม/ช้า ไม่ใช่เรา (ping ปกติแต่ TTFB 30s+ = backend เขาเอง)
        # ไม่เขียนทับไฟล์เดิม -> widget ขึ้น STALE เองหลัง 2 ชม. / กด refresh เองได้
        print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] CME DOWN: {type(e).__name__}: {e}",
              file=sys.stderr)
        sys.exit(2)
    except Exception as e:
        print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] ERROR {type(e).__name__}: {e}",
              file=sys.stderr)
        sys.exit(1)
