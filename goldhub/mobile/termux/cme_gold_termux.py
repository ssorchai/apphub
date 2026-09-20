# -*- coding: utf-8 -*-
"""
Gold 0DTE Put/Call -> TradingView paste — Termux/Android

ก.ย. 2026: CME ถอดข้อมูลแท็บ Intraday ของ Vol2Vol ออก ตัวเก่าที่ดึงจาก Vol2Vol
ทั้งหมดจึงใช้ไม่ได้ -> ย้ายมาใช้แหล่งเดียวกับ cme_fetcher.py บน Mac:
  - Intraday + OI รายสไตรค์ + ราคา F : Barchart (core-api ภายในของหน้าเว็บ)
  - IV หลักที่ใช้คิด SD             : QuikStrike Event Vol Calculator (ช่อง vol ของจุด 0DTE)
  - เส้น smile (VS) + VolSettle      : QuikStrike Vol2Vol แท็บ Open Interest (ยังมีข้อมูล)
  - Vol Chg                           : QuikStrike Settlement Sheet (เปิดให้ดูหลัง 12:00 ไทย)
ส่วนของ QuikStrike เป็นตัวเสริม พังก็ยังได้ clip จาก Barchart (IV คำนวณเองจาก bid/ask)

HTTP ล้วน ไม่มี browser / copy ลง clipboard ของ Android ผ่าน termux-clipboard-set
format ของ clip ตรงกับ cme_fetcher.py ทุกบรรทัด (indicator ตัวเดียวกัน):
  F:...|D:...|S:...|IV:...|IVCHG:...|DTE:...|IVS:...|IVSCHG:...
  ID;strike:put:call;...
  OI;strike:put:call;...
  VS;strike:vol%;...

Usage:
    python cme_gold_termux.py
"""
import calendar
import io
import json
import math
import os
import re
import subprocess
import sys
import time
from datetime import date, datetime, timedelta, timezone

if sys.stdout is not None:
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass

import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_FILE = os.path.join(BASE_DIR, "cme_last_output.txt")

# UA แบบ desktop เสมอ -- UA มือถือทำให้ QuikStrike ส่งหน้าแบบ mobile ที่ไม่มีลิงก์ expiration
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
TIMEOUT = 30

# ---- Barchart ----
# หน้า HTML ของ barchart ติด AWS WAF challenge แต่ /proxies/core-api ไม่ติด เงื่อนไขจริง
# มีแค่ header sec-fetch-site: same-origin (ไม่ต้องมี cookie) -- ห้ามโหลดหน้า HTML
BC_BASE = "https://www.barchart.com"
BC_CHAIN_FIELDS = ("optionType,strikePrice,lastPrice,bidPrice,askPrice,"
                   "volume,openInterest,tradeTime,symbolName")
GC_MONTHS = [2, 4, 6, 8, 10, 12]
MONTH_CODE = {"F": 1, "G": 2, "H": 3, "J": 4, "K": 5, "M": 6,
              "N": 7, "Q": 8, "U": 9, "V": 10, "X": 11, "Z": 12}
# รหัส weekly series ของ barchart ต่อวันในสัปดาห์ (n = สัปดาห์ที่ของเดือน)
WEEK_CODES = {
    0: lambda n: "IY{}".format(n),          # จันทร์  IY1-IY5
    1: lambda n: "I0" + chr(64 + n),        # อังคาร  I0A-I0E
    2: lambda n: "IY{}".format(n + 5),      # พุธ    IY6-IY10
    3: lambda n: "I0" + chr(70 + n),        # พฤหัส  I0G-I0K
    4: lambda n: "IG{}".format(n),          # ศุกร์  IG1-IG5
}
WD_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]

# ---- QuikStrike (anonymous ด้วย Referer จาก cmegroup.com) ----
QS = "https://cmegroup-tools.quikstrike.net/User/QuikStrikeView.aspx?pid=40&pf=6&viewitemid="
QS_EVC_URL = QS + "IntegratedEventVolCalculator"
QS_V2V_URL = QS + "IntegratedV2VExpectedRange"
QS_SETTLE_URL = QS + "IntegratedSettlementSheet"
QS_REFERER = "https://www.cmegroup.com/"
# ตาราง #pricing-sheet: [3]=strike [7]=vol settle [9]=vol chg (20 คอลัมน์)
SHEET_STRIKE, SHEET_VOL, SHEET_VOLCHG, SHEET_NCOL = 3, 7, 9, 20

# clip ส่งเฉพาะ F ± 4σ (DTE ที่เหลือจริง) -- ช่องของ TradingView รับได้ราว 4096 ตัวอักษร
CLIP_SD = 4
CLIP_MIN_HALF = 25
CLIP_MAX_CHARS = 4000


def log(msg):
    print("[{:%H:%M:%S}] {}".format(datetime.now(), msg), flush=True)


def set_clipboard(text):
    try:
        subprocess.run(["termux-clipboard-set"], input=text.encode("utf-8"),
                       check=True, timeout=20)
        return True
    except Exception as e:
        log("! termux-clipboard-set failed ({})".format(e))
        log("  (install the Termux:API app and run: pkg install termux-api)")
        return False


# --------------------------------------------------------------------------- calendar
def _nth_weekday(year, month, weekday, n):
    d = date(year, month, 1)
    return d + timedelta(days=(weekday - d.weekday()) % 7 + (n - 1) * 7)


def us_dst(d):
    """daylight saving ของ US: อาทิตย์ที่ 2 ของ มี.ค. ถึงอาทิตย์แรกของ พ.ย."""
    return _nth_weekday(d.year, 3, 6, 2) <= d < _nth_weekday(d.year, 11, 6, 1)


def expiry_utc(d):
    """option ทองหมดอายุ 12:30 CT = 13:30 ET -> UTC (ไม่พึ่ง timezone ของมือถือ)"""
    return datetime(d.year, d.month, d.day, 17 if us_dst(d) else 18, 30, tzinfo=timezone.utc)


def session_open_utc(now_utc):
    """เวลาเปิด session Globex ล่าสุด: ทองเปิด 17:00 CT วันอาทิตย์-พฤหัส (= trade date
    ของวันถัดไป) ช่วงพัก 16:00-17:00 CT และเสาร์-อาทิตย์จะได้ session ที่เพิ่งปิด"""
    for k in range(8):
        d = now_utc.date() - timedelta(days=k)
        t = datetime(d.year, d.month, d.day, 22 if us_dst(d) else 23, tzinfo=timezone.utc)
        if t <= now_utc and d.weekday() in (6, 0, 1, 2, 3):
            return t
    return now_utc - timedelta(days=1)


def month_option_expiry(year, month):
    """monthly option ของสัญญาเดือน M หมดอายุ ~4 business day ก่อนสิ้นเดือน M-1"""
    m, y = (month - 1, year) if month > 1 else (12, year - 1)
    d = date(y, m, calendar.monthrange(y, m)[1])
    n = 0
    while True:
        if d.weekday() < 5:
            n += 1
            if n == 4:
                return d
        d -= timedelta(days=1)


def underlying_for(series_expiry):
    """weekly อ้าง GC เดือนมาตรฐานตัวใกล้สุดที่ monthly option ยังไม่หมด ณ วันหมดอายุ"""
    y, m = series_expiry.year, series_expiry.month
    for k in range(14):
        mm = (m + k - 1) % 12 + 1
        yy = y + (m + k - 1) // 12
        if mm in GC_MONTHS and month_option_expiry(yy, mm) >= series_expiry:
            code = [c for c, v in MONTH_CODE.items() if v == mm][0]
            return "GC{}{}".format(code, str(yy)[-2:])
    return None


def weekly_candidates(now_utc, horizon=9):
    """[(expiry_date, barchart_code)] ของ series ที่ยังไม่หมดอายุ เรียงใกล้->ไกล"""
    out = []
    start = now_utc.date() - timedelta(days=1)
    for k in range(horizon):
        d = start + timedelta(days=k)
        if d.weekday() >= 5 or expiry_utc(d) <= now_utc:
            continue
        out.append((d, series_codes(d)))
    return out


def series_codes(d):
    """รหัสที่เป็นไปได้ของ series วัน d: ตัวเดาตามตารางก่อน แล้วสัปดาห์ ±1
    (ตารางไม่ตายตัว: ก.ย. 26 อังคาร Week 3 = I0DU26 แต่ ต.ค. Week 1 = I0AV26
    -> ต้องยืนยันจากชื่อ series เสมอ)"""
    n = (d.day - 1) // 7 + 1
    mc = [c for c, mm in MONTH_CODE.items() if mm == d.month][0]
    return ["{}{}{}".format(WEEK_CODES[d.weekday()](k), mc, str(d.year)[-2:])
            for k in (n, n + 1, n - 1) if 1 <= k <= 6]


# --------------------------------------------------------------------------- Barchart
def bc_api(s, path_qs):
    r = s.get(BC_BASE + "/proxies/core-api/v1/" + path_qs, timeout=TIMEOUT, headers={
        "Accept": "application/json", "sec-fetch-site": "same-origin",
        "sec-fetch-mode": "cors", "sec-fetch-dest": "empty",
        "Referer": BC_BASE + "/futures/quotes/GC*0/options"})
    r.raise_for_status()
    return r.json()


def parse_chain(chain):
    legs = {}
    for strike, sides in (chain.get("data") or {}).items():
        k = float(strike.replace(",", ""))
        k = int(k) if k == int(k) else k
        v = {"Call": {}, "Put": {}}
        for leg in sides:
            r = leg.get("raw", leg)
            v[r.get("optionType", "?")] = r
        legs[k] = v
    return legs


def _name_expiry(name):
    """'Gold Thursday Week 2 Options Sep '26 ...' -> วันหมดอายุจริงของ series / None"""
    m = re.match(r"Gold (Monday|Tuesday|Wednesday|Thursday|Friday) "
                 r"Week (\d) Options ([A-Z][a-z]{2}) '(\d\d)", name or "")
    if not m:
        return None
    return _nth_weekday(2000 + int(m.group(4)), datetime.strptime(m.group(3), "%b").month,
                        WD_NAMES.index(m.group(1)), int(m.group(2)))


def series_name_expiry(legs):
    for v in legs.values():
        for side in ("Call", "Put"):
            got = _name_expiry(v[side].get("symbolName"))
            if got:
                return got
    return None


def probe_series_expiry(s, sym):
    """ยิงเบาๆ (1 leg) เอาแค่ชื่อ series -> วันหมดอายุ / None"""
    try:
        d = bc_api(s, "quotes/get?symbol={}&list=futures.options&fields=symbolName"
                      "&limit=1&raw=1".format(sym))
    except requests.RequestException:
        return None
    for row in d.get("data") or []:
        got = _name_expiry(row.get("raw", row).get("symbolName"))
        if got:
            return got
    return None


def barchart_snapshot(s):
    now_utc = datetime.now(timezone.utc)

    def fetch_chain(sym):
        try:
            return parse_chain(bc_api(s, "quotes/get?symbol={}&list=futures.options&fields={}"
                                         "&groupBy=strikePrice&orderBy=strikePrice&orderDir=asc"
                                         "&raw=1".format(sym, BC_CHAIN_FIELDS)))
        except requests.RequestException:
            return {}

    # ต้องได้ series ที่ชื่อบอกวันหมดอายุตรงกับวันนั้น -- รหัสเดาผิดได้ ลองสัปดาห์ ±1
    series = expiry = None
    legs = {}
    tried = []
    for exp_guess, syms in weekly_candidates(now_utc)[:5]:
        tried.append(syms[0])
        got = fetch_chain(syms[0])
        named = series_name_expiry(got) if got else None
        if got and (named is None or named == exp_guess):
            series, expiry, legs = syms[0], exp_guess, got
            break
        for alt in syms[1:]:
            if probe_series_expiry(s, alt) == exp_guess:
                got = fetch_chain(alt)
                if got:
                    series, expiry, legs = alt, exp_guess, got
                break
        if series:
            break
    if series is None:
        raise RuntimeError("barchart: ทุก candidate ว่าง ({})".format(",".join(tried)))

    dte = round(max((expiry_utc(expiry) - now_utc).total_seconds(), 0) / 86400, 3)
    und = underlying_for(expiry)
    fq = bc_api(s, "quotes/get?symbols={}&fields=symbol,lastPrice&raw=1".format(und))
    F = None
    for row in fq.get("data") or []:
        r = row.get("raw", row)
        if r.get("symbol") == und and r.get("lastPrice"):
            F = float(r["lastPrice"])

    # ตัดสไตรค์หลุดโลก (chain เคยมีแถว strike 10,000 ทั้งที่สไตรค์จริงไกลสุด 6,000)
    if F:
        legs = {k: v for k, v in legs.items() if 0.5 * F <= k <= 1.5 * F}
    # Intraday = volume ของ session นี้เท่านั้น: สไตรค์ที่ยังไม่มีใครเทรดตั้งแต่เปิด session
    # barchart ยังโชว์ volume ของ session ก่อนค้างไว้ (11 ก.ย. 26 ตอน 09:50 ไทย 3,821 จาก
    # 4,553 สัญญาเป็นของเมื่อวาน) -> นับเฉพาะ leg ที่ last trade >= เวลาเปิด session
    sess = session_open_utc(now_utc).timestamp()
    vol = lambda r: int(r.get("volume") or 0) if (r.get("tradeTime") or 0) >= sess else 0
    id_rows, oi_rows = [], []
    for k, v in sorted(legs.items()):
        pv, cv = vol(v["Put"]), vol(v["Call"])
        po, co = int(v["Put"].get("openInterest") or 0), int(v["Call"].get("openInterest") or 0)
        if pv + cv:
            id_rows.append((k, pv, cv))
        if po + co:
            oi_rows.append((k, po, co))
    return {"series": series, "expiry": expiry, "und": und, "F": F, "dte": dte,
            "legs": legs, "id_rows": id_rows, "oi_rows": oi_rows}


# --------------------------------------------------------------------------- IV สำรอง
def _ncdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def b76(F, K, t, v, call):
    if v <= 0 or t <= 0:
        return max(F - K, 0.0) if call else max(K - F, 0.0)
    sd = v * math.sqrt(t)
    d1 = (math.log(F / K) + 0.5 * sd * sd) / sd
    d2 = d1 - sd
    return F * _ncdf(d1) - K * _ncdf(d2) if call else K * _ncdf(-d2) - F * _ncdf(-d1)


def b76_iv(F, K, t, price, call):
    intr = max(F - K, 0.0) if call else max(K - F, 0.0)
    if t <= 0 or price <= intr + 1e-9 or b76(F, K, t, 5.0, call) < price:
        return None
    lo, hi = 1e-4, 5.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if b76(F, K, t, mid, call) < price:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2 * 100.0


def iv_at(rows, x):
    if not rows:
        return None
    if x is None or x <= rows[0][0]:
        return rows[0][1]
    if x >= rows[-1][0]:
        return rows[-1][1]
    for (k0, v0), (k1, v1) in zip(rows, rows[1:]):
        if k0 <= x <= k1:
            return v0 + (v1 - v0) * (x - k0) / (k1 - k0)
    return None


def computed_iv_rows(legs, F, dte):
    """smile จาก mid ของ bid/ask ฝั่ง OTM (barchart ไม่ให้ IV ของ series ในวันหมดอายุ)"""
    if not F or not dte:
        return []
    rows = []
    for k, v in sorted(legs.items()):
        call = k > F
        r = v["Call"] if call else v["Put"]
        bid, ask = r.get("bidPrice"), r.get("askPrice")
        if not bid or not ask or float(ask) < float(bid):
            continue
        iv = b76_iv(F, float(k), dte / 365.0, (float(bid) + float(ask)) / 2, call)
        if iv is not None and 0.5 < iv < 300:
            rows.append((k, iv))
    atm = iv_at(rows, F)
    return [(k, v) for k, v in rows if not atm or v <= atm * 2.5]


# --------------------------------------------------------------------------- QuikStrike
# ลดความเสี่ยงโดน block (ตรงกับ cme_fetcher.py บน Mac):
#  - ใช้ session เดียวต่อรอบ (หน้าแรกเปิด session ใช้ 4 request เพราะ redirect หน้าถัดไป 1)
#  - Vol2Vol / Settlement Sheet เป็นค่า settle -> cache ใน QS_STATE (อยู่ในโฟลเดอร์โปรแกรม
#    รอดข้าม restart มือถือ) ดึงใหม่เมื่อข้ามวัน CME หรือเก่าเกิน 4 ชม.
#  - ตัวเบรก: QuikStrike ตอบ 403/429/หน้า login/หน้าตรวจบอท -> หยุดยิง 12 ชม.
#    (มือถือไม่นับเน็ตหลุดเป็นสัญญาณ เพราะเน็ตมือถือหลุดบ่อยเป็นปกติ)
QS_STATE = os.path.join(BASE_DIR, "qs_state.json")
QS_CACHE_MAX_AGE = 4 * 3600
QS_PAUSE_BLOCK = 12 * 3600
QS_PAUSE_OUTAGE = 2 * 3600
BLOCK_MARKERS = ("captcha", "access denied", "request rejected", "request unsuccessful",
                 "awswaf", "just a moment", "unusual traffic")


class QSBlocked(Exception):
    def __init__(self, msg, pause):
        super().__init__(msg)
        self.pause = pause


class SettleEmbargo(RuntimeError):
    pass


def qs_check(html, url=""):
    if "/Account/Login" in url:
        raise QSBlocked("เด้งไปหน้า login", QS_PAUSE_BLOCK)
    head = html[:5000].lower()
    if any(k in head for k in BLOCK_MARKERS) and "pricing-sheet" not in head:
        raise QSBlocked("หน้าตรวจบอท/ปฏิเสธ", QS_PAUSE_BLOCK)
    if "/Error/ErrorPage.aspx" in url or "QuikStrike Error" in html[:3000]:
        if "unknown+view" in url or "unknown view" in html[:3000]:
            raise RuntimeError("QuikStrike error page (unknown view)")
        raise QSBlocked("error page", QS_PAUSE_OUTAGE)


def qs_status(r):
    if r.status_code in (403, 429):
        raise QSBlocked("HTTP {}".format(r.status_code), QS_PAUSE_BLOCK)
    if r.status_code >= 500:
        raise QSBlocked("HTTP {}".format(r.status_code), QS_PAUSE_OUTAGE)


def qs_selects(html):
    out = {}
    for m in re.finditer(r'<select[^>]*name="([^"]+)"[^>]*>(.*?)</select>', html, re.S):
        opts = re.findall(r'<option([^>]*)value="([^"]*)"', m.group(2))
        out[m.group(1)] = next((v for a, v in opts if "selected" in a), opts[0][1] if opts else "")
    return out


class QSClient:
    """session เดียวต่อรอบ: แนบ insid/qsid ที่ได้จากหน้าแรกไปกับหน้าถัดไป เหมือนกดเมนูใน browser"""

    def __init__(self, s):
        self.s, self.inst, self.ref = s, None, QS_REFERER

    def get(self, view_url):
        url = view_url + ("&" + self.inst if self.inst else "")
        r = self.s.get(url, timeout=TIMEOUT, headers={"Referer": self.ref})
        qs_status(r)
        qs_check(r.text, r.url)
        m = re.search(r"insid=\d+&qsid=[0-9a-f-]+", r.url)
        if m:
            self.inst = m.group(0)
        self.ref = r.url
        return r.url, r.text

    def postback(self, url, html, target, extra=None):
        """จำลอง __doPostBack ของ WebForms (ต้องส่งค่า <select> ทุกตัวกลับด้วย ไม่งั้นรีเซ็ต)"""
        def val(n):
            m = re.search(r'id="{}" value="([^"]*)"'.format(n), html)
            return m.group(1) if m else ""
        fields = qs_selects(html)
        fields.update({"__EVENTTARGET": target, "__EVENTARGUMENT": "",
                       "__VIEWSTATE": val("__VIEWSTATE"),
                       "__VIEWSTATEGENERATOR": val("__VIEWSTATEGENERATOR"),
                       "__EVENTVALIDATION": val("__EVENTVALIDATION")})
        fields.update(extra or {})
        r = self.s.post(url, data=fields, timeout=TIMEOUT, headers={"Referer": url})
        qs_status(r)
        qs_check(r.text, r.url)
        return r.text


def qs_open_expiry(qs, view_url, expiry, extra_fn=None):
    """เปิด view แล้วเลือก expiration ตามวันหมดอายุ (จาก title ของ anchor) -> (url, html, sym)
    จับด้วยวันหมดอายุ เพราะ barchart กับ QuikStrike ใช้คนละระบบรหัส (IG2U26 vs OG2U6)"""
    url, page = qs.get(view_url)
    want = "{}/{}/{}".format(expiry.month, expiry.day, expiry.year)
    for m in re.finditer(r'title="([^"]*Option Expiration:[^"]*)"[^>]*?'
                         r'href="javascript:__doPostBack\(&#39;([^&]*\$lbExpiration)&#39;', page):
        if re.search(r"Option Expiration:\s*" + re.escape(want) + r"\b", m.group(1)):
            sm = re.search(r"Option Symbol:\s*([A-Z0-9]+)", m.group(1))
            html = qs.postback(url, page, m.group(2), extra_fn(page) if extra_fn else None)
            return url, html, sm.group(1) if sm else None
    raise RuntimeError("ไม่เจอ expiration {} ใน selector".format(want))


def chart_settings(html, control):
    i = html.find("$create(" + control)
    if i < 0:
        return None
    m = re.search(r'"JSONSettings":"((?:[^"\\]|\\.)*)"', html[i:])
    return json.loads(m.group(1).encode().decode("unicode_escape")) if m else None


def event_vol(qs, expiry):
    """ช่อง vol ของจุด 0DTE ใน Event Vol Calculator (ห้ามใช้ forwardVol -- อันนั้นคือ
    ช่วงหลัง expiry นี้ไปถึงตัวถัดไป ไม่ใช่วันนี้)"""
    _, page = qs.get(QS_EVC_URL)
    d = chart_settings(page, "UserControlsV2.EventVol.Calculator.Chart")
    if not d:
        raise RuntimeError("EventVol: ไม่เจอ payload")
    for srs in d.get("Series") or []:
        if srs.get("name") != "Volatility":
            continue
        for p in srs.get("data") or []:
            if datetime.strptime(p.get("expires", ""), "%m/%d/%Y").date() == expiry:
                return float(str(p["vol"]).replace("%", "").strip()), p.get("symbol")
    raise RuntimeError("EventVol: ไม่มีจุดของ {}".format(expiry))


def v2v_smile(qs, expiry):
    """เส้น Vol Settle + ATMVol จาก Vol2Vol แท็บ Open Interest (vol เป็นเศษส่วน)"""
    url, html, sym = qs_open_expiry(qs, QS_V2V_URL, expiry)
    tab = re.search(r"__doPostBack\(&#39;([^&]*\$lbOI)&#39;", html)
    if not tab:
        raise RuntimeError("Vol2Vol: ไม่เจอแท็บ OI")
    d = chart_settings(qs.postback(url, html, tab.group(1)), "UserControlsV2.QuikOptionsV")
    if not d:
        raise RuntimeError("Vol2Vol: แท็บ OI ไม่มี payload")
    if sym and not (d.get("Title") or "").startswith(sym):
        raise RuntimeError("Vol2Vol: ได้ series {!r}".format(d.get("Title")))
    vs = []
    for p in (d.get("VolSettle") or {}).get("data") or []:
        if p.get("x") and p.get("y"):
            k = float(p["x"])
            vs.append((int(k) if k == int(k) else k, round(float(p["y"]) * 100, 2)))
    if not vs:
        raise RuntimeError("Vol2Vol: VolSettle ว่าง")
    atm = d.get("ATMVol")
    return sorted(vs), (round(atm * 100, 2) if atm else None), sym


def settle_vol_chg_rows(qs, expiry):
    """[(strike, vol chg)] จาก Settlement Sheet (ปิดให้ดูจนถึง 00:00 CT = 12:00 ไทย)"""
    all_strikes = lambda h: {n: "-1" for n in qs_selects(h) if n.endswith("ddlStrikes")}
    _, html, _ = qs_open_expiry(qs, QS_SETTLE_URL, expiry, all_strikes)
    if "settlements are not available for viewing" in html:
        raise SettleEmbargo("Settlement Sheet ยังปิด (เปิดหลัง 12:00 ไทย)")
    m = re.search(r'id="pricing-sheet"(.*?)</table>', html, re.S)
    if not m:
        raise RuntimeError("ไม่เจอตาราง #pricing-sheet")
    chg = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", m.group(1), re.S):
        tds = [re.sub("<[^>]+>", "", td).replace("&nbsp;", "").replace(",", "").strip()
               for td in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
        if len(tds) < SHEET_NCOL:
            continue
        try:
            chg.append((float(tds[SHEET_STRIKE]), float(tds[SHEET_VOLCHG].replace("%", ""))))
        except ValueError:
            continue
    return sorted(chg)


def qs_state_load():
    try:
        return json.load(open(QS_STATE, encoding="utf-8"))
    except Exception:
        return {}


def qs_state_save(st):
    tmp = QS_STATE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f)
    os.replace(tmp, QS_STATE)


def ct_day(now_utc):
    """วันที่ตามเวลา Chicago -- QuikStrike เปลี่ยนชุด settlement ตามวันของ CME"""
    return (now_utc - timedelta(hours=5 if us_dst(now_utc.date()) else 6)).date()


def next_ct_midnight(now_utc):
    d = ct_day(now_utc) + timedelta(days=1)
    return datetime(d.year, d.month, d.day, 5 if us_dst(d) else 6, tzinfo=timezone.utc)


def quikstrike(s, snap):
    """ดึง/อ่าน cache ค่าจาก QuikStrike -> dict(iv_event, v2v, chg_rows, qs_sym, paused)"""
    now_utc = datetime.now(timezone.utc)
    now_ts = now_utc.timestamp()
    st = qs_state_load()
    cache = st.get("cache") or {}
    if cache.get("expiry") != snap["expiry"].isoformat():
        cache = {"expiry": snap["expiry"].isoformat()}
    day = ct_day(now_utc).isoformat()
    fresh = lambda e: bool(e) and e.get("ct_day") == day and now_ts - e.get("ts", 0) < QS_CACHE_MAX_AGE
    out = {"iv_event": None, "qs_sym": cache.get("qs_sym"), "paused": None}

    if now_ts < st.get("paused_until", 0):
        out["paused"] = st["paused_until"]
        log("QuikStrike พักอยู่ถึง {:%d %b %H:%M} ({}) -- ใช้ cache".format(
            datetime.fromtimestamp(st["paused_until"]), st.get("pause_reason")))
    else:
        qs = QSClient(s)
        try:
            try:
                out["iv_event"], sym = event_vol(qs, snap["expiry"])
                out["qs_sym"] = out["qs_sym"] or sym
                log("event vol 0DTE {}".format(out["iv_event"]))
            except (QSBlocked, requests.RequestException):
                raise
            except Exception as e:
                log("event vol ข้าม ({})".format(e))
            if not fresh(cache.get("v2v")):
                try:
                    vs, atm, sym = v2v_smile(qs, snap["expiry"])
                    cache["v2v"] = {"ct_day": day, "ts": now_ts, "vs": vs, "atm": atm}
                    out["qs_sym"] = out["qs_sym"] or sym
                    log("vol2vol {} VolSettle {} strikes, ATM {}".format(sym, len(vs), atm))
                except (QSBlocked, requests.RequestException):
                    raise
                except Exception as e:
                    log("vol2vol ข้าม ({})".format(e))
            if not fresh(cache.get("settle")) and now_ts >= cache.get("settle_next_try", 0):
                try:
                    cache["settle"] = {"ct_day": day, "ts": now_ts,
                                       "chg": settle_vol_chg_rows(qs, snap["expiry"])}
                    log("settlement sheet ok (Vol Chg)")
                except SettleEmbargo as e:
                    cache["settle_next_try"] = next_ct_midnight(now_utc).timestamp()
                    log("vol chg ข้าม ({})".format(e))
                except (QSBlocked, requests.RequestException):
                    raise
                except Exception as e:
                    log("vol chg ข้าม ({})".format(e))
        except QSBlocked as e:
            st["paused_until"], st["pause_reason"] = now_ts + e.pause, str(e)
            out["paused"] = st["paused_until"]
            log("! QuikStrike {} -> หยุดยิง {} ชม.".format(e, e.pause // 3600))
        except requests.RequestException as e:
            log("QuikStrike ต่อไม่ได้ ({}) -- ข้ามรอบนี้".format(type(e).__name__))
    if out["qs_sym"]:
        cache["qs_sym"] = out["qs_sym"]
    st["cache"] = cache
    try:
        qs_state_save(st)
    except OSError as e:
        log("! บันทึก cache ไม่ได้ ({})".format(e))
    out["v2v"] = cache.get("v2v")
    out["chg_rows"] = [tuple(r) for r in (cache.get("settle") or {}).get("chg") or []]
    return out


# --------------------------------------------------------------------------- clip
def fmt_strike(x):
    return str(int(x)) if float(x).is_integer() else "{:g}".format(x)


def build_clip(snap, k):
    F, iv, dte = snap["F"], snap["iv"], snap["dte"]
    win = None
    if F and iv and dte is not None:
        half = max(F * iv / 100.0 * math.sqrt(max(dte, 0) / 365.0) * k, CLIP_MIN_HALF)
        win = (F - half, F + half)
    inwin = (lambda x: win[0] <= x <= win[1]) if win else (lambda x: True)
    blank = lambda v: "" if v is None else v
    header = "F:{}|D:{:%Y-%m-%d %H:%M}|S:{}|IV:{}|IVCHG:{}|DTE:{}|IVS:{}|IVSCHG:{}".format(
        blank(F), datetime.now(), snap["series"], blank(iv), blank(snap["iv_chg"]),
        blank(dte), blank(snap["iv_settle"]), blank(snap["iv_settle_chg"]))
    return "\n".join([
        header,
        "ID;" + ";".join("{}:{}:{}".format(fmt_strike(s), p, c) for s, p, c in snap["id_rows"] if inwin(s)),
        "OI;" + ";".join("{}:{}:{}".format(fmt_strike(s), p, c) for s, p, c in snap["oi_rows"] if inwin(s)),
        "VS;" + ";".join("{}:{:.2f}".format(fmt_strike(s), v) for s, v in snap["vs_rows"] if inwin(s)),
    ])


# --------------------------------------------------------------------------- main
def fetch():
    s = requests.Session()
    s.headers["User-Agent"] = UA
    log("barchart: Intraday + OI ...")
    snap = barchart_snapshot(s)
    log("series {} (exp {}, on {}) F={} DTE {}".format(
        snap["series"], snap["expiry"], snap["und"], snap["F"], snap["dte"]))

    snap.update(iv=None, iv_src=None, iv_chg=None, iv_settle=None, iv_settle_chg=None,
                vs_rows=[], smile_src=None, qs_sym=None)
    q = quikstrike(s, snap)
    snap["qs_sym"] = q["qs_sym"]
    if q["iv_event"] is not None:
        snap["iv"], snap["iv_src"] = q["iv_event"], "event"
    atm_v2v = None
    if q["v2v"]:
        snap["vs_rows"] = [tuple(r) for r in q["v2v"]["vs"]]
        atm_v2v = q["v2v"]["atm"]
        snap["iv_settle"], snap["smile_src"] = atm_v2v, "vol2vol"
    if q["chg_rows"]:
        v = iv_at(q["chg_rows"], snap["F"])
        snap["iv_settle_chg"] = round(v, 2) if v is not None else None
    snap["qs_paused"] = q["paused"]

    if not snap["vs_rows"]:
        snap["vs_rows"] = [(k, round(v, 2)) for k, v in
                           computed_iv_rows(snap["legs"], snap["F"], snap["dte"])]
        snap["smile_src"] = "live bid/ask"
    if snap["iv"] is None and atm_v2v is not None:
        snap["iv"], snap["iv_src"] = atm_v2v, "vol2vol"
    if snap["iv"] is None:
        v = iv_at(snap["vs_rows"], snap["F"])
        snap["iv"], snap["iv_src"] = (round(v, 2) if v else None), snap["smile_src"]

    k = CLIP_SD
    clip = build_clip(snap, k)
    while len(clip) > CLIP_MAX_CHARS and k > 1:
        k -= 0.5
        clip = build_clip(snap, k)
    sd1 = (snap["F"] * snap["iv"] / 100 * math.sqrt(0.6 / 365)) if snap["F"] and snap["iv"] else None
    summary = [
        "Gold {} ({})  exp {}  DTE {:.2f}".format(snap["series"], snap["qs_sym"] or "-",
                                                  snap["expiry"], snap["dte"]),
        "Future {} ({})   IV {} [{}]".format(snap["F"], snap["und"], snap["iv"], snap["iv_src"]),
        "VolSettle {}{}   smile: {}".format(
            snap["iv_settle"] if snap["iv_settle"] is not None else "-",
            " ({:+})".format(snap["iv_settle_chg"]) if snap["iv_settle_chg"] is not None else "",
            snap["smile_src"]),
        "Intraday P {} / C {}   OI P {} / C {}".format(
            sum(r[1] for r in snap["id_rows"]), sum(r[2] for r in snap["id_rows"]),
            sum(r[1] for r in snap["oi_rows"]), sum(r[2] for r in snap["oi_rows"])),
        "clip {} chars (±{}σ){}".format(len(clip), k,
                                         "   1SD@0.6DTE ±{:.1f}".format(sd1) if sd1 else ""),
    ]
    if snap["qs_paused"]:
        summary.append("QuikStrike พักอยู่ถึง {:%d %b %H:%M} (ตัวเบรก) -- ค่า vol มาจาก cache/ค่าสด".format(
            datetime.fromtimestamp(snap["qs_paused"])))
    return clip, "\n".join(summary)


def main():
    t0 = time.time()
    try:
        clip, summary = fetch()
    except Exception as e:
        log("ERROR: {}: {}".format(type(e).__name__, e))
        sys.exit(1)
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        f.write(clip + "\n")
    ok = set_clipboard(clip)
    print()
    print(summary)
    print("(took {:.1f}s)".format(time.time() - t0))
    print()
    if ok:
        print("=> P/C data copied to clipboard — paste into 'Paste P/C Data' in TradingView")
    else:
        print("----- P/C PASTE (copy manually) -----")
        print(clip)


if __name__ == "__main__":
    main()
