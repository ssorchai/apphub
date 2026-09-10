#!/usr/bin/env python3
"""
Gold 0DTE Put/Call fetcher -- Barchart ล้วน (Intraday + OI + IV + curve)

ประวัติ: เดิมดึงจาก CME QuikStrike Vol2Vol แต่ ก.ย. 2026 CME ถอด intraday ออก
(หน้า Vol2Vol เหลือแต่โครง ไม่มี $create payload แล้ว) และใส่ bot detection โหด
-> ย้ายมา Barchart ทั้งหมด (feed CME ที่เขา license เอง, delayed 10-15 นาที
ซึ่งพอๆ กับรอบ re-mark ของ QuikStrike เดิมอยู่แล้ว)

⚠️ barchart ใส่ AWS WAF JS challenge บน "หน้า HTML" ทุกหน้า (ก.ย. 2026) แต่ path
/proxies/core-api ไม่โดน -- เงื่อนไขจริงของ API มีแค่ header `sec-fetch-site:
same-origin` (พิสูจน์ 10 ก.ย.: ไม่ต้องมี cookie/XSRF/WAF-token เลย) จึง**ห้าม**
โหลดหน้า HTML -- ทุกอย่างรวม series discovery ทำผ่าน API:

  - discovery: สร้างรหัส series จากตาราง WEEK_CODES (จันทร์ IY1-5 / อังคาร I0A-E /
    พุธ IY6-10 / พฤหัส I0G-K / ศุกร์ IG1-5 + เดือน+ปี) แล้วยิง chain ไล่จากวันใกล้สุด
    ตัวจริงยืนยันจาก `symbolName` ใน response ("Gold Thursday Week 2 Options Sep '26")
    -> วันหมดอายุคำนวณจากชื่อ ไม่ใช่จากรหัส / series ที่หมดอายุแล้วโดนล้าง (chain ว่าง)
  - chain เดียวได้ครบ: volume/OI/lastPrice/optImpliedVolatility ต่อ strike
    (ชื่อ field IV แกะจาก class ตารางหน้า volatility-greeks -- 'impliedVolatility'
    เฉยๆ คืน null / หน่วยเป็น % อยู่แล้ว)
  - F + curve: quotes ของ underlying + futures 3 เดือนใกล้สุดในคอลเดียว

IV วัน 0DTE: barchart คืน optImpliedVolatility=0 ทั้ง chain "ในวันหมดอายุของ series
นั้นเอง" (หน้าเว็บจริงก็ว่าง -- ข้อจำกัดฝั่งเขา) -> คำนวณเองจาก premium (Black-76 +
bisection, t=dte/365 day-count เดียวกับสูตร SD) เฉพาะฝั่ง OTM ที่มี volume วันนี้
/ ไม่ได้อีกค่อย inherit จาก clip เดิมของวันเดียวกัน
(QuikStrike PricingSheet ของเพื่อนยังหา URL จริงไม่เจอ ได้เมื่อไหร่ค่อยต่อเพิ่ม)

Output (atomic เขียน .tmp แล้ว os.replace เหมือน fetcher ตัวอื่น):
  /tmp/cme_putcall.json      ให้ cme-putcall.jsx (Übersicht) อ่านแสดงผล
  /tmp/cme_putcall_clip.txt  string สำหรับ paste ลงช่อง P/C ของ oi_block.pine:
      F:4405.6|D:2026-09-10 16:55|S:I0HU26|IV:23.57|IVCHG:|DTE:0.419
      ID;4090:12:5;4100:44:10;...        (strike:put:call เฉพาะที่มีของ)
      OI;4000:821:66;...
      VS;3900:31.87;3925:30.12;...       (strike:vol% ใช้วาด smile -- เป็น IV
                                          "ปัจจุบัน" delayed ไม่ใช่ settle แบบเดิม)
  /tmp/cme_curve.json        futures curve ให้ gold_fetcher ทำ Theory Diff

cron รายชั่วโมง:
  7 * * * * /usr/bin/python3 /Users/sorachai/src/my-cronjob/cme_fetcher.py >> /tmp/cme_cron.log 2>&1
ทดสอบ: python3 cme_fetcher.py  (รันครั้งเดียวเสมอ)
"""

import calendar
import json
import math
import os
import re
import socket
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

JSON_OUT = "/tmp/cme_putcall.json"
CLIP_OUT = "/tmp/cme_putcall_clip.txt"
CURVE_OUT = "/tmp/cme_curve.json"
CHART_OUT = "/tmp/cme_chart.html"   # กราฟหน้าตาแบบ CME Vol2Vol เปิดค้างใน browser ได้

# SD จากราคาเปิดวัน (Yahoo แม่นกว่า investing — pattern เดียวกับ gold_fetcher.py)
# DTE fix 0.6 = ตัดช่วงเอเชียเช้าทิ้ง / vol = IV - IVCHG เมื่อมี chg (ยุค barchart
# ปกติไม่มี chg -> ใช้ IV ปัจจุบันตรงๆ)
YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/GC=F?interval=1d&range=1d"
SD_DTE = 0.6

# ⚠️ Yahoo ต้องใช้ UA "สั้น" ตัวนี้เท่านั้น ห้ามใช้ UA ตัวบน (ที่มี Chrome/126...)
# — Yahoo ตอบ 429 ให้ UA ตัวนั้นแบบ deterministic ตัวแปรคือ UA string ล้วนๆ ไม่ใช่ TLS
YAHOO_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

# ต้องเป็น path เต็ม: curl เป็น keg-only และ cron เห็นแค่ /usr/bin/curl ซึ่งโดน 403
# (เครื่องนี้ Homebrew prefix = /usr/local แม้เป็น arm64)
CURL_BIN = "/usr/local/opt/curl/bin/curl"

# state รอบก่อน สำหรับหา "ของที่เติมเข้ามา" ระหว่าง refresh (แบบวงเล็บ +28 ของบอท telegram)
PREV_STATE = "/tmp/cme_putcall_prev.json"

BC_BASE = "https://www.barchart.com"
BC_CHAIN_FIELDS = ("optionType,strikePrice,lastPrice,bidPrice,askPrice,"
                   "volume,openInterest,optImpliedVolatility,symbolName")
# เดือนของ gold futures มาตรฐาน (G J M Q V Z) ใช้หา underlying + curve
GC_MONTHS = [2, 4, 6, 8, 10, 12]
CURVE_N = 3
MONTH_CODE = {"F": 1, "G": 2, "H": 3, "J": 4, "K": 5, "M": 6,
              "N": 7, "Q": 8, "U": 9, "V": 10, "X": 11, "Z": 12}

# รหัส weekly series ต่อวันในสัปดาห์ (n = สัปดาห์ที่ของเดือน 1-5)
# ยืนยันกับ API 10 ก.ย. 26: IY3U26="Monday Week 3", IY8U26="Wednesday Week 3",
# I0HU26="Thursday Week 2", IG2U26="Friday Week 2" / I0B (Tue w2) หมดอายุแล้ว=ว่าง
WEEK_CODES = {
    0: lambda n: "IY{}".format(n),          # จันทร์  IY1-IY5
    1: lambda n: "I0" + chr(64 + n),        # อังคาร  I0A-I0E
    2: lambda n: "IY{}".format(n + 5),      # พุธ    IY6-IY10
    3: lambda n: "I0" + chr(70 + n),        # พฤหัส  I0G-I0K
    4: lambda n: "IG{}".format(n),          # ศุกร์  IG1-IG5
}
WD_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]

# งบเวลารวม (แหล่งเดียวแล้ว) -- urllib นับ timeout ต่อ socket ไม่ใช่ต่อ request
MAX_RUNTIME = 90
_deadline = None


class SourceDown(Exception):
    """ฝั่งแหล่งข้อมูลมีปัญหา ไม่ใช่โค้ดเรา -- retry ในรอบนี้ไม่ช่วย"""


def _budget(cap=30):
    """เวลาที่เหลือในงบ (วินาที) -- ใช้เป็น timeout ของ request ถัดไป"""
    if _deadline is None:
        return cap
    left = _deadline - time.monotonic()
    if left <= 1:
        raise SourceDown("เกินงบเวลา (เซิร์ฟช้าผิดปกติ)")
    return min(cap, left)


# --------------------------------------------------------------------------- #
# ปฏิทินสัญญา
# --------------------------------------------------------------------------- #
def _nth_weekday(year, month, weekday, n):
    d = date(year, month, 1)
    off = (weekday - d.weekday()) % 7
    return d + timedelta(days=off + (n - 1) * 7)


def futures_expiry(sym):
    """GCQ6/GCQ26 -> วันหมดอายุ futures = business day ที่ 3 นับถอยหลังจากสิ้นเดือนส่งมอบ"""
    m = re.match(r"GC([FGHJKMNQUVXZ])(\d{1,2})$", sym)
    if not m:
        return None
    month = MONTH_CODE[m.group(1)]
    yd = m.group(2)
    now = datetime.now()
    if len(yd) == 2:
        year = 2000 + int(yd)
    else:
        year = (now.year // 10) * 10 + int(yd)
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


def month_option_expiry(year, month):
    """monthly OPTION ของสัญญาเดือน M หมดอายุ ~4 business day ก่อนสิ้นเดือน M-1
    (คนละตัวกับ futures_expiry ซึ่งเป็นการส่งมอบ futures ปลายเดือน M)"""
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
    """weekly series อ้าง GC เดือนมาตรฐานตัวใกล้สุดที่ monthly option ยังไม่หมดอายุ
    ณ วันหมดอายุของ series (เช่น 10 ก.ย. -> GCV26 แต่ 2 ต.ค. -> GCZ26 เพราะ
    option ของ V หมด ~25 ก.ย. ไปแล้ว)"""
    y, m = series_expiry.year, series_expiry.month
    for k in range(14):
        mm = (m + k - 1) % 12 + 1
        yy = y + (m + k - 1) // 12
        if mm in GC_MONTHS and month_option_expiry(yy, mm) >= series_expiry:
            code = [c for c, v in MONTH_CODE.items() if v == mm][0]
            return "GC{}{}".format(code, str(yy)[-2:])
    return None


def gc_front_months(n=CURVE_N):
    """สัญญา gold เดือนมาตรฐาน n ตัวใกล้สุดที่ยังไม่หมดอายุ เช่น ['GCV26', 'GCZ26', 'GCG27']"""
    today = date.today()
    out = []
    k = 0
    while len(out) < n and k < 30:
        m = (today.month + k - 1) % 12 + 1
        y = today.year + (today.month + k - 1) // 12
        k += 1
        if m in GC_MONTHS:
            code = [c for c, mm in MONTH_CODE.items() if mm == m][0]
            sym = "GC{}{}".format(code, str(y)[-2:])
            if futures_expiry(sym) >= today:
                out.append(sym)
    return out


def weekly_candidates(today, horizon=8):
    """[(expiry_date, series_code)] ของวันทำการวันนี้ + horizon วันข้างหน้า
    เรียงใกล้->ไกล (เสาร์-อาทิตย์/วันหยุดจะไหลไป series ถัดไปเอง)"""
    out = []
    for k in range(horizon):
        d = today + timedelta(days=k)
        if d.weekday() >= 5:
            continue
        n = (d.day - 1) // 7 + 1
        code = WEEK_CODES[d.weekday()](n)
        mc = [c for c, mm in MONTH_CODE.items() if mm == d.month][0]
        out.append((d, "{}{}{}".format(code, mc, str(d.year)[-2:])))
    return out


# --------------------------------------------------------------------------- #
# Black-76 (คำนวณ IV เองจาก premium -- ใช้วัน 0DTE ที่ barchart คืน IV=0)
# --------------------------------------------------------------------------- #
def _ncdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def b76(F, K, t, v, call):
    """ราคา option แบบ Black-76 (r=0 -- 0DTE ดอกเบี้ยจิ๋วจนทิ้งได้)"""
    if v <= 0 or t <= 0:
        return max(F - K, 0.0) if call else max(K - F, 0.0)
    sd = v * math.sqrt(t)
    d1 = (math.log(F / K) + 0.5 * sd * sd) / sd
    d2 = d1 - sd
    if call:
        return F * _ncdf(d1) - K * _ncdf(d2)
    return K * _ncdf(-d2) - F * _ncdf(-d1)


def b76_iv(F, K, t, price, call):
    """implied vol (%) จาก premium ด้วย bisection / คืน None ถ้าหาไม่ได้
    (ราคา <= intrinsic หรือสูงเกิน vol 500%)"""
    intr = max(F - K, 0.0) if call else max(K - F, 0.0)
    if t <= 0 or price <= intr + 1e-9:
        return None
    lo, hi = 1e-4, 5.0
    if b76(F, K, t, hi, call) < price:
        return None
    for _ in range(60):
        mid = (lo + hi) / 2
        if b76(F, K, t, mid, call) < price:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2 * 100.0


def computed_iv_rows(legs, F, dte):
    """[(strike, iv%)] จาก "mid ของ bid/ask" ฝั่ง OTM -- bid/ask เป็น quote สด
    (delayed 10-15 นาทีเท่า feed) ต่างจาก lastPrice ที่เป็น trade ค้างเก่าได้ทั้งวัน
    smile จาก mid จึงเรียบและทันสมัยกว่ามาก / strike ไหนไม่มี two-sided quote ก็ข้าม"""
    if not F or not dte or dte <= 0:
        return []
    t = dte / 365.0
    rows = []
    for s, v in sorted(legs.items()):
        call = s > F  # ฝั่ง OTM มาตรฐานของการสร้าง smile
        r = v["Call"] if call else v["Put"]
        bid, ask = r.get("bidPrice"), r.get("askPrice")
        if not bid or not ask or float(ask) < float(bid):
            continue
        mid = (float(bid) + float(ask)) / 2
        iv = b76_iv(F, float(s), t, mid, call)
        if iv is not None and 0.5 < iv < 300:
            rows.append((s, iv))
    # ตัดปลายปีกที่ IV พุ่งเกิน 2.5x ATM -- เป็น artifact ของ minimum tick
    # (option ไร้ค่า bid/ask ต่ำสุด 0.05 ก็ back out ได้ IV 100+ ซึ่งไม่ใช่ราคาจริง)
    atm = iv_at(rows, F)
    if atm:
        rows = [(s, v) for s, v in rows if v <= atm * 2.5]
    return rows


def iv_at(vs_rows, x):
    """interpolate IV smile ณ ราคา x (ใช้หา ATM IV)"""
    if not vs_rows:
        return None
    ks = [s for s, _ in vs_rows]
    if x is None or x <= ks[0]:
        return vs_rows[0][1]
    if x >= ks[-1]:
        return vs_rows[-1][1]
    for (k0, v0), (k1, v1) in zip(vs_rows, vs_rows[1:]):
        if k0 <= x <= k1:
            return v0 + (v1 - v0) * (x - k0) / (k1 - k0)
    return None


# --------------------------------------------------------------------------- #
# Barchart core-api
# --------------------------------------------------------------------------- #
def bc_api(path_qs, referer=None):
    """ยิง core-api ตรงๆ -- ไม่มี cookie/XSRF/page load เพราะเงื่อนไขเดียวของ
    endpoint นี้คือ sec-fetch-site: same-origin (สถานะ ก.ย. 2026)"""
    req = urllib.request.Request(BC_BASE + "/proxies/core-api/v1/" + path_qs, headers={
        "User-Agent": UA, "Accept": "application/json",
        "sec-fetch-site": "same-origin", "sec-fetch-mode": "cors",
        "sec-fetch-dest": "empty",
        "Referer": referer or (BC_BASE + "/futures/quotes/GC*0/options")})
    return json.loads(urllib.request.urlopen(req, timeout=_budget(30)).read())


def parse_chain(chain):
    """chain (groupBy=strikePrice) -> {strike: {"Put": raw, "Call": raw}}"""
    legs = {}
    for strike, sides in (chain.get("data") or {}).items():
        s = float(strike.replace(",", ""))
        s = int(s) if s == int(s) else s
        v = {"Call": {}, "Put": {}}
        for leg in sides:
            r = leg.get("raw", leg)
            v[r.get("optionType", "?")] = r
        legs[s] = v
    return legs


def series_name_expiry(legs):
    """อ่าน 'Gold Thursday Week 2 Options Sep '26 ...' จาก symbolName ของ leg แรก
    -> (expiry_date, label) / None ถ้า parse ไม่ได้ (เช่นไปโดน monthly series)"""
    for v in legs.values():
        for side in ("Call", "Put"):
            m = re.match(r"Gold (Monday|Tuesday|Wednesday|Thursday|Friday) "
                         r"Week (\d) Options ([A-Z][a-z]{2}) '(\d\d)",
                         v[side].get("symbolName") or "")
            if m:
                wd = WD_NAMES.index(m.group(1))
                n = int(m.group(2))
                month = datetime.strptime(m.group(3), "%b").month
                year = 2000 + int(m.group(4))
                return _nth_weekday(year, month, wd, n), m.group(0)
    return None


def snapshot_barchart():
    """ดึงทุกอย่างจาก barchart ผ่าน core-api ล้วน (ห้ามโหลดหน้า HTML -- โดน WAF)"""
    today = date.today()

    # ไล่ probe จาก series ใกล้หมดอายุสุด: chain ว่าง = หมดอายุ/ยังไม่เปิด ข้ามไปตัวถัดไป
    series = expiry = None
    legs = {}
    tried = []
    for exp_guess, sym in weekly_candidates(today)[:5]:
        tried.append(sym)
        try:
            chain = bc_api("quotes/get?symbol={}&list=futures.options&fields={}"
                           "&groupBy=strikePrice&orderBy=strikePrice&orderDir=asc"
                           "&raw=1".format(sym, BC_CHAIN_FIELDS))
        except SourceDown:
            raise
        except Exception:
            continue
        got = parse_chain(chain)
        if not got:
            continue
        named = series_name_expiry(got)
        exp = named[0] if named else exp_guess  # ชื่อจริงชนะรหัสเดา
        if exp < today:
            continue
        series, expiry, legs = sym, exp, got
        break
    if series is None:
        raise SourceDown("barchart: ทุก candidate ว่าง ({})".format(",".join(tried)))

    # DTE: หมดอายุ 13:30 NY = 00:30 ไทยของวันถัดไป (หน้าร้อน; หน้าหนาว 01:30 --
    # คลาดครึ่งชั่วโมงยอมรับได้)
    end = datetime(expiry.year, expiry.month, expiry.day) + timedelta(days=1, minutes=30)
    dte = round(max((end - datetime.now()).total_seconds(), 0) / 86400, 3)

    # underlying ตามกติกา monthly-option-expiry + ราคา futures/curve ในคอลเดียว
    und_sym = underlying_for(expiry) or gc_front_months(1)[0]
    curve_syms = gc_front_months(CURVE_N)
    ask = list(dict.fromkeys([und_sym] + curve_syms))
    fq = bc_api("quotes/get?symbols={}&fields=symbol,lastPrice&raw=1".format(",".join(ask)))
    prices = {}
    for row in (fq.get("data") or []):
        r = row.get("raw", row)
        if r.get("lastPrice"):
            prices[r.get("symbol")] = float(r["lastPrice"])
    F = prices.get(und_sym)

    # Intraday / OI รายสไตรค์
    id_rows, oi_rows = [], []
    for s, v in sorted(legs.items()):
        pv = int(v["Put"].get("volume") or 0)
        cv = int(v["Call"].get("volume") or 0)
        po = int(v["Put"].get("openInterest") or 0)
        co = int(v["Call"].get("openInterest") or 0)
        if pv + cv > 0:
            id_rows.append((s, pv, cv))
        if po + co > 0:
            oi_rows.append((s, po, co))

    # IV smile: ค่า optImpliedVolatility (หน่วย % แล้ว) ฝั่ง OTM ต่อ strike --
    # วันหมดอายุ barchart คืน 0 ทั้ง chain -> คำนวณเองจาก premium แบบ Black-76
    vs_rows = []
    for s, v in sorted(legs.items()):
        r = v["Call"] if (F is not None and s > F) else v["Put"]
        iv = r.get("optImpliedVolatility")
        if iv and float(iv) > 0.5:
            vs_rows.append((s, round(float(iv), 2)))
    iv_src = "barchart"
    if not vs_rows:
        vs_rows = [(s, round(v, 2)) for s, v in computed_iv_rows(legs, F, dte)]
        iv_src = "computed"
    iv = iv_at(vs_rows, F)

    # curve: spread ภายใน feed เดียวกัน (ความช้าหักล้างกัน) -- format เดิมให้ gold_fetcher
    curve = None
    cons = []
    for sym in curve_syms:
        if sym in prices:
            fe = futures_expiry(sym)
            cons.append({"sym": sym, "price": prices[sym], "expiry": fe.isoformat(),
                         "days": (fe - today).days})
    if cons:
        base = cons[0]["price"]
        for c in cons:
            c["spread_vs_front"] = round(c["price"] - base, 2)
        spread_carry = None
        if len(cons) >= 2:
            gap = (date.fromisoformat(cons[1]["expiry"]) - date.fromisoformat(cons[0]["expiry"])).days
            if gap > 0:
                spread_carry = round(math.log(cons[1]["price"] / cons[0]["price"]) / (gap / 365) * 100, 3)
        curve = {"ts": datetime.now().timestamp(), "contracts": cons,
                 "spread_carry": spread_carry}

    return {
        "source": "barchart", "series": series, "und_sym": und_sym,
        "F": F, "dte": dte, "iv": round(iv, 2) if iv is not None else None,
        "iv_chg": None, "future_chg": None, "iv_src": iv_src,
        "id_rows": id_rows, "oi_rows": oi_rows, "vs_rows": vs_rows, "curve": curve,
    }


def inherit_same_day(snap):
    """IV/smile หายทั้งสองทาง -- ยืมจาก clip เดิมได้ถ้าเป็น "วันเดียวกัน"
    (smile ระหว่างวันขยับช้า ยืมข้ามชั่วโมงพอไหว ดีกว่าไม่มี)"""
    if snap["iv"] is not None and snap["vs_rows"]:
        return snap
    try:
        old = open(CLIP_OUT).read().strip().split("\n")
        hdr = dict(t.split(":", 1) for t in old[0].split("|") if ":" in t)
        if hdr.get("D", "")[:10] != "{:%Y-%m-%d}".format(datetime.now()):
            return snap
        if snap["iv"] is None and hdr.get("IV"):
            snap["iv"] = float(hdr["IV"])
            snap["iv_chg"] = float(hdr["IVCHG"]) if hdr.get("IVCHG") else None
            snap["iv_src"] = "inherit"
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


# --------------------------------------------------------------------------- #
# ส่วนประกอบเดิม (SD / top actives / changes / yahoo open)
# --------------------------------------------------------------------------- #
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
    """กรอบ SD: mean = ราคาเปิด Yahoo, DTE 0.6
    vol = IV - IVCHG เมื่อมี chg (semantic settle เดิมของ QuikStrike) /
    ยุค barchart ไม่มี chg -> ใช้ IV ปัจจุบัน (ATM, delayed) ตรงๆ"""
    if open_price is None or iv is None:
        return None
    vol_used = iv - (iv_chg or 0)
    sd1 = open_price * (vol_used / 100.0) * math.sqrt(SD_DTE / 365.0)
    lv = {"{}{}".format(side, n): round(open_price + (n * sd1 if side == "s" else -n * sd1), 1)
          for n in (1, 2, 3) for side in ("b", "s")}
    return dict(open=open_price, vol_used=round(vol_used, 2), dte=SD_DTE,
                sd1=round(sd1, 1), **lv)


def top_changes(rows_now, prev_map, n=2):
    """เทียบ per-strike กับรอบก่อน คืน n อันดับที่เปลี่ยนมากสุด [{strike, dp, dc}]
    นับเฉพาะ strike ที่อยู่ในรอบปัจจุบัน — ตัวที่หายไปมักเป็นเพราะช่วง strike เลื่อน
    (จะกลายเป็น delta ลบปลอมก้อนใหญ่) ไม่ใช่การปิดสัญญาจริง"""
    changes = []
    for s, p, c in rows_now:
        p_old, c_old = prev_map.get(str(s), (0, 0))
        dp, dc = p - p_old, c - c_old
        if dp or dc:
            changes.append({"strike": s, "dp": dp, "dc": dc})
    changes.sort(key=lambda x: -(abs(x["dp"]) + abs(x["dc"])))
    return changes[:n]


# --------------------------------------------------------------------------- #
# กราฟ HTML หน้าตาแบบ CME Vol2Vol (เปิด /tmp/cme_chart.html ค้างใน browser ได้
# หน้า reload ตัวเองทุก 5 นาที ข้อมูลใหม่มาตามรอบ cron) -- ทั้งไฟล์ self-contained
# ไม่มี dependency ภายนอก เพราะต้องเปิดแบบ file:// ได้
# --------------------------------------------------------------------------- #
CHART_TMPL = r"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta http-equiv="refresh" content="300">
<title>Gold 0DTE Put/Call</title>
<style>
 body{font-family:-apple-system,Helvetica,Arial,sans-serif;background:#fafafa;margin:14px;color:#222}
 #hdr{display:flex;align-items:baseline;gap:24px;margin:2px 4px 8px}
 #title{font-size:19px;font-weight:700}
 #totals{font-size:14px}
 #totals b.put{color:#f5a623}#totals b.call{color:#4a80e8}#totals b.iv{color:#c0392b}
 #mode{margin-left:auto;display:flex;gap:6px;align-items:center}
 #mode button{border:1px solid #ccc;background:#fff;padding:3px 12px;border-radius:4px;cursor:pointer;font-size:12px}
 #mode button.on{background:#4a80e8;color:#fff;border-color:#4a80e8}
 #legend{font-size:12px;color:#555;margin-left:12px}
 #legend .sw{display:inline-block;width:9px;height:9px;border-radius:50%;margin:0 3px 0 10px}
 #upd{font-size:11px;color:#999;margin:6px 4px}
 svg{background:#f5f5f5;border:1px solid #e2e2e2;border-radius:4px}
</style></head><body>
<div id="hdr">
 <span id="title"></span>
 <span id="totals"></span>
 <span id="mode">
  <span id="legend"><span class="sw" style="background:#f5a623"></span>Put
   <span class="sw" style="background:#4a80e8"></span>Call
   <span style="color:#c0392b;margin-left:10px">- - -</span> IV</span>
  <button id="bId">Intraday</button><button id="bOi">OI</button>
 </span>
</div>
<svg id="c" width="960" height="600"></svg>
<div id="upd"></div>
<script>
const D = __DATA__;
let mode = "id";
const NS = "http://www.w3.org/2000/svg";
function el(tag, attrs, parent, tip){
  const e = document.createElementNS(NS, tag);
  for (const k in attrs) e.setAttribute(k, attrs[k]);
  if (tip){ const t = document.createElementNS(NS, "title"); t.textContent = tip; e.appendChild(t); }
  parent.appendChild(e); return e;
}
function fmt(x){ return x==null ? "--" : x.toLocaleString("en-US"); }
function render(){
  const svg = document.getElementById("c"); svg.innerHTML = "";
  const W = 960, H = 600, L = 52, R = 58, T = 16, B = 34;
  const rows = D[mode].filter(r => r[1] + r[2] > 0);
  document.getElementById("title").textContent = D.series + (mode === "id" ? " Intraday Volume" : " Open Interest");
  const tp = rows.reduce((a, r) => a + r[1], 0), tc = rows.reduce((a, r) => a + r[2], 0);
  document.getElementById("totals").innerHTML =
    'Put: <b class="put">' + fmt(tp) + '</b> &nbsp;Call: <b class="call">' + fmt(tc) +
    '</b> &nbsp;IV' + (D.iv_src && D.iv_src !== "barchart" ? " (" + D.iv_src + ")" : "") +
    ': <b class="iv">' + (D.iv ?? "--") + '</b>';
  document.getElementById("bId").className = mode === "id" ? "on" : "";
  document.getElementById("bOi").className = mode === "oi" ? "on" : "";
  document.getElementById("upd").textContent = "updated " + D.updated + " · " + D.series +
    " on " + D.und + " · DTE " + D.dte + " · source barchart (delayed 10-15m)";
  if (!rows.length) return;
  // โดเมนแกน x: ±3.5σ รอบ F (ไม่งั้นปีก OI ลากกราฟกว้างจนแท่งกลางจมหาย)
  const sig = (D.F && D.iv && D.dte > 0) ? D.F * D.iv / 100 * Math.sqrt(D.dte / 365) : null;
  let lo = Math.min(...rows.map(r => r[0])), hi = Math.max(...rows.map(r => r[0]));
  if (sig && D.F){ lo = Math.max(lo, D.F - 3.5 * sig); hi = Math.min(hi, D.F + 3.5 * sig); }
  lo -= 5; hi += 5;
  const x = v => L + (v - lo) / (hi - lo) * (W - L - R);
  const vrows = rows.filter(r => r[0] >= lo && r[0] <= hi);
  const ymax = Math.max(...vrows.map(r => Math.max(r[1], r[2]))) * 1.08;
  const y = v => T + (1 - v / ymax) * (H - T - B);
  // แถบ SD band รอบ F (ในเข้มออกอ่อน แบบ expected range ของ CME)
  if (sig && D.F){
    const shades = ["#d7d7d7", "#e2e2e2", "#ececec"];  // วงใน (1σ) เข้มสุดแบบ CME
    for (let n = 3; n >= 1; n--){
      const a = Math.max(x(D.F - n * sig), L), b = Math.min(x(D.F + n * sig), W - R);
      el("rect", {x: a, y: T, width: b - a, height: H - T - B, fill: shades[n - 1]}, svg,
         "±" + n + "σ: " + (D.F - n * sig).toFixed(1) + " - " + (D.F + n * sig).toFixed(1));
    }
  }
  // grid + แกนซ้าย (volume)
  const step = Math.pow(10, Math.floor(Math.log10(ymax))) * (ymax / Math.pow(10, Math.floor(Math.log10(ymax))) > 5 ? 1 : 0.5) || 1;
  for (let v = 0; v <= ymax; v += step){
    el("line", {x1: L, x2: W - R, y1: y(v), y2: y(v), stroke: "#ddd", "stroke-width": 1}, svg);
    el("text", {x: L - 6, y: y(v) + 4, "text-anchor": "end", "font-size": 11, fill: "#888"}, svg).textContent = fmt(v);
  }
  // แท่ง Put(ส้ม)/Call(น้ำเงิน) เคียงกันต่อ strike
  const stepX = vrows.length > 1 ? Math.min(...vrows.slice(1).map((r, i) => r[0] - vrows[i][0])) : 5;
  const bw = Math.max(1.5, (x(lo + stepX) - x(lo)) * 0.36);
  for (const [s, p, c] of vrows){
    const tip = s + "  Put " + fmt(p) + "  Call " + fmt(c) + "  Total " + fmt(p + c);
    if (p) el("rect", {x: x(s) - bw - 0.5, y: y(p), width: bw, height: y(0) - y(p), fill: "#f5a623"}, svg, tip);
    if (c) el("rect", {x: x(s) + 0.5, y: y(c), width: bw, height: y(0) - y(c), fill: "#4a80e8"}, svg, tip);
  }
  // smile IV แกนขวา (เส้นประแดง)
  const vs = D.vs.filter(r => r[0] >= lo && r[0] <= hi);
  if (vs.length > 2){
    let vlo = Math.min(...vs.map(r => r[1])), vhi = Math.max(...vs.map(r => r[1]));
    const pad = (vhi - vlo) * 0.15 + 0.5; vlo -= pad; vhi += pad;
    const yr = v => T + (1 - (v - vlo) / (vhi - vlo)) * (H - T - B);
    el("path", {d: vs.map((r, i) => (i ? "L" : "M") + x(r[0]).toFixed(1) + "," + yr(r[1]).toFixed(1)).join(""),
                fill: "none", stroke: "#e05252", "stroke-width": 1.6, "stroke-dasharray": "6 4", opacity: 0.9}, svg);
    for (let k = 0; k <= 5; k++){
      const v = vlo + (vhi - vlo) * k / 5;
      el("text", {x: W - R + 6, y: yr(v) + 4, "font-size": 11, fill: "#888"}, svg).textContent = v.toFixed(1);
    }
    el("text", {x: W - 12, y: H / 2, "font-size": 11, fill: "#aaa",
                transform: "rotate(90 " + (W - 12) + " " + H / 2 + ")", "text-anchor": "middle"}, svg).textContent = "Volatility";
  }
  // เส้น Future
  if (D.F && D.F > lo && D.F < hi){
    el("line", {x1: x(D.F), x2: x(D.F), y1: T, y2: H - B, stroke: "#333", "stroke-width": 1.2, "stroke-dasharray": "5 3"}, svg);
    el("text", {x: x(D.F) - 5, y: T + 8, "font-size": 11, fill: "#333",
                transform: "rotate(90 " + (x(D.F) - 5) + " " + (T + 8) + ")"}, svg).textContent = "Future: " + fmt(D.F);
  }
  // แกน x
  const t0 = Math.ceil(lo / 50) * 50;
  for (let s = t0; s <= hi; s += 50)
    el("text", {x: x(s), y: H - B + 18, "text-anchor": "middle", "font-size": 11, fill: "#666"}, svg).textContent = fmt(s);
  el("text", {x: 16, y: H / 2, "font-size": 11, fill: "#aaa",
              transform: "rotate(-90 16 " + H / 2 + ")", "text-anchor": "middle"}, svg).textContent =
    mode === "id" ? "Intraday Volume" : "Open Interest";
}
document.getElementById("bId").onclick = () => { mode = "id"; render(); };
document.getElementById("bOi").onclick = () => { mode = "oi"; render(); };
render();
</script></body></html>
"""


def chart_html(snap, now):
    payload = {
        "series": snap["series"], "und": snap.get("und_sym"), "F": snap["F"],
        "dte": snap["dte"], "iv": snap["iv"], "iv_src": snap.get("iv_src"),
        "updated": "{:%Y-%m-%d %H:%M}".format(now),
        "id": [list(r) for r in snap["id_rows"]],
        "oi": [list(r) for r in snap["oi_rows"]],
        "vs": [list(r) for r in snap["vs_rows"]],
    }
    return CHART_TMPL.replace("__DATA__", json.dumps(payload))


def main():
    global _deadline
    now = datetime.now()
    _deadline = time.monotonic() + MAX_RUNTIME

    # แหล่งเดียว: barchart (CME/QuikStrike Vol2Vol ถูกถอดออก ก.ย. 2026)
    snap = snapshot_barchart()
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

    header = ("F:{}|D:{:%Y-%m-%d %H:%M}|S:{}|IV:{}|IVCHG:{}|DTE:{}".format(
        meta["F"] if meta["F"] is not None else "", now, meta["series"],
        meta["iv"] if meta["iv"] is not None else "",
        iv_chg if iv_chg is not None else "",
        round(meta["dte"], 3) if meta["dte"] is not None else ""))
    vs_rows = snap["vs_rows"]
    clip = "\n".join([
        header,
        "ID;" + ";".join("{}:{}:{}".format(s, p, c) for s, p, c in id_rows),
        "OI;" + ";".join("{}:{}:{}".format(s, p, c) for s, p, c in oi_rows),
        "VS;" + ";".join("{}:{:.2f}".format(s, v) for s, v in vs_rows),
    ]) + "\n"

    data = {
        "ts": now.timestamp(),
        "system_time": "{:%H:%M}".format(now),
        "source": snap["source"],
        "series": meta["series"],
        "und_sym": snap.get("und_sym"),  # underlying ของ 0DTE เช่น GCV26
        "F": meta["F"],
        "dte": round(meta["dte"], 3) if meta["dte"] is not None else None,
        "iv": meta["iv"],
        "iv_chg": iv_chg,
        "iv_src": snap.get("iv_src"),    # barchart / computed (Black-76) / inherit
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
        "series": meta["series"], "time": "{:%H:%M}".format(now),
        "id": {str(s): [p, c] for s, p, c in id_rows},
        "oi": {str(s): [p, c] for s, p, c in oi_rows},
    })
    writes = [(JSON_OUT, json.dumps(data, ensure_ascii=False)),
              (CLIP_OUT, clip), (PREV_STATE, new_state),
              (CHART_OUT, chart_html(snap, now))]
    if curve:
        writes.append((CURVE_OUT, json.dumps(curve)))
    for path, content in writes:
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            f.write(content)
        os.replace(tmp, path)

    curve_txt = ""
    if curve:
        curve_txt = " curve {} carry {}%".format(
            "/".join(c["sym"] for c in curve["contracts"]), curve["spread_carry"])
    print("[{:%Y-%m-%d %H:%M:%S}] ok [{}] {} und={} F={}{} "
          "ID {}/{} OI {}/{} IV {} ({}) strikes {}/{}/{} clip {}B".format(
              now, snap["source"], meta["series"], snap.get("und_sym"),
              meta["F"], curve_txt,
              data["intraday"]["put"], data["intraday"]["call"],
              data["oi"]["put"], data["oi"]["call"],
              meta["iv"], snap.get("iv_src"),
              len(id_rows), len(oi_rows), len(vs_rows), len(clip)))


if __name__ == "__main__":
    try:
        main()
    except (SourceDown, socket.timeout, urllib.error.URLError) as e:
        # ฝั่งแหล่งข้อมูลล่ม/ช้า: ไม่เขียนทับไฟล์เดิม -> widget ขึ้น STALE เองหลัง 2 ชม.
        print("[{:%Y-%m-%d %H:%M:%S}] SOURCE DOWN: {}: {}".format(
            datetime.now(), type(e).__name__, e), file=sys.stderr)
        sys.exit(2)
    except Exception as e:
        print("[{:%Y-%m-%d %H:%M:%S}] ERROR {}: {}".format(
            datetime.now(), type(e).__name__, e), file=sys.stderr)
        sys.exit(1)
