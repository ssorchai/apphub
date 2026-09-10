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

QuikStrike ยังใช้ได้ 2 view แบบ anonymous (Referer จาก cmegroup.com เหมือนยุค Vol2Vol
-- viewitemid หาโดยจำลอง postback กดเมนูให้เซิร์ฟเวอร์เฉลย ชื่อในเมนูใช้ตรงๆ ไม่ได้):
  - IntegratedEventVolCalculator -> event vol ของ 0DTE = **IV หลักที่ใช้คิด SD**
    (forward vol ครอบช่วงที่จบวันนี้ วันมี event เช่น FOMC จะกว้างกว่าปกติ)
    ⚠️ ค่านี้ re-mark ระหว่างวัน ตอนเช้าจะเท่า settle แล้วค่อยขยับตามตลาด
  - IntegratedSettlementSheet -> ตาราง #pricing-sheet: **settle vol + Vol Chg รายสไตรค์**
    ของ CME = smile ที่เอาไป plot (VS) และเป็นคู่เดียวที่ใช้สูตร Vol - Vol Chg ได้
    เลือก expiration เองด้วย postback (จับคู่จากวันหมดอายุใน title ของ anchor เพราะ
    barchart/QuikStrike ใช้คนละระบบรหัส: I0HU26 vs G2RU6) + ตั้ง ddlStrikes=(All)

IV สำรองเมื่อ QuikStrike ล่ม: barchart คืน optImpliedVolatility=0 ทั้ง chain "ในวัน
หมดอายุของ series นั้นเอง" (หน้าเว็บจริงก็ว่าง) -> คำนวณเองจาก mid ของ bid/ask
(Black-76 + bisection, t=dte/365 day-count เดียวกับสูตร SD) ฝั่ง OTM
/ ไม่ได้อีกค่อย inherit จาก clip เดิมของวันเดียวกัน

Output (atomic เขียน .tmp แล้ว os.replace เหมือน fetcher ตัวอื่น):
  /tmp/cme_putcall.json      ให้ cme-putcall.jsx (Übersicht) อ่านแสดงผล
  /tmp/cme_putcall_clip.txt  string สำหรับ paste ลงช่อง P/C ของ oi_block.pine:
      F:4407.7|D:2026-09-10 17:29|S:I0HU26|IV:41.55|IVCHG:|DTE:0.292|IVS:31.54|IVSCHG:3.69
      ID;4090:12:5;4100:44:10;...        (strike:put:call เฉพาะที่มีของ)
      OI;4000:821:66;...
      VS;3900:31.87;3925:30.12;...       (strike:vol% = settle vol ของ CME นิ่งทั้งวัน)
      IV/IVCHG = ตัวที่ใช้คิด SD (ปกติ IV = event vol, IVCHG ว่างเพราะ Vol Chg เป็นของ
      คู่ settle -- เอามาลบ event vol จะไม่มีความหมาย) / IVS,IVSCHG = คู่ settle ของ CME
      คีย์ IVS/IVSCHG เป็นของใหม่ ฝั่ง Pine จับคีย์ทีละตัวจึงข้ามคีย์ที่ไม่รู้จักเงียบๆ
  /tmp/cme_eventvol.json     จุด event vol ของ 0DTE (vol/forward vol)
  /tmp/cme_chart.html        กราฟแบบ CME Vol2Vol (แท่ง P/C + smile settle + SD band)
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
import http.cookiejar
from datetime import date, datetime, timedelta

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

JSON_OUT = "/tmp/cme_putcall.json"
CLIP_OUT = "/tmp/cme_putcall_clip.txt"
CURVE_OUT = "/tmp/cme_curve.json"
CHART_OUT = "/tmp/cme_chart.html"   # กราฟหน้าตาแบบ CME Vol2Vol เปิดค้างใน browser ได้
EVENTVOL_OUT = "/tmp/cme_eventvol.json"

# Event Volatility Calculator ของ QuikStrike ยังเข้า anonymous ได้ (Referer trick เดิม)
# viewitemid จริงคือ IntegratedEventVolCalculator -- แกะจาก ContainerId ใน payload
# (ลิงก์บน cmegroup.com เป็นแค่ iframe ครอบหน้านี้ -- ห้ามยิง cmegroup.com เอง IP โดนแบน)
# ให้ ATM vol + forward vol รายช่วงของทุก expiration -> forward vol ที่โดดคือวันมี event
QS_EVC_URL = ("https://cmegroup-tools.quikstrike.net/User/QuikStrikeView.aspx"
              "?pid=40&pf=6&viewitemid=IntegratedEventVolCalculator")
# Settlement Sheet = ตาราง #pricing-sheet ตัวเดียวกับที่ script ของเพื่อนอ่าน และ
# **เข้า anonymous ได้** (viewitemid จริง = IntegratedSettlementSheet -- ชื่อในเมนูคือ
# "Settlement Prices" หา viewitemid ด้วยการจำลอง postback กดเมนูให้เซิร์ฟเวอร์เฉลยเอง)
# ให้ settle vol + Vol Chg "รายสไตรค์" ของ CME = smile settle จริงแบบยุค Vol2Vol
QS_SETTLE_URL = ("https://cmegroup-tools.quikstrike.net/User/QuikStrikeView.aspx"
                 "?pid=40&pf=6&viewitemid=IntegratedSettlementSheet")
QS_REFERER = "https://www.cmegroup.com/"
QS_BUDGET = 45          # งบแยกของ QuikStrike -- ตัวเสริม ห้ามกินงบจนกระทบข้อมูลหลัก

# คอลัมน์ของตาราง #pricing-sheet (ยืนยัน 10 ก.ย. 26 จาก header สองชั้น:
# Call[Chg,Prior,Settle] | Strike | Put[Settle,Prior,Chg] | Volatility[S,P,C] |
# BasisPointVol[S,P,C] | BlackScholesVol[S,P,C] | OpenInterest[Call,CallChg,Put,PutChg])
SHEET_STRIKE, SHEET_VOL, SHEET_VOLCHG, SHEET_NCOL = 3, 7, 9, 20

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
        "expiry": expiry,
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


def _qs_opener():
    jar = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    op.addheaders = [("User-Agent", UA), ("Referer", QS_REFERER)]
    return op


def _qs_selects(html):
    """{name: ค่าที่เลือกอยู่} ของ <select> ทุกตัวในฟอร์ม -- ASP.NET อ่าน state ของ
    control จากฟอร์มที่ POST กลับ ถ้าไม่ส่งไปด้วยมันจะรีเซ็ตเป็น option แรก"""
    out = {}
    for m in re.finditer(r'<select[^>]*name="([^"]+)"[^>]*>(.*?)</select>', html, re.S):
        opts = re.findall(r'<option([^>]*)value="([^"]*)"', m.group(2))
        sel = next((v for a, v in opts if "selected" in a), opts[0][1] if opts else "")
        out[m.group(1)] = sel
    return out


def _qs_postback(op, url, html, target, extra=None):
    """จำลอง __doPostBack ของ WebForms (ส่ง __VIEWSTATE เดิมกลับ + __EVENTTARGET)"""
    def val(n):
        m = re.search(r'id="{}" value="([^"]*)"'.format(n), html)
        return m.group(1) if m else ""
    fields = _qs_selects(html)
    fields.update({
        "__EVENTTARGET": target, "__EVENTARGUMENT": "",
        "__VIEWSTATE": val("__VIEWSTATE"),
        "__VIEWSTATEGENERATOR": val("__VIEWSTATEGENERATOR"),
        "__EVENTVALIDATION": val("__EVENTVALIDATION")})
    fields.update(extra or {})
    data = urllib.parse.urlencode(fields).encode()
    req = urllib.request.Request(url, data=data, headers={
        "User-Agent": UA, "Referer": url,
        "Content-Type": "application/x-www-form-urlencoded"})
    return op.open(req, timeout=_budget(35)).read().decode()


def _parse_sheet(html):
    """ตาราง #pricing-sheet -> ([(strike, vol_settle)], {strike: vol_chg})"""
    m = re.search(r'id="pricing-sheet"(.*?)</table>', html, re.S)
    if not m:
        raise RuntimeError("settle sheet: ไม่เจอตาราง #pricing-sheet")
    vs, chg = [], {}
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", m.group(1), re.S):
        tds = [re.sub("<[^>]+>", "", td).replace("&nbsp;", "").replace(",", "").strip()
               for td in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
        if len(tds) < SHEET_NCOL:
            continue
        try:
            k = float(tds[SHEET_STRIKE])
            v = float(tds[SHEET_VOL].replace("%", ""))
            c = float(tds[SHEET_VOLCHG].replace("%", ""))
        except ValueError:
            continue
        if k < 100 or not (0 < v < 300):   # กันแถวสรุป/แถวหัวที่หลุด filter มา
            continue
        k = int(k) if k == int(k) else k
        vs.append((k, v))
        chg[k] = c
    if not vs:
        raise RuntimeError("settle sheet: parse ไม่ได้สักแถว (โครงตารางเปลี่ยน?)")
    vs.sort()
    return vs, chg


def fetch_settle_sheet(expiry):
    """smile settle ของ CME รายสไตรค์ สำหรับ series ที่หมดอายุวันที่ expiry
    -> (vs_rows, chg_map, qs_sym)

    ต้องเลือก expiration ใน selector เองด้วย postback: default ของหน้าคือ series ถัดไป
    ไม่ใช่ 0DTE / จับคู่จาก attribute title ของ anchor ซึ่งมีข้อมูลครบ (ชื่อสัญลักษณ์
    อยู่ใน <div> ข้างในอีกที ใช้ text ของ anchor จับไม่ได้):
      title="Option Contract:\tSep 2026
             Option Expiration:\t9/10/2026 (0.31 DTE)
             Option Symbol:\t\tG2RU6 ..."
    จับด้วย "วันหมดอายุ" ไม่ใช่ชื่อ -- barchart กับ QuikStrike ใช้คนละระบบรหัส
    (I0HU26 vs G2RU6) วันหมดอายุเป็นตัวเชื่อมเดียวที่เชื่อได้"""
    op = _qs_opener()
    r = op.open(urllib.request.Request(QS_SETTLE_URL, headers={
        "User-Agent": UA, "Referer": QS_REFERER}), timeout=_budget(35))
    html = r.read().decode()
    url = r.geturl()
    _qs_check_page(html, url)
    want = "{}/{}/{}".format(expiry.month, expiry.day, expiry.year)
    target = qs_sym = None
    for m in re.finditer(r'title="([^"]*Option Expiration:[^"]*)"[^>]*?'
                         r'href="javascript:__doPostBack\(&#39;([^&]*\$lbExpiration)&#39;', html):
        title = m.group(1)
        if re.search(r"Option Expiration:\s*" + re.escape(want) + r"\b", title):
            target = m.group(2)
            sm = re.search(r"Option Symbol:\s*([A-Z0-9]+)", title)
            qs_sym = sm.group(1) if sm else None
            break
    if not target:
        raise RuntimeError("settle sheet: ไม่เจอ expiration {} ใน selector".format(want))
    # ddlStrikes = -1 คือ "(All)" -- default ของหน้าคือ 25 สไตรค์รอบ ATM ซึ่งแคบกว่ากรอบ
    # 3σ ที่ใช้เทรด และ ladder นี้ถูกใช้เป็นแกนของ WormHole ฝั่ง Pine ด้วย
    extra = {n: "-1" for n in _qs_selects(html) if n.endswith("ddlStrikes")}
    html = _qs_postback(op, url, html, target, extra)
    _qs_check_page(html)
    vs, chg = _parse_sheet(html)
    return vs, chg, qs_sym


def _qs_check_page(html, url=""):
    """จับหน้า error/login ของ QuikStrike (ทั้งคู่ตอบ HTTP 200 -- ดู status ไม่พอ)"""
    if "/Error/ErrorPage.aspx" in url or "QuikStrike Error" in html[:3000]:
        m = re.search(r"MSG=([^&]*)", url)
        msg = urllib.parse.unquote_plus(m.group(1)).strip()[:80] if m else "ไม่ทราบสาเหตุ"
        raise RuntimeError("QuikStrike error page: " + msg)
    if "/Account/Login.aspx" in url:
        raise RuntimeError("QuikStrike เด้งไปหน้า login (โดน bot detection?)")


def fetch_eventvol():
    """[{sym, expires, dte, vol, fwd}] จาก QuikStrike Event Volatility Calculator
    (ตัวเสริม -- QuikStrike ล่ม/เปลี่ยนโครงเมื่อไหร่ก็ข้าม ไม่กระทบข้อมูลหลัก)
    ข้อมูลฝังใน HTML เป็น $create(...EventVol.Calculator.Chart, {"JSONSettings": ...})
    แบบเดียวกับ Vol2Vol ยุคเก่า / vol = ATM vol ของ expiration, fwd = forward vol
    ของช่วงระหว่าง expiration ก่อนหน้า -> fwd ที่โดดจากเพื่อน = ช่วงนั้นมี event"""
    req = urllib.request.Request(QS_EVC_URL, headers={
        "User-Agent": UA, "Referer": QS_REFERER})
    html = urllib.request.urlopen(req, timeout=_budget(35)).read().decode()
    i = html.find("EventVol.Calculator.Chart")
    if i < 0:
        raise RuntimeError("EventVol: ไม่เจอ chart payload (โดน error/login page?)")
    m = re.search(r'"JSONSettings":"((?:[^"\\]|\\.)*)"', html[i - 50:])
    d = json.loads(m.group(1).encode().decode("unicode_escape"))
    pts = []
    for s in d.get("Series", []):
        if s.get("name") != "Volatility":
            continue
        for p in s.get("data") or []:
            try:
                vol = float(str(p.get("vol", "")).replace("%", "").strip())
                dte = float(p.get("dte"))
            except (ValueError, TypeError):
                continue
            try:
                fwd = float(str(p.get("forwardVol", "")).replace("%", "").strip())
                if math.isnan(fwd):
                    fwd = None
            except (ValueError, TypeError):
                fwd = None
            pts.append({"sym": p.get("symbol"), "expires": p.get("expires"),
                        "dte": round(dte, 2), "vol": vol, "fwd": fwd})
    pts.sort(key=lambda x: x["dte"])
    if not pts:
        raise RuntimeError("EventVol: payload ว่าง")
    return pts


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
 #hdr{display:flex;align-items:baseline;flex-wrap:wrap;gap:6px 18px;margin:2px 4px 8px}
 #title{font-size:19px;font-weight:700;white-space:nowrap}
 #totals{font-size:14px;white-space:nowrap}
 #totals b.put{color:#f5a623}#totals b.call{color:#4a80e8}#totals b.iv{color:#c0392b}
 #totals b.ev{color:#7b52c0}
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
   <span style="color:#c0392b;margin-left:10px">- - -</span> Vol Settle</span>
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
function smooth(vs){                       // median-3 + weighted MA (1,2,3,2,1)
  if (vs.length < 5) return vs;
  const v = vs.map(r => r[1]);
  const med = v.map((x, i) => (i > 0 && i < v.length - 1)
    ? [v[i-1], x, v[i+1]].sort((a, b) => a - b)[1] : x);
  const w = [1, 2, 3, 2, 1];
  return vs.map((r, i) => {
    let s = 0, ws = 0;
    for (let k = -2; k <= 2; k++){
      const j = i + k;
      if (j >= 0 && j < med.length){ s += med[j] * w[k + 2]; ws += w[k + 2]; }
    }
    return [r[0], s / ws];
  });
}
function splinePath(p){                    // Catmull-Rom -> cubic bezier
  if (p.length < 3) return p.map((q, i) => (i ? "L" : "M") + q[0].toFixed(1) + "," + q[1].toFixed(1)).join("");
  let d = "M" + p[0][0].toFixed(1) + "," + p[0][1].toFixed(1);
  for (let i = 0; i < p.length - 1; i++){
    const p0 = p[Math.max(i - 1, 0)], p1 = p[i], p2 = p[i + 1], p3 = p[Math.min(i + 2, p.length - 1)];
    const c1 = [p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6];
    const c2 = [p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6];
    d += "C" + c1[0].toFixed(1) + "," + c1[1].toFixed(1) + " " + c2[0].toFixed(1) + "," + c2[1].toFixed(1) + " " + p2[0].toFixed(1) + "," + p2[1].toFixed(1);
  }
  return d;
}
function render(){
  const svg = document.getElementById("c"); svg.innerHTML = "";
  const W = 960, H = 600, L = 52, R = 58, T = 16, B = 34;
  const rows = D[mode].filter(r => r[1] + r[2] > 0);
  document.getElementById("title").textContent = D.series + (mode === "id" ? " Intraday Volume" : " Open Interest");
  const tp = rows.reduce((a, r) => a + r[1], 0), tc = rows.reduce((a, r) => a + r[2], 0);
  // แถวตัวเลข: VolSettle (+Chg) แบบ CME + Event Vol ของ 0DTE / ตัวที่ขีดเส้นใต้คือตัวที่คิด SD
  const un = k => D.iv_src === k ? "border-bottom:2px solid currentColor" : "";
  let s = 'Put: <b class="put">' + fmt(tp) + '</b> &nbsp;Call: <b class="call">' + fmt(tc) + '</b>';
  if (D.iv_settle != null)
    s += ' &nbsp;VolSettle: <b class="iv" style="' + un("settle") + '">' + D.iv_settle + '</b>' +
         (D.iv_settle_chg != null ? ' <span style="color:#999">(' +
          (D.iv_settle_chg > 0 ? "+" : "") + D.iv_settle_chg + ')</span>' : "");
  if (D.iv_event != null)
    s += ' &nbsp;EventVol 0DTE: <b class="ev" style="' + un("event") + '">' + D.iv_event + '</b>';
  if (D.iv_settle == null && D.iv_event == null)
    s += ' &nbsp;IV (' + D.iv_src + '): <b class="iv">' + (D.iv ?? "--") + '</b>';
  document.getElementById("totals").innerHTML = s;
  document.getElementById("bId").className = mode === "id" ? "on" : "";
  document.getElementById("bOi").className = mode === "oi" ? "on" : "";
  document.getElementById("upd").textContent = "updated " + D.updated + " · " + D.series +
    (D.qs_sym ? " (" + D.qs_sym + ")" : "") + " on " + D.und + " · DTE " + D.dte +
    " · P/C barchart delayed 10-15m · vol CME settle+event (QuikStrike)" +
    " · ขีดเส้นใต้ = ตัวที่ใช้คิด SD";
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
  // smile IV แกนขวา (เส้นประแดง) -- ค่า computed มี noise จาก bid/ask spread
  // เลย smooth ตอน render: median-3 กัน outlier + moving average ถ่วงน้ำหนัก
  // แล้ววาดเป็น Catmull-Rom spline (ข้อมูลดิบใน clip/VS ไม่ถูกแตะ)
  const vs = smooth(D.vs.filter(r => r[0] >= lo && r[0] <= hi));
  if (vs.length > 2){
    let vlo = Math.min(...vs.map(r => r[1])), vhi = Math.max(...vs.map(r => r[1]));
    const pad = (vhi - vlo) * 0.15 + 0.5; vlo -= pad; vhi += pad;
    const yr = v => T + (1 - (v - vlo) / (vhi - vlo)) * (H - T - B);
    el("path", {d: splinePath(vs.map(r => [x(r[0]), yr(r[1])])),
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


def chart_html(snap, now, ev=None):
    payload = {
        "series": snap["series"], "und": snap.get("und_sym"), "F": snap["F"],
        "dte": snap["dte"], "iv": snap["iv"], "iv_src": snap.get("iv_src"),
        "iv_event": snap.get("iv_event"), "iv_settle": snap.get("iv_settle"),
        "iv_settle_chg": snap.get("iv_settle_chg"), "qs_sym": snap.get("qs_sym"),
        "updated": "{:%Y-%m-%d %H:%M}".format(now),
        "id": [list(r) for r in snap["id_rows"]],
        "oi": [list(r) for r in snap["oi_rows"]],
        "vs": [list(r) for r in snap["vs_rows"]],
        "ev": ev or [],
    }
    return CHART_TMPL.replace("__DATA__", json.dumps(payload))


def main():
    global _deadline
    now = datetime.now()
    _deadline = time.monotonic() + MAX_RUNTIME

    # แหล่งเดียว: barchart (CME/QuikStrike Vol2Vol ถูกถอดออก ก.ย. 2026)
    snap = snapshot_barchart()
    snap = inherit_same_day(snap)

    # ---- ส่วนเสริมจาก QuikStrike (งบเวลาแยก / พังก็ข้าม ไม่กระทบข้อมูลหลักและ exit code) ----
    # 1) Event Vol Calculator: เอาเฉพาะ "จุด 0DTE" ตามที่ใช้จริง (จับคู่ด้วยวันหมดอายุ
    #    ไม่ใช่ชื่อ -- QuikStrike ใช้รหัส CME 'G2RU6' ส่วน barchart ใช้ 'I0HU26')
    #    -> ได้ทั้ง event vol (forward vol ของช่วงที่จบวันนี้) และรหัส CME ของ series
    # 2) Settlement Sheet: smile settle + Vol Chg รายสไตรค์ของ series เดียวกันนั้น
    _deadline = time.monotonic() + QS_BUDGET
    ev0 = qs_sym = None
    try:
        for p in fetch_eventvol():
            if datetime.strptime(p["expires"], "%m/%d/%Y").date() == snap["expiry"]:
                ev0, qs_sym = p, p["sym"]
                break
        print("[{:%Y-%m-%d %H:%M:%S}] eventvol 0DTE {}".format(now, ev0), file=sys.stderr)
    except Exception as e:
        print("[{:%Y-%m-%d %H:%M:%S}] eventvol พัง (ข้าม): {}: {}".format(
            now, type(e).__name__, str(e)[:80]), file=sys.stderr)

    iv_settle = iv_settle_chg = None
    if True:
        try:
            vs_settle, chg_map, sheet_sym = fetch_settle_sheet(snap["expiry"])
            qs_sym = qs_sym or sheet_sym
            iv_settle = iv_at(vs_settle, snap["F"])
            iv_settle = round(iv_settle, 2) if iv_settle is not None else None
            # ladder "(All)" ยาวถึง 3000-6000 และปีกไกลมี vol หลักร้อย (ของจริงแต่ทำให้
            # smile ที่ plot เพี้ยนหมด) -- ตัดที่ 2.5x ATM กติกาเดียวกับ smile ที่คำนวณเอง
            if iv_settle:
                vs_settle = [(s, v) for s, v in vs_settle if v <= iv_settle * 2.5]
            snap["vs_rows"] = vs_settle          # smile ที่ plot = settle ของ CME
            snap["iv_src"] = "settle"
            iv_settle_chg = iv_at(sorted(chg_map.items()), snap["F"])
            iv_settle_chg = round(iv_settle_chg, 2) if iv_settle_chg is not None else None
            print("[{:%Y-%m-%d %H:%M:%S}] settle sheet {} ok {} strikes ATM {} chg {}".format(
                now, sheet_sym, len(vs_settle), iv_settle, iv_settle_chg), file=sys.stderr)
        except Exception as e:
            print("[{:%Y-%m-%d %H:%M:%S}] settle sheet พัง (ข้าม): {}: {}".format(
                now, type(e).__name__, str(e)[:80]), file=sys.stderr)

    # IV หลักที่ใช้คิด SD = event vol ของ 0DTE (forward vol ครอบช่วงที่จบวันนี้ -- วันมี
    # event เช่น FOMC จะกว้างกว่า settle vol เอง) ไล่ fallback: event -> settle -> computed
    snap["iv_event"] = ev0.get("fwd") if ev0 else None
    snap["iv_settle"] = iv_settle
    snap["iv_settle_chg"] = iv_settle_chg
    if snap["iv_event"] is not None:
        snap["iv"], snap["iv_src"] = snap["iv_event"], "event"
    elif iv_settle is not None:
        snap["iv"], snap["iv_src"] = iv_settle, "settle"
    # IVCHG ต้องว่างเมื่อ IV เป็น event vol: ฝั่ง Pine คิด vol = IV - IVCHG ซึ่งเป็นสูตร
    # ของคู่ settle เท่านั้น เอา settle chg ไปลบ event vol จะได้ค่าที่ไม่มีความหมาย
    snap["iv_chg"] = None if snap["iv_src"] == "event" else iv_settle_chg

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

    # IVS/IVSCHG = settle vol ของ CME (คู่ที่ใช้สูตร Vol - Vol Chg ได้) เพิ่มเข้ามาใหม่ --
    # parser ฝั่ง Pine จับคีย์แบบ if ทีละตัว คีย์ที่ไม่รู้จักถูกข้ามเงียบๆ จึงเข้ากันได้กับ
    # indicator เวอร์ชันปัจจุบัน (ถ้าจะเพิ่มโหมด SD จาก settle ค่อยไปอ่านคีย์นี้)
    header = ("F:{}|D:{:%Y-%m-%d %H:%M}|S:{}|IV:{}|IVCHG:{}|DTE:{}|IVS:{}|IVSCHG:{}".format(
        meta["F"] if meta["F"] is not None else "", now, meta["series"],
        meta["iv"] if meta["iv"] is not None else "",
        iv_chg if iv_chg is not None else "",
        round(meta["dte"], 3) if meta["dte"] is not None else "",
        snap["iv_settle"] if snap.get("iv_settle") is not None else "",
        snap["iv_settle_chg"] if snap.get("iv_settle_chg") is not None else ""))
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
        "iv": meta["iv"],                # ตัวที่ใช้คิด SD จริง (ปกติ = event vol)
        "iv_chg": iv_chg,
        # event = forward vol 0DTE จาก QuikStrike EVC / settle = ATM ของ smile settle /
        # computed = Black-76 จาก bid/ask ของ barchart / inherit = ยืม clip วันเดียวกัน
        "iv_src": snap.get("iv_src"),
        "iv_event": snap.get("iv_event"),
        "iv_settle": snap.get("iv_settle"),
        "iv_settle_chg": snap.get("iv_settle_chg"),
        "qs_sym": qs_sym,                # รหัส CME ของ series เดียวกัน เช่น G2RU6
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
              (CHART_OUT, chart_html(snap, now, ev0))]
    if curve:
        writes.append((CURVE_OUT, json.dumps(curve)))
    if ev0:
        writes.append((EVENTVOL_OUT, json.dumps({"ts": now.timestamp(), "point": ev0})))
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
