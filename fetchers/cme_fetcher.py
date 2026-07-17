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


# เพดานเวลารวมทั้งรอบ: urllib นับ timeout ต่อ socket ไม่ใช่ต่อ request -- ตอนเซิร์ฟช้า
# redirect หลาย hop x retry ทบกันได้ถึง 4 นาที (วัดจริง 17 ก.ค. 2026) cron รายชั่วโมง
# ไม่ควรค้างขนาดนั้น หมดเวลาก็ยอมแพ้ไปรอบหน้า ข้อมูลเดิมยังอยู่
# หมายเหตุ: กันได้แค่ "ก่อนยิง request ถัดไป" -- ตัวที่ยิงค้างอยู่ยังกินได้อีก
# (per-socket timeout x จำนวน redirect hop) จริงจึงจบราว MAX_RUNTIME + ~40s
MAX_RUNTIME = 100
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
    try:
        best = nearest_expiration(html)
        if best:
            html = _postback(op, final_url, html, best[0])
    except Exception:
        pass

    intraday = extract_payload(html)
    oi = extract_payload(_postback(op, final_url, html, OI_TARGET))
    return intraday, oi, curve


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


def main():
    global _deadline
    _deadline = time.monotonic() + MAX_RUNTIME
    now = datetime.now()
    intraday, oi, curve = fetch_both_tabs()
    meta = meta_of(oi)
    id_rows, oi_rows = strike_rows(intraday), strike_rows(oi)

    # หา Vol Chg จาก subtitle ฝั่งไหนก็ได้ (ค่าเดียวกัน)
    sub = re.sub("<[^>]+>", "", oi.get("Subtitle", "")).replace("\xa0", " ")
    mv = re.search(r"Vol Chg:\s*(-?[\d.]+)", sub)
    iv_chg = float(mv.group(1)) if mv else None

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

    header = (f"F:{meta['F']}|D:{now:%Y-%m-%d %H:%M}|S:{meta['series']}"
              f"|IV:{meta['iv']}|IVCHG:{iv_chg if iv_chg is not None else ''}"
              f"|DTE:{round(meta['dte'], 3) if meta['dte'] is not None else ''}")
    # smile: settle vol ทุก strike ในชาร์ต (รวม strike ที่ไม่มี volume — เส้นจะได้เนียนเต็มช่วง)
    vs = series_points(oi, "VolSettle")
    vs_rows = [(int(k) if k == int(k) else k, v * 100) for k, v in sorted(vs.items()) if v and v > 0]
    clip = "\n".join([
        header,
        "ID;" + ";".join(f"{s}:{p}:{c}" for s, p, c in id_rows),
        "OI;" + ";".join(f"{s}:{p}:{c}" for s, p, c in oi_rows),
        "VS;" + ";".join(f"{s}:{v:.2f}" for s, v in vs_rows),
    ]) + "\n"

    data = {
        "ts": now.timestamp(),
        "system_time": f"{now:%H:%M}",
        "series": meta["series"],
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
    print(f"[{now:%Y-%m-%d %H:%M:%S}] ok {meta['series']} F={meta['F']}{curve_txt} "
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
