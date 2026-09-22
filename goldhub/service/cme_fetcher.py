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
  - IntegratedEventVolCalculator -> ช่อง vol ของจุด 0DTE = **IV หลักที่ใช้คิด SD**
    (ไม่ใช่ forwardVol -- อันนั้นคือช่วงหลัง expiry ไปถึงตัวถัดไป)
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
from datetime import date, datetime, timedelta, timezone

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
# Vol2Vol Expected Range -- แท็บ Intraday โดนถอดข้อมูล แต่แท็บ Open Interest ยังมี
# smile "Vol Settle" รายสไตรค์ + ATMVol (ลิงก์บน cmegroup.com เป็น iframe ครอบหน้านี้)
QS_V2V_URL = ("https://cmegroup-tools.quikstrike.net/User/QuikStrikeView.aspx"
              "?pid=40&pf=6&viewitemid=IntegratedV2VExpectedRange")
QS_REFERER = "https://www.cmegroup.com/"
QS_BUDGET = 60          # งบแยกของ QuikStrike -- ห้ามกระทบข้อมูลหลัก
# สถานะที่ต้องรอดข้าม restart (macOS ล้าง /tmp ตอนบูต): cache ค่ารายวันของ QuikStrike
# + สถานะตัวเบรก
QS_STATE = os.path.expanduser("~/Library/Caches/cme-fetcher/qs_state.json")
QS_CACHE_MAX_AGE = 2 * 3600   # Vol2Vol/Settlement ดึงใหม่เมื่อข้ามวัน CME หรือ cache เก่าเกินนี้
# smile ที่ cache ไว้ "เสีย" ถ้าเส้นที่ราคา settle ไม่ตรงกับ ATMVol ของก้อนเดียวกันเกินค่านี้
# (18 ก.ย. 26 06:07: ATMVol 25.2 แต่เส้นทั้งเส้น 39-42 = ได้ payload คนละรอบมาปนกัน)
QS_SMILE_TOL = 3.0
QS_PAUSE_BLOCK = 12 * 3600    # สัญญาณโดนบล็อก (403/429/หน้า login/captcha)
QS_PAUSE_OUTAGE = 2 * 3600    # หน้า error ของเขาเอง / ต่อไม่ได้ 2 รอบติด

# คอลัมน์ของตาราง #pricing-sheet (ยืนยัน 10 ก.ย. 26 จาก header สองชั้น:
# Call[Chg,Prior,Settle] | Strike | Put[Settle,Prior,Chg] | Volatility[S,P,C] |
# BasisPointVol[S,P,C] | BlackScholesVol[S,P,C] | OpenInterest[Call,CallChg,Put,PutChg])
SHEET_STRIKE, SHEET_VOL, SHEET_VOLCHG, SHEET_NCOL = 3, 7, 9, 20

# SD จากราคาเปิดวัน (Yahoo แม่นกว่า investing — pattern เดียวกับ gold_fetcher.py)
# DTE fix 0.6 = ตัดช่วงเอเชียเช้าทิ้ง / vol = IV - IVCHG เมื่อมี chg (ยุค barchart
# ปกติไม่มี chg -> ใช้ IV ปัจจุบันตรงๆ)
YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/GC=F?interval=1d&range=1d"
SD_DTE = 0.6

# ช่วงสไตรค์ที่ส่งเข้า clip: F ± CLIP_SD × σ โดย σ ใช้ DTE ที่เหลือจริง
# CLIP_MIN_HALF กันช่วงนาทีท้ายๆ ก่อนหมดอายุที่ σ หดจนแทบไม่เหลือสไตรค์ (1 OI block)
CLIP_SD = 4
CLIP_MIN_HALF = 25
# ช่อง text_area ของ TradingView รับได้ราว 4096 ตัวอักษร (clip 4253 paste ไม่เข้า) เผื่อไว้
CLIP_MAX_CHARS = 4000

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
                   "volume,openInterest,optImpliedVolatility,tradeTime,symbolName")
# เดือนของ gold futures มาตรฐาน (G J M Q V Z) ใช้หา underlying + curve
GC_MONTHS = [2, 4, 6, 8, 10, 12]
CURVE_N = 3
MONTH_CODE = {"F": 1, "G": 2, "H": 3, "J": 4, "K": 5, "M": 6,
              "N": 7, "Q": 8, "U": 9, "V": 10, "X": 11, "Z": 12}

# รหัส weekly series ต่อวันในสัปดาห์ (n = สัปดาห์ที่ของเดือน 1-5)
# ยืนยันกับ API 10 ก.ย. 26: IY3U26="Monday Week 3", IY8U26="Wednesday Week 3",
# I0HU26="Thursday Week 2", IG2U26="Friday Week 2"
# ตารางนี้เป็นแค่ตัวเดาแรก: 15 ก.ย. 26 อังคาร Week 3 จริงคือ I0DU26 (ไม่ใช่ I0C) ขณะที่
# ต.ค. Week 1 = I0AV26 -> series_codes ลองสัปดาห์ ±1 และยืนยันจากชื่อ series ทุกครั้ง
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


def us_dst(d):
    """daylight saving ของ US: อาทิตย์ที่ 2 ของ มี.ค. ถึงอาทิตย์แรกของ พ.ย."""
    return _nth_weekday(d.year, 3, 6, 2) <= d < _nth_weekday(d.year, 11, 6, 1)


def expiry_utc(d):
    """option ทองหมดอายุ 12:30 CT = 13:30 ET -> UTC (00:30 ไทยหน้าร้อน / 01:30 หน้าหนาว)"""
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


def weekly_candidates(now_utc, horizon=9):
    """[(expiry_date, series_code)] ของ series ที่ยังไม่หมดอายุ เรียงใกล้->ไกล
    (เริ่มจากเมื่อวานตามเวลา UTC: ช่วง 00:00-00:30 ไทย series ของ "เมื่อวาน" ยังเทรดอยู่)"""
    out = []
    start = now_utc.date() - timedelta(days=1)
    for k in range(horizon):
        d = start + timedelta(days=k)
        if d.weekday() >= 5 or expiry_utc(d) <= now_utc:
            continue
        out.append((d, series_codes(d)))
    return out


def series_codes(d):
    """รหัส barchart ที่เป็นไปได้ของ series หมดอายุวัน d: ตัวเดาตามตารางก่อน แล้วสัปดาห์ ±1
    (ตารางไม่ตายตัว: ก.ย. 26 อังคารเลื่อนไปหนึ่งตัว Week 3 = I0DU26 แต่ ต.ค. Week 1 = I0AV26
    -> ตัวไหนใช่ต้องยืนยันจากชื่อ series เสมอ)"""
    n = (d.day - 1) // 7 + 1
    mc = [c for c, mm in MONTH_CODE.items() if mm == d.month][0]
    return ["{}{}{}".format(WEEK_CODES[d.weekday()](k), mc, str(d.year)[-2:])
            for k in (n, n + 1, n - 1) if 1 <= k <= 6]


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


DELTA_TARGETS = (0.05, 0.15, 0.25, 0.35, 0.45)
DELTA_MIN_DTE = 0.02          # ใกล้หมดอายุกว่านี้ delta พลิกเร็วจนเส้นไม่มีความหมาย
DELTA_MIN_ROWS = 8            # smile ที่ขาดเกินนี้ (bid/ask หาย) ซ่อนเส้นดีกว่าวาดผิด


def greeks_rows(iv_rows, F, dte, strikes):
    """[[strike, call_delta, gamma]] ต่อสไตรค์จาก smile เดียวกับเส้น delta
    ใช้ถ่วงน้ำหนัก OI/volume ในกราฟ: delta-weighted = |delta| x จำนวนสัญญา
    (= futures เทียบเท่า) / gamma-weighted = gamma x OI (จุดที่คนเฮดจ์ต้องเทรดหนักถ้าราคามา)"""
    if not iv_rows or not F or not dte or dte < DELTA_MIN_DTE or len(iv_rows) < DELTA_MIN_ROWS:
        return []
    t = dte / 365.0
    out = []
    for K in strikes:
        v = iv_at(iv_rows, K)
        if not v or v <= 0:
            continue
        sd = v / 100.0 * math.sqrt(t)
        d1 = (math.log(F / K) + 0.5 * sd * sd) / sd
        gamma = math.exp(-d1 * d1 / 2) / math.sqrt(2 * math.pi) / (F * sd)
        out.append([K, round(_ncdf(d1), 4), round(gamma, 8)])
    return out


def delta_levels(legs, F, dte, targets=DELTA_TARGETS):
    """ราคาที่ delta ของออปชัน OTM เท่ากับเป้า -> [{"d", "side", "k"}] (เส้นแบบ 25ΔP/25ΔC
    ของ CME) คิดเองด้วย Black-76: F สด + DTE จริง + IV รายสไตรค์จาก mid ของ bid/ask
    (ใช้ smile จริงจึงสะท้อนความเบ้ ไม่ใช่ IV ตัวเดียวทั้งกราฟ)
    หมายเหตุ: delta ขึ้นกับ v*sqrt(t) -- ค่าของ TradingView จึงตรงกับของเราแม้ IV ไม่ตรง"""
    if not F or not dte or dte < DELTA_MIN_DTE:
        return []
    rows = computed_iv_rows(legs, F, dte)
    if len(rows) < DELTA_MIN_ROWS:
        return []
    t = dte / 365.0

    def delta_at(K, call):
        v = iv_at(rows, K)
        if not v or v <= 0:
            return None
        sd = v / 100.0 * math.sqrt(t)
        d1 = (math.log(F / K) + 0.5 * sd * sd) / sd
        return _ncdf(d1) if call else _ncdf(d1) - 1.0

    out = []
    for target in targets:
        for call in (False, True):
            # |delta| ลดลงเมื่อ strike ห่าง F ออกไป -> bisection บนระยะห่าง
            lo, hi = (F * 1.0005, F * 2.0) if call else (F * 0.5, F * 0.9995)
            f = lambda K: (abs(delta_at(K, call) or 0) - target)
            if f(lo if call else hi) < 0 or f(hi if call else lo) > 0:
                continue                     # เป้าอยู่นอกช่วงที่ smile ครอบคลุม
            for _ in range(60):
                mid = (lo + hi) / 2
                near = f(mid) > 0            # ยังใกล้เงินเกินไป
                if call:
                    lo, hi = (mid, hi) if near else (lo, mid)
                else:
                    lo, hi = (lo, mid) if near else (mid, hi)
            out.append({"d": target, "side": "C" if call else "P",
                        "k": round((lo + hi) / 2, 1)})
    return sorted(out, key=lambda r: r["k"])


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


def _name_expiry(name):
    """'Gold Thursday Week 2 Options Sep '26 ...' -> (expiry_date, label) / None"""
    m = re.match(r"Gold (Monday|Tuesday|Wednesday|Thursday|Friday) "
                 r"Week (\d) Options ([A-Z][a-z]{2}) '(\d\d)", name or "")
    if not m:
        return None
    wd = WD_NAMES.index(m.group(1))
    month = datetime.strptime(m.group(3), "%b").month
    return _nth_weekday(2000 + int(m.group(4)), month, wd, int(m.group(2))), m.group(0)


def series_name_expiry(legs):
    """อ่านชื่อ series จาก symbolName ของ leg แรก -> (expiry_date, label)
    / None ถ้า parse ไม่ได้ (เช่นไปโดน monthly series)"""
    for v in legs.values():
        for side in ("Call", "Put"):
            got = _name_expiry(v[side].get("symbolName"))
            if got:
                return got
    return None


def probe_series_expiry(sym):
    """ยิงเบาๆ (1 leg) เอาแค่ชื่อ series -> expiry_date / None ถ้าว่าง/ไม่ใช่ weekly ทอง"""
    try:
        d = bc_api("quotes/get?symbol={}&list=futures.options&fields=symbolName"
                   "&limit=1&raw=1".format(sym))
    except SourceDown:
        raise
    except Exception:
        return None
    for row in d.get("data") or []:
        got = _name_expiry(row.get("raw", row).get("symbolName"))
        if got:
            return got[0]
    return None


# รหัส series ที่ยืนยันแล้วต่อวันหมดอายุ -- WEEK_CODES เดาผิดได้ทั้งสัปดาห์ (22 ก.ย. 26 วันอังคาร
# เดา I0DU26 แต่ของจริง I0EU26) ถ้าไม่จำ รอบ 5 นาทีจะโหลด chain ผิดตัวเต็มๆ ทิ้งทุกรอบ
# จำใน process เดียว (daemon) พอ -- รันครั้งเดียวจบแบบ cron/ปุ่ม refresh ก็แค่เดาใหม่เหมือนเดิม
# ตัวตรวจชื่อ series ยังทำงานทุกรอบ รหัสที่จำไว้ผิดเมื่อไหร่ก็ตกไปลองตัวอื่นตามปกติ
_series_memo = {}


def snapshot_barchart():
    """ดึงทุกอย่างจาก barchart ผ่าน core-api ล้วน (ห้ามโหลดหน้า HTML -- โดน WAF)"""
    today = date.today()
    now_utc = datetime.now(timezone.utc)

    def fetch_chain(sym):
        try:
            return parse_chain(bc_api("quotes/get?symbol={}&list=futures.options&fields={}"
                                      "&groupBy=strikePrice&orderBy=strikePrice&orderDir=asc"
                                      "&raw=1".format(sym, BC_CHAIN_FIELDS)))
        except SourceDown:
            raise
        except Exception:
            return {}

    # ไล่จาก series ใกล้หมดอายุสุด: ต้องได้ series ที่ "ชื่อ" บอกวันหมดอายุตรงกับวันนั้น
    # รหัสเดาผิดได้ (ได้ series ว่าง หรือได้ของสัปดาห์อื่น) -> ลองรหัสสัปดาห์ ±1 แบบยิงเบา
    # ถ้าไม่ครบทุกรหัส วันนั้นไม่มี series (วันหยุด) ข้ามไปวันถัดไป
    series = expiry = None
    legs = {}
    tried = []
    for exp_guess, syms in weekly_candidates(now_utc)[:5]:
        memo = _series_memo.get(exp_guess)
        if memo in syms:
            syms = [memo] + [x for x in syms if x != memo]
        tried.append(syms[0])
        got = fetch_chain(syms[0])
        named = series_name_expiry(got) if got else None
        if got and (named is None or named[0] == exp_guess):
            series, expiry, legs = syms[0], exp_guess, got
            break
        for alt in syms[1:]:
            if probe_series_expiry(alt) == exp_guess:
                got = fetch_chain(alt)
                if got:
                    series, expiry, legs = alt, exp_guess, got
                break
        if series:
            break
    if series is None:
        raise SourceDown("barchart: ทุก candidate ว่าง ({})".format(",".join(tried)))
    _series_memo[expiry] = series

    dte = round(max((expiry_utc(expiry) - now_utc).total_seconds(), 0) / 86400, 3)

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

    # ตัดสไตรค์ที่หลุดโลก: chain ของ barchart มีแถว strike 10,000 (put vol 90) โผล่มา
    # ขณะที่ F ~4,300 และสไตรค์จริงไกลสุดแค่ 6,000 (หน้าเว็บ barchart ก็โชว์แถวนี้)
    # สไตรค์จริงอยู่ในช่วงราว 0.7-1.4 เท่าของ F จึงตัดที่ 0.5-1.5 เท่า
    if F:
        legs = {s: v for s, v in legs.items() if 0.5 * F <= s <= 1.5 * F}

    # Intraday / OI รายสไตรค์
    # Intraday = volume ของ session นี้เท่านั้น: สไตรค์ที่ยังไม่มีใครเทรดตั้งแต่เปิด session
    # barchart ยังโชว์ volume ของ session ก่อนค้างไว้ (11 ก.ย. 26 ตอน 09:50 ไทย 3,821 จาก
    # 4,553 สัญญาเป็นของเมื่อวาน) -> นับเฉพาะ leg ที่ last trade >= เวลาเปิด session
    sess = session_open_utc(now_utc).timestamp()
    vol = lambda r: int(r.get("volume") or 0) if (r.get("tradeTime") or 0) >= sess else 0
    id_rows, oi_rows = [], []
    for s, v in sorted(legs.items()):
        pv = vol(v["Put"])
        cv = vol(v["Call"])
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
        "delta": delta_levels(legs, F, dte),
        "iv_live_rows": computed_iv_rows(legs, F, dte),
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


def clip_window(F, iv, dte, k=CLIP_SD):
    """(ล่าง, บน) ของช่วงสไตรค์ที่ส่งเข้า clip / None = ไม่มีข้อมูลพอ ส่งทั้ง chain"""
    if F is None or not iv or dte is None:
        return None
    half = max(F * iv / 100.0 * math.sqrt(max(dte, 0) / 365.0) * k, CLIP_MIN_HALF)
    return F - half, F + half


def chart_rows(meta, snap, id_rows, oi_rows):
    win = clip_window(meta["F"], meta["iv"] or snap.get("iv_settle"), meta["dte"])
    inwin = (lambda s: win[0] <= s <= win[1]) if win else (lambda s: True)
    ks = sorted({s for s, _, _ in id_rows} | {s for s, _, _ in oi_rows})
    return {
        "id": [[s, p, c] for s, p, c in id_rows if inwin(s)],
        "oi": [[s, p, c] for s, p, c in oi_rows if inwin(s)],
        "vs": [[s, v] for s, v in snap["vs_rows"] if inwin(s)],
        # greeks ต่อสไตรค์ให้กราฟถ่วงน้ำหนักเอง (delta-weighted / gamma-weighted)
        "gk": greeks_rows(snap.get("iv_live_rows") or [], meta["F"], meta["dte"],
                          [s for s in ks if inwin(s)]),
    }


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


class QSBlocked(Exception):
    """สัญญาณว่า QuikStrike ไม่อยากให้เข้า (หรือล่มอยู่) -> ตัวเบรกหยุดยิงไป pause วินาที"""
    def __init__(self, msg, pause):
        super().__init__(msg)
        self.pause = pause


class SettleEmbargo(RuntimeError):
    """Settlement Sheet ปิดให้ดูจนถึง 00:00 CT -- ไม่ใช่ความผิดปกติ"""


# ข้อผิดพลาดที่ต้องหยุด QuikStrike ทั้งรอบ (ไม่ใช่แค่ข้ามหน้านั้น)
QS_NETFAIL = (socket.timeout, urllib.error.URLError, ConnectionError, SourceDown)
QS_ESCALATE = (QSBlocked,) + QS_NETFAIL
BLOCK_MARKERS = ("captcha", "access denied", "request rejected", "request unsuccessful",
                 "awswaf", "just a moment", "unusual traffic")


def qs_state_load():
    try:
        return json.load(open(QS_STATE))
    except Exception:
        return {}


def qs_state_save(st):
    os.makedirs(os.path.dirname(QS_STATE), exist_ok=True)
    tmp = QS_STATE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(st, f)
    os.replace(tmp, QS_STATE)


def ct_day(now_utc):
    """วันที่ตามเวลา Chicago -- QuikStrike เปลี่ยนชุด settlement ตามวันของ CME"""
    return (now_utc - timedelta(hours=5 if us_dst(now_utc.date()) else 6)).date()


def next_ct_midnight(now_utc):
    d = ct_day(now_utc) + timedelta(days=1)
    return datetime(d.year, d.month, d.day, 5 if us_dst(d) else 6, tzinfo=timezone.utc)


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


class QSClient:
    """session เดียวต่อรอบ: หน้าแรก QuikStrike จะ redirect เติม insid/qsid (instance ของ
    session) ให้ แล้วหน้าถัดไปแนบค่าเดิมไปด้วยแบบเดียวกับกดเมนูใน browser -- ไม่สร้าง
    session ใหม่ทุกหน้า และหน้าที่ 2 เป็นต้นไปไม่ต้องเสีย request ให้ redirect"""

    def __init__(self):
        self.op = _qs_opener()
        self.inst = None
        self.ref = QS_REFERER

    def _open(self, req):
        try:
            return self.op.open(req, timeout=_budget(35))
        except urllib.error.HTTPError as e:
            if e.code in (403, 429):
                raise QSBlocked("HTTP {}".format(e.code), QS_PAUSE_BLOCK)
            if e.code >= 500:
                raise QSBlocked("HTTP {}".format(e.code), QS_PAUSE_OUTAGE)
            raise

    def get(self, view_url):
        url = view_url + ("&" + self.inst if self.inst else "")
        r = self._open(urllib.request.Request(url, headers={"User-Agent": UA, "Referer": self.ref}))
        html, final = r.read().decode(), r.geturl()
        _qs_check_page(html, final)
        m = re.search(r"insid=\d+&qsid=[0-9a-f-]+", final)
        if m:
            self.inst = m.group(0)
        self.ref = final
        return final, html

    def postback(self, url, html, target, extra=None):
        try:
            body = _qs_postback(self.op, url, html, target, extra)
        except urllib.error.HTTPError as e:
            if e.code in (403, 429):
                raise QSBlocked("HTTP {}".format(e.code), QS_PAUSE_BLOCK)
            if e.code >= 500:
                raise QSBlocked("HTTP {}".format(e.code), QS_PAUSE_OUTAGE)
            raise
        _qs_check_page(body)
        return body


def _parse_sheet(html):
    """ตาราง #pricing-sheet -> ([(strike, vol_settle)], {strike: vol_chg})"""
    # CME ปิดการแสดง settlement ของรอบล่าสุดจนถึงเที่ยงคืน CT (= 12:00 ไทย หน้าร้อน /
    # 13:00 หน้าหนาว) ช่วงเช้าไทยหน้าจึงว่างทั้งหน้า -- ไม่ใช่ความผิดปกติ ใช้ smile สดแทน
    if "settlements are not available for viewing" in html:
        raise SettleEmbargo("settle sheet ถูกปิดจนถึง 00:00 CT (12:00 ไทย) -- ยังไม่มี Vol Chg")
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


def _qs_open_expiry(view_url, expiry, extra_fn=None, qs=None):
    """เปิด view ของ QuikStrike แล้วเลือก expiration ที่หมดอายุวันที่ expiry
    -> (op, url, html หลังเลือก, qs_sym)

    default ของแต่ละ view ไม่แน่ว่าเป็น 0DTE (Settlement Sheet เปิดมาเป็น series ถัดไป)
    จึงเลือกเองด้วย postback ทุกครั้ง / จับคู่จาก attribute title ของ anchor ซึ่งมีข้อมูล
    ครบ (ชื่อสัญลักษณ์อยู่ใน <div> ข้างในอีกที ใช้ text ของ anchor จับไม่ได้):
      title="Option Contract:\tSep 2026
             Option Expiration:\t9/10/2026 (0.31 DTE)
             Option Symbol:\t\tG2RU6 ..."
    จับด้วย "วันหมดอายุ" ไม่ใช่ชื่อ -- barchart กับ QuikStrike ใช้คนละระบบรหัส
    (I0HU26 vs G2RU6) วันหมดอายุเป็นตัวเชื่อมเดียวที่เชื่อได้
    extra_fn(html) -> dict ของ field เพิ่มที่ส่งไปกับ postback นี้ด้วย
    qs = QSClient ของรอบนี้ (ไม่ส่งมา = เปิด session ใหม่)"""
    qs = qs or QSClient()
    url, html = qs.get(view_url)
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
        raise RuntimeError("ไม่เจอ expiration {} ใน selector".format(want))
    html = qs.postback(url, html, target, extra_fn(html) if extra_fn else None)
    return qs.op, url, html, qs_sym


def fetch_settle_sheet(expiry, qs=None):
    """settle vol + Vol Chg รายสไตรค์จาก Settlement Sheet -> (vs_rows, chg_map, qs_sym)
    ตอนนี้ใช้หลักๆ เพื่อเอา Vol Chg (Vol2Vol ไม่มีแล้ว) และเป็นสำรองของ smile"""
    # ddlStrikes = -1 คือ "(All)" -- default ของหน้าคือ 25 สไตรค์รอบ ATM
    all_strikes = lambda h: {n: "-1" for n in _qs_selects(h) if n.endswith("ddlStrikes")}
    _, _, html, qs_sym = _qs_open_expiry(QS_SETTLE_URL, expiry, all_strikes, qs)
    vs, chg = _parse_sheet(html)
    return vs, chg, qs_sym


def fetch_v2v_smile(expiry, qs=None):
    """smile "Vol Settle" จาก Vol2Vol แท็บ Open Interest -> (vs_rows, atm_vol, F, qs_sym)

    แท็บ Intraday ของ Vol2Vol โดนถอดข้อมูลไปแล้ว (ก.ย. 2026) แต่แท็บ OI ยังส่ง chart
    payload ครบ: series Call/Put/Vol/VolSettle/Ranges + ATMVol, FuturePrice, DTE
    หน่วย vol เป็นเศษส่วน (0.4499 = 44.99%) / ไม่โดนปิดช่วงเช้าแบบ Settlement Sheet
    ข้อจำกัด: ladder แคบตามกราฟของ CME (ราว 80 สไตรค์) และไม่มี Vol Chg แล้ว"""
    qs = qs or QSClient()
    _, url, html, qs_sym = _qs_open_expiry(QS_V2V_URL, expiry, qs=qs)
    tab = re.search(r"__doPostBack\(&#39;([^&]*\$lbOI)&#39;", html)
    if not tab:
        raise RuntimeError("Vol2Vol: ไม่เจอแท็บ Open Interest")
    html = qs.postback(url, html, tab.group(1))
    i = html.find("$create(UserControlsV2.QuikOptionsV")
    if i < 0:
        raise RuntimeError("Vol2Vol: แท็บ OI ไม่มี chart payload")
    m = re.search(r'"JSONSettings":"((?:[^"\\]|\\.)*)"', html[i:])
    d = json.loads(m.group(1).encode().decode("unicode_escape"))
    if qs_sym and not (d.get("Title") or "").startswith(qs_sym):
        raise RuntimeError("Vol2Vol: ได้ series {!r} ไม่ใช่ {}".format(d.get("Title"), qs_sym))
    vs = []
    for p in (d.get("VolSettle") or {}).get("data") or []:
        if p.get("x") and p.get("y"):
            k = float(p["x"])
            vs.append((int(k) if k == int(k) else k, round(float(p["y"]) * 100, 2)))
    if not vs:
        raise RuntimeError("Vol2Vol: series VolSettle ว่าง")
    atm = d.get("ATMVol")
    return (sorted(vs), round(atm * 100, 2) if atm else None,
            d.get("FuturePrice"), qs_sym)


def _qs_check_page(html, url=""):
    """จับหน้า error/login ของ QuikStrike (ตอบ HTTP 200 ทั้งคู่ -- ดู status ไม่พอ)
    แยกสามแบบ: โดนบล็อก (เบรก 12 ชม.) / ระบบเขาล่ม (เบรก 2 ชม.) / บั๊กฝั่งเรา (แค่ข้าม)"""
    if "/Account/Login.aspx" in url:
        raise QSBlocked("เด้งไปหน้า login", QS_PAUSE_BLOCK)
    head = html[:5000].lower()
    if any(k in head for k in BLOCK_MARKERS) and "pricing-sheet" not in head:
        raise QSBlocked("หน้าตรวจบอท/ปฏิเสธ", QS_PAUSE_BLOCK)
    if "/Error/ErrorPage.aspx" in url or "QuikStrike Error" in html[:3000]:
        m = re.search(r"MSG=([^&]*)", url)
        msg = urllib.parse.unquote_plus(m.group(1)).strip()[:80] if m else "ไม่ทราบสาเหตุ"
        if "unknown view" in msg:
            raise RuntimeError("QuikStrike error page: " + msg)
        raise QSBlocked("error page: " + msg, QS_PAUSE_OUTAGE)


def fetch_eventvol(qs=None):
    """[{sym, expires, dte, vol, fwd}] จาก QuikStrike Event Volatility Calculator
    (ตัวเสริม -- QuikStrike ล่ม/เปลี่ยนโครงเมื่อไหร่ก็ข้าม ไม่กระทบข้อมูลหลัก)
    ข้อมูลฝังใน HTML เป็น $create(...EventVol.Calculator.Chart, {"JSONSettings": ...})
    แบบเดียวกับ Vol2Vol ยุคเก่า / vol = ATM vol ของ expiration, fwd = forward vol
    ของช่วงจาก expiration นี้ไปถึงตัวถัดไป -> fwd ที่โดดจากเพื่อน = ช่วงนั้นมี event"""
    _, html = (qs or QSClient()).get(QS_EVC_URL)
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
 svg{background:#f5f5f5;border:1px solid #e2e2e2;border-radius:4px;display:block}
 #wrap{position:relative;display:inline-block}
 #tip{position:absolute;pointer-events:none;display:none;background:rgba(255,255,255,.97);
      border:1px solid #bbb;border-radius:5px;box-shadow:0 2px 8px rgba(0,0,0,.18);
      padding:7px 10px;font-size:12px;line-height:1.5;white-space:nowrap;color:#222}
 #tip .k{font-size:14px;font-weight:700}
 #tip .d{color:#999;font-weight:400;font-size:11px}
 #tip table{border-collapse:collapse;margin-top:3px}
 #tip td{padding:0 0 0 10px;text-align:right}
 #tip td:first-child{padding-left:0;text-align:left;color:#777}
 #tip tr.on td{font-weight:700}
 #tip .p{color:#e8940c}#tip .c{color:#3b6fd6}#tip .v{color:#c0392b}
</style></head><body>
<div id="hdr">
 <span id="title"></span>
 <span id="totals"></span>
 <span id="live"></span>
 <span id="mode">
  <span id="legend"><span class="sw" style="background:#f5a623"></span>Put
   <span class="sw" style="background:#4a80e8"></span>Call
   <span style="color:#c0392b;margin-left:10px">- - -</span> <span id="smlbl">Vol Settle</span></span>
  <button id="bId">Intraday</button><button id="bOi">OI</button>
  <button id="bDelta" title="เส้น 5/15/25/35/45 delta (คิดจาก bid/ask ของ barchart)">&#916;</button>
 </span>
</div>
<div id="wrap"><svg id="c" width="960" height="600"></svg><div id="tip"></div></div>
<div id="upd"></div>
<script>
const D = __DATA__;
let mode = "id";
// เส้น delta: ปิดไว้ก่อน กดเปิดเอง (จำค่าที่เลือกไว้ข้ามการ refresh ทุก 5 นาที)
let dOn = false;
try { dOn = localStorage.getItem("cme.delta") === "1"; } catch (e) {}
// greeks ต่อสไตรค์จาก fetcher: [strike, call delta, gamma]
const GK = new Map((D.gk || []).map(r => [r[0], {cd: r[1], g: r[2]}]));
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
  document.getElementById("smlbl").textContent = D.iv_settle != null ? "Vol Settle" : "IV live (bid/ask)";
  document.getElementById("bId").className = mode === "id" ? "on" : "";
  document.getElementById("bOi").className = mode === "oi" ? "on" : "";
  document.getElementById("bDelta").className = dOn ? "on" : "";
  document.getElementById("upd").textContent = "updated " + D.updated + " · " + D.series +
    (D.qs_sym ? " (" + D.qs_sym + ")" : "") + " on " + D.und + " · DTE " + D.dte +
    " · P/C barchart delayed 10-15m · smile " + (D.smile_src || "-") +
    (D.smile_ts ? " " + D.smile_ts : "") + " · SD IV " + D.iv_src +
    " · ขีดเส้นใต้ = ตัวที่ใช้คิด SD";
  if (!rows.length) return;
  // โดเมนแกน x: ±3.5σ รอบ F (ไม่งั้นปีก OI ลากกราฟกว้างจนแท่งกลางจมหาย)
  const sig = (D.F && D.iv && D.dte > 0) ? D.F * D.iv / 100 * Math.sqrt(D.dte / 365) : null;
  let lo = Math.min(...rows.map(r => r[0])), hi = Math.max(...rows.map(r => r[0]));
  if (sig && D.F){ lo = Math.max(lo, D.F - 3.5 * sig); hi = Math.min(hi, D.F + 3.5 * sig); }
  lo -= 5; hi += 5;
  const x = v => L + (v - lo) / (hi - lo) * (W - L - R);
  const vrows = rows.filter(r => r[0] >= lo && r[0] <= hi);
  const ymax = Math.max(...vrows.map(r => Math.max(r[1], r[2]))) * 1.08 || 1;
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
    el("text", {x: L - 6, y: y(v) + 4, "text-anchor": "end", "font-size": 11, fill: "#888"}, svg)
      .textContent = fmt(Math.round(v));
  }
  // แท่ง Put(ส้ม)/Call(น้ำเงิน) เคียงกันต่อ strike
  const stepX = vrows.length > 1 ? Math.min(...vrows.slice(1).map((r, i) => r[0] - vrows[i][0])) : 5;
  const bw = Math.max(1.5, (x(lo + stepX) - x(lo)) * 0.36);
  for (const [s, p, c] of vrows){
    const tip = s + "  Put " + fmt(p) + "  Call " + fmt(c) + "  Total " + fmt(p + c);
    if (p) el("rect", {x: x(s) - bw - 0.5, y: y(p), width: bw, height: y(0) - y(p), fill: "#f5a623"}, svg, tip);
    if (c) el("rect", {x: x(s) + 0.5, y: y(c), width: bw, height: y(0) - y(c), fill: "#4a80e8"}, svg, tip);
  }
  // เส้น delta แบบ CME: 5/15/25/35/45Δ ทั้งสองฝั่ง ป้ายตั้งที่หัวเส้น (วาดทับแท่งแบบจางๆ)
  // เส้นคิดไว้ตอน fetcher ดึงข้อมูล (F ตอนนั้น) -- เลื่อนทั้งชุดตาม F สด ให้ยังเป็น delta เดิม
  const dShift = (liveF() != null && D.F) ? liveF() - D.F : 0;
  if (dOn) for (const d0 of (D.delta || [])){
    const d = {d: d0.d, side: d0.side, k: d0.k + dShift};
    if (d.k < lo || d.k > hi) continue;
    const px = x(d.k), lbl = Math.round(d.d * 100) + "Δ" + d.side;
    el("line", {x1: px, x2: px, y1: T, y2: H - B, stroke: "#8a8a8a", "stroke-width": 1,
                "stroke-dasharray": "5 4", opacity: 0.55}, svg, lbl + " = " + d.k.toFixed(1));
    el("text", {x: px - 4, y: T + 6, "font-size": 11, fill: "#9a9a9a", "text-anchor": "end",
                transform: "rotate(-90 " + (px - 4) + " " + (T + 6) + ")"}, svg).textContent = lbl;
  }
  // smile IV แกนขวา (เส้นประแดง) -- ค่า computed มี noise จาก bid/ask spread
  // เลย smooth ตอน render: median-3 กัน outlier + moving average ถ่วงน้ำหนัก
  // แล้ววาดเป็น Catmull-Rom spline (ข้อมูลดิบใน clip/VS ไม่ถูกแตะ)
  const vs = smooth(D.vs.filter(r => r[0] >= lo && r[0] <= hi));
  let yr = null;
  if (vs.length > 2){
    let vlo = Math.min(...vs.map(r => r[1])), vhi = Math.max(...vs.map(r => r[1]));
    const pad = (vhi - vlo) * 0.15 + 0.5; vlo -= pad; vhi += pad;
    yr = v => T + (1 - (v - vlo) / (vhi - vlo)) * (H - T - B);
    el("path", {d: splinePath(vs.map(r => [x(r[0]), yr(r[1])])),
                fill: "none", stroke: "#e05252", "stroke-width": 1.6, "stroke-dasharray": "6 4", opacity: 0.9}, svg);
    for (let k = 0; k <= 5; k++){
      const v = vlo + (vhi - vlo) * k / 5;
      el("text", {x: W - R + 6, y: yr(v) + 4, "font-size": 11, fill: "#888"}, svg).textContent = v.toFixed(1);
    }
    el("text", {x: W - 12, y: H / 2, "font-size": 11, fill: "#aaa",
                transform: "rotate(90 " + (W - 12) + " " + H / 2 + ")", "text-anchor": "middle"}, svg).textContent = "Volatility";
  }
  // แกน x
  const t0 = Math.ceil(lo / 50) * 50;
  for (let s = t0; s <= hi; s += 50)
    el("text", {x: x(s), y: H - B + 18, "text-anchor": "middle", "font-size": 11, fill: "#666"}, svg).textContent = fmt(s);
  el("text", {x: 16, y: H / 2, "font-size": 11, fill: "#aaa",
              transform: "rotate(-90 16 " + H / 2 + ")", "text-anchor": "middle"}, svg).textContent =
    mode === "id" ? "Intraday Volume" : "Open Interest";
  G = {svg, T, H, B, lo, hi, x};
  drawLive();
  cursor(svg, {W, H, L, R, T, B, lo, hi, x, yr, vs, sig, stepX});
}

// cursor แบบ CME: เส้นตั้งตามเมาส์ ดูดเข้าสไตรค์ใกล้สุด + กล่องค่า Put/Call ของสไตรค์นั้น
// โชว์ทั้ง Intraday และ OI (โหมดที่ดูอยู่ตัวหนาอยู่บน) + vol ที่สไตรค์ + ห่างจาก F กี่ σ
// ใช้ pointer events จึงลากนิ้วบนมือถือได้ด้วย / overlay โปร่งใสบังทับ <title> ของแท่งเดิม
function interp(rows, k){
  if (!rows.length) return null;
  if (k <= rows[0][0]) return k === rows[0][0] ? rows[0][1] : null;
  for (let i = 1; i < rows.length; i++)
    if (k <= rows[i][0]){
      const [k0, v0] = rows[i - 1], [k1, v1] = rows[i];
      return v0 + (v1 - v0) * (k - k0) / (k1 - k0);
    }
  return null;
}
// delta ณ สไตรค์ใดๆ: interpolate จากเส้น delta ที่ fetcher คำนวณมา (แปลงฝั่ง put เป็น
// delta ของ call ก่อน: put -0.25 = call 0.75) แล้วคืนค่าเป็น |delta| ของฝั่ง OTM
function deltaAt(k){
  const sh = (liveF() != null && D.F) ? liveF() - D.F : 0;
  const lv = (D.delta || []).map(d => [d.k + sh, d.side === "P" ? 1 - d.d : d.d]);
  if (lv.length < 2) return null;
  const cd = interp(lv, k);
  if (cd == null) return null;
  return k >= (liveF() ?? D.F) ? cd : 1 - cd;
}
function cursor(svg, g){
  const tip = document.getElementById("tip");
  tip.style.display = "none";
  const idm = new Map(D.id.map(r => [r[0], r])), oim = new Map(D.oi.map(r => [r[0], r]));
  const ks = [...new Set([...D.id, ...D.oi].map(r => r[0]))]
    .filter(k => k >= g.lo && k <= g.hi).sort((a, b) => a - b);
  if (!ks.length) return;
  const cur = el("g", {visibility: "hidden", "pointer-events": "none"}, svg);
  const band = el("rect", {y: g.T, height: g.H - g.T - g.B, fill: "rgba(0,0,0,0.07)"}, cur);
  const line = el("line", {y1: g.T, y2: g.H - g.B, stroke: "#222", "stroke-width": 1, "stroke-dasharray": "3 3"}, cur);
  const dot = el("circle", {r: 4, fill: "#e05252", stroke: "#fff", "stroke-width": 1.5}, cur);
  const lblBg = el("rect", {y: g.H - g.B + 3, height: 17, rx: 3, fill: "#222"}, cur);
  const lbl = el("text", {y: g.H - g.B + 15.5, "text-anchor": "middle", "font-size": 11,
                          "font-weight": 700, fill: "#fff"}, cur);
  const ov = el("rect", {x: g.L, y: g.T, width: g.W - g.L - g.R, height: g.H - g.T - g.B,
                         fill: "transparent", style: "cursor:crosshair;touch-action:pan-y"}, svg);
  const cell = (r, i) => r ? fmt(r[i]) : "0";
  const row = (name, r, on) =>
    '<tr' + (on ? ' class="on"' : '') + '><td>' + name + '</td>' +
    '<td class="p">P ' + cell(r, 1) + '</td><td class="c">C ' + cell(r, 2) + '</td>' +
    '<td>Σ ' + (r ? fmt(r[1] + r[2]) : "0") + '</td></tr>';
  function show(ev){
    const bb = svg.getBoundingClientRect();
    const px = (ev.clientX - bb.left) * g.W / bb.width;
    const py = (ev.clientY - bb.top) * g.H / bb.height;
    const v = g.lo + (px - g.L) / (g.W - g.L - g.R) * (g.hi - g.lo);
    let k = ks[0];
    for (const s of ks) if (Math.abs(s - v) < Math.abs(k - v)) k = s;
    const X = g.x(k), bw = Math.max(4, g.x(g.lo + g.stepX) - g.x(g.lo));
    band.setAttribute("x", X - bw / 2); band.setAttribute("width", bw);
    line.setAttribute("x1", X); line.setAttribute("x2", X);
    lbl.textContent = fmt(k);
    const tw = lbl.getComputedTextLength ? lbl.getComputedTextLength() + 12 : 44;
    lblBg.setAttribute("x", X - tw / 2); lblBg.setAttribute("width", tw); lbl.setAttribute("x", X);
    const vk = interp(g.vs, k);
    if (g.yr && vk != null){
      dot.setAttribute("cx", X); dot.setAttribute("cy", g.yr(vk)); dot.setAttribute("visibility", "visible");
    } else dot.setAttribute("visibility", "hidden");
    cur.setAttribute("visibility", "visible");
    // ค่า vol ในกล่องใช้ของดิบ (ตัวเลขของ CME) ส่วนจุดบนเส้นใช้ค่าที่ smooth ให้ตรงกับเส้นที่วาด
    const vraw = interp(D.vs, k);
    const fNow = liveF() ?? D.F;
    const dist = (g.sig && fNow) ? (k - fNow) / g.sig : null;
    const rows = mode === "id"
      ? row("Intraday", idm.get(k), true) + row("OI", oim.get(k), false)
      : row("OI", oim.get(k), true) + row("Intraday", idm.get(k), false);
    const dl = deltaAt(k);
    tip.innerHTML = '<div class="k">' + fmt(k) +
      (dist != null ? ' <span class="d">' + (dist >= 0 ? "+" : "") + dist.toFixed(2) + 'σ จาก F</span>' : '') +
      '</div><table>' + rows + '</table>' +
      (vraw != null ? '<div class="v">' + (D.iv_settle != null ? "Vol Settle " : "IV ") +
                      vraw.toFixed(2) + '%</div>' : '') +
      (dl != null ? '<div class="d">&#916; ' + dl.toFixed(2) + (k >= fNow ? 'C' : 'P') + '</div>' : '');
    tip.style.display = "block";
    const sx = bb.width / g.W, sy = bb.height / g.H;
    let left = X * sx + 14;
    if (left + tip.offsetWidth > bb.width - 4) left = X * sx - tip.offsetWidth - 14;
    let top = Math.min(Math.max(py * sy - tip.offsetHeight / 2, 4), bb.height - tip.offsetHeight - 4);
    tip.style.left = left + "px"; tip.style.top = top + "px";
  }
  function hide(){ cur.setAttribute("visibility", "hidden"); tip.style.display = "none"; }
  ov.addEventListener("pointermove", show);
  ov.addEventListener("pointerdown", show);
  ov.addEventListener("pointerleave", hide);
}
document.getElementById("bId").onclick = () => { mode = "id"; render(); };
document.getElementById("bOi").onclick = () => { mode = "oi"; render(); };
document.getElementById("bDelta").onclick = () => {
  dOn = !dOn;
  try { localStorage.setItem("cme.delta", dOn ? "1" : "0"); } catch (e) {}
  render();
};
// ---- ราคา Future สด: gold_fetcher.py เขียน /tmp/gold_live.js ทุก ~5 วินาที ----
// หน้านี้เปิดแบบ file:// จึง fetch JSON ไม่ได้ ต้องโหลดซ้ำผ่าน <script src> แทน
// ใช้เฉพาะเมื่อสัญญาตรงกับ underlying ของ series (GCV6 = GCV26) และไฟล์ไม่เก่าเกิน 3 นาที
let G = null;
function liveF(){
  const L = window.GOLD_LIVE;
  if (!L || !L.price || !L.sym || !D.und) return null;
  const und = D.und.slice(0, 3) + D.und.slice(-1);
  if (L.sym !== und || Date.now() / 1000 - L.ts > 180) return null;
  return L.price;
}
function vline(p, attrs, label, dark){
  if (!G || p <= G.lo || p >= G.hi) return;
  const X = G.x(p), g = el("g", {class: "fline"}, G.svg);
  el("line", Object.assign({x1: X, x2: X, y1: G.T, y2: G.H - G.B}, attrs), g);
  const t = el("text", {x: X + 4, y: G.T + 13, "font-size": 11, "font-weight": dark ? 700 : 400,
                        fill: dark ? "#fff" : "#888"}, g);
  t.textContent = label;
  if (dark){
    const w = t.getComputedTextLength() + 8;
    const bg = el("rect", {x: X, y: G.T + 1, width: w, height: 17, rx: 3, fill: "#222"}, g);
    g.insertBefore(bg, t);
  }
}
function drawLive(){
  const f = liveF(), L = window.GOLD_LIVE;
  const box = document.getElementById("live");
  if (f != null){
    const ch = L.change_open;
    box.innerHTML = '&nbsp;Future <b>' + fmt(f) + '</b>' +
      (ch != null ? ' <span style="color:' + (ch >= 0 ? '#1a8f45' : '#c0392b') + '">' +
                    (ch >= 0 ? '+' : '') + ch + ' จาก open</span>' : '') +
      ' <span style="color:#999;font-size:12px">live ' + L.time + '</span>';
  } else {
    box.innerHTML = D.F ? '&nbsp;Future <b>' + fmt(D.F) + '</b> <span style="color:#999;font-size:12px">' +
                          'ตอนดึงข้อมูล ' + D.updated.slice(11) + '</span>' : '';
  }
  if (!G) return;
  G.svg.querySelectorAll(".fline").forEach(n => n.remove());
  if (f != null){
    if (D.F) vline(D.F, {stroke: "#999", "stroke-width": 1, "stroke-dasharray": "3 4"},
                   "data " + fmt(D.F), false);
    vline(f, {stroke: "#111", "stroke-width": 1.6}, "Future " + fmt(f), true);
  } else if (D.F){
    vline(D.F, {stroke: "#333", "stroke-width": 1.2, "stroke-dasharray": "5 3"}, "Future " + fmt(D.F), true);
  }
  // เส้นต้องอยู่ใต้ overlay ของ cursor ไม่งั้นบังการชี้เมาส์
  const ov = G.svg.querySelector('rect[style*="crosshair"]');
  if (ov) G.svg.querySelectorAll(".fline").forEach(n => G.svg.insertBefore(n, ov));
}
function pollLive(){
  const s = document.createElement("script");
  s.src = "gold_live.js?t=" + Date.now();
  s.onload = () => { s.remove(); drawLive(); };
  s.onerror = () => { s.remove(); drawLive(); };
  document.head.appendChild(s);
}
render();
pollLive();
setInterval(pollLive, 5000);
</script></body></html>
"""


def chart_html(snap, now, ev=None):
    payload = {
        "series": snap["series"], "und": snap.get("und_sym"), "F": snap["F"],
        "dte": snap["dte"], "iv": snap["iv"], "iv_src": snap.get("iv_src"),
        "iv_event": snap.get("iv_event"), "iv_settle": snap.get("iv_settle"),
        "iv_settle_chg": snap.get("iv_settle_chg"), "qs_sym": snap.get("qs_sym"),
        "smile_src": snap.get("smile_src"), "smile_ts": snap.get("smile_ts"),
        "delta": snap.get("delta") or [],
        "updated": "{:%Y-%m-%d %H:%M}".format(now),
        "id": [list(r) for r in snap["id_rows"]],
        "oi": [list(r) for r in snap["oi_rows"]],
        "vs": [list(r) for r in snap["vs_rows"]],
        "gk": greeks_rows(snap.get("iv_live_rows") or [], snap["F"], snap["dte"],
                          sorted({r[0] for r in snap["id_rows"]} | {r[0] for r in snap["oi_rows"]})),
        "ev": ev or [],
    }
    return CHART_TMPL.replace("__DATA__", json.dumps(payload))


def main(use_qs=True, baseline=True):
    """หนึ่งรอบ snapshot -- คืน dict ข้อมูลรายสไตรค์ให้ ticker ใช้ต่อในหน่วยความจำ

    use_qs=False (เฟส 3, รอบ 5 นาทีของ daemon): **ไม่แตะ QuikStrike เลย** ใช้ event vol /
    Vol2Vol / settle จาก cache ล้วน -- request ไป CME ต้องเท่าเดิม (ชั่วโมงละรอบ)
    baseline=False: ไม่เขียน PREV_STATE ทับ ให้ "Δ CHANGES SINCE" ยังเทียบกับรอบรายชั่วโมง
    (ไม่งั้นจะกลายเป็นเทียบ 5 นาทีก่อนโดยไม่ตั้งใจ)
    ค่า default = พฤติกรรมเดิมทุกอย่าง (cron เก่า / ปุ่ม refresh ของ widget)"""
    global _deadline
    now = datetime.now()
    _deadline = time.monotonic() + MAX_RUNTIME

    # แหล่งเดียว: barchart (CME/QuikStrike Vol2Vol ถูกถอดออก ก.ย. 2026)
    snap = snapshot_barchart()
    snap = inherit_same_day(snap)

    # ---- ส่วนเสริมจาก QuikStrike (งบเวลาแยก / พังก็ข้าม ไม่กระทบข้อมูลหลักและ exit code) ----
    # ลดความเสี่ยงโดน block (11 ก.ย. 26):
    #  - Event Vol re-mark ระหว่างวัน -> ดึงทุกรอบ / จับจุด 0DTE ด้วยวันหมดอายุ
    #  - Vol2Vol (VolSettle + ATMVol) กับ Settlement Sheet (Vol Chg) เป็นค่า settle นิ่งทั้งวัน
    #    -> ดึงครั้งเดียวต่อ series ต่อ "วันของ CME" (QuikStrike เปลี่ยนชุดที่ 00:00 CT)
    #    cache อยู่ใน ~/Library/Caches ให้รอดข้าม restart และตัดสินจากสถานะ ไม่ใช่เวลาตายตัว
    #    (เครื่องปิดไปช่วงไหน รอบแรกหลังเปิดก็เติมส่วนที่ขาดเอง)
    #  - ทุกหน้าใช้ session เดียวกัน (QSClient)
    #  - ตัวเบรก: เจอสัญญาณโดนบล็อก -> หยุดยิง QuikStrike ชั่วคราว ระหว่างนั้นใช้ cache
    _deadline = time.monotonic() + QS_BUDGET
    now_utc = datetime.now(timezone.utc)
    now_ts = now_utc.timestamp()
    st = qs_state_load()
    cache = st.get("cache") or {}
    if cache.get("expiry") != snap["expiry"].isoformat():
        cache = {"expiry": snap["expiry"].isoformat()}
    day = ct_day(now_utc).isoformat()
    # cache ใช้ได้ถ้ายังเป็นวัน CME เดียวกันและอายุไม่เกิน 4 ชม. -- 11 ก.ย. 12:05 ไทย
    # Vol2Vol ยังโชว์ OI/EOD ของวันก่อนอยู่ (ไม่ได้เปลี่ยนตรง 00:00 CT) จึงต้องมีเพดานอายุด้วย
    fresh = lambda e: bool(e) and e.get("ct_day") == day and now_ts - e.get("ts", 0) < QS_CACHE_MAX_AGE

    def smile_ok(e):
        """smile กับ ATMVol ต้องมาจาก settle รอบเดียวกัน: จุดต่ำสุดของเส้น (รูปตัว U)
        ต้องอยู่ใกล้ ATMVol ถ้าห่างมาก = payload คนละรอบ ใช้ไม่ได้"""
        if not e or not e.get("vs") or e.get("atm") is None:
            return True                      # ไม่มีของให้ตรวจ -> ปล่อยผ่าน
        return abs(min(v for _, v in e["vs"]) - e["atm"]) <= QS_SMILE_TOL
    ev0 = None
    ev_fresh = False
    qs_sym = cache.get("qs_sym")

    def qlog(msg):
        print("[{:%Y-%m-%d %H:%M:%S}] {}".format(now, msg), file=sys.stderr)

    if not use_qs:
        # รอบ Barchart-only: event vol ล่าสุดของ series นี้จาก cache (ดึงไว้รอบรายชั่วโมง)
        e = cache.get("ev")
        if e and now_ts - e.get("ts", 0) < QS_CACHE_MAX_AGE:
            ev0 = e.get("point")
    elif now_ts < st.get("paused_until", 0):
        qlog("QuikStrike paused ถึง {:%d %b %H:%M} ({}) -- ใช้ cache".format(
            datetime.fromtimestamp(st["paused_until"]), st.get("pause_reason")))
    else:
        qs = QSClient()
        try:
            try:
                for p in fetch_eventvol(qs):
                    if datetime.strptime(p["expires"], "%m/%d/%Y").date() == snap["expiry"]:
                        ev0, qs_sym = p, p["sym"]
                        ev_fresh = True
                        cache["ev"] = {"ts": now_ts, "point": p}
                        break
                qlog("eventvol 0DTE {}".format(ev0))
            except QS_ESCALATE:
                raise
            except Exception as e:
                qlog("eventvol พัง (ข้าม): {}: {}".format(type(e).__name__, str(e)[:80]))

            stale_smile = not smile_ok(cache.get("v2v")) and now_ts >= cache.get("v2v_next_try", 0)
            if stale_smile:
                qlog("vol2vol cache ไม่สอดคล้อง (ATMVol {} vs เส้นต่ำสุด {}) -- ดึงใหม่".format(
                    cache["v2v"].get("atm"), min(v for _, v in cache["v2v"]["vs"])))
            if not fresh(cache.get("v2v")) or stale_smile:
                try:
                    vs_v2v, atm, _, sym = fetch_v2v_smile(snap["expiry"], qs)
                    cache["v2v"] = {"ct_day": day, "ts": now_ts, "vs": vs_v2v, "atm": atm}
                    qs_sym = qs_sym or sym
                    if not smile_ok(cache["v2v"]):
                        # CME เสิร์ฟของไม่สอดคล้องเอง -- อย่าวนดึงทุกรอบ รอชั่วโมงหน้า
                        cache["v2v_next_try"] = now_ts + 3600
                    qlog("vol2vol {} ok {} strikes ATMVol {} (cache {} ชม.)".format(
                        sym, len(vs_v2v), atm, QS_CACHE_MAX_AGE // 3600))
                except QS_ESCALATE:
                    raise
                except Exception as e:
                    qlog("vol2vol พัง (ข้าม): {}: {}".format(type(e).__name__, str(e)[:80]))

            if not fresh(cache.get("settle")) and now_ts >= cache.get("settle_next_try", 0):
                try:
                    vs_settle, chg_map, sym = fetch_settle_sheet(snap["expiry"], qs)
                    cache["settle"] = {"ct_day": day, "ts": now_ts, "vs": vs_settle,
                                       "chg": sorted(chg_map.items())}
                    qs_sym = qs_sym or sym
                    qlog("settle sheet {} ok (cache {} ชม.)".format(sym, QS_CACHE_MAX_AGE // 3600))
                except SettleEmbargo as e:
                    # ปิดให้ดูจนถึง 00:00 CT -- ไม่ต้องลองทุกชั่วโมง รอรอบหลังเที่ยงคืน CT ทีเดียว
                    cache["settle_next_try"] = next_ct_midnight(now_utc).timestamp()
                    qlog("{} -- ลองใหม่หลัง {:%H:%M}".format(e, datetime.fromtimestamp(cache["settle_next_try"])))
                except QS_ESCALATE:
                    raise
                except Exception as e:
                    qlog("settle sheet พัง (ข้าม): {}: {}".format(type(e).__name__, str(e)[:80]))
            st["net_fail"] = 0
        except QSBlocked as e:
            st["paused_until"], st["pause_reason"] = now_ts + e.pause, str(e)
            qlog("⚠️ QuikStrike {} -> หยุดยิง {} ชม.".format(e, e.pause // 3600))
        except QS_NETFAIL as e:
            # barchart ในรอบเดียวกันผ่านแล้ว = เน็ตเราปกติ แต่ไป QuikStrike ไม่ได้ -- นับสะสม
            # 2 รอบติดค่อยเบรก (รอบเดียวอาจเป็นแค่เน็ตสะดุด)
            st["net_fail"] = st.get("net_fail", 0) + 1
            qlog("QuikStrike ต่อไม่ได้ ({}: {}) ครั้งที่ {}".format(type(e).__name__, str(e)[:60], st["net_fail"]))
            if st["net_fail"] >= 2:
                st["paused_until"] = now_ts + QS_PAUSE_OUTAGE
                st["pause_reason"] = "ต่อไม่ได้ {} รอบติด".format(st["net_fail"])
                qlog("⚠️ หยุดยิง QuikStrike {} ชม.".format(QS_PAUSE_OUTAGE // 3600))
    if use_qs:
        # รอบ Barchart-only ไม่เขียน state ของ QuikStrike (ไม่ได้แตะอะไร จะได้ไม่ชนกับ process อื่น)
        if qs_sym:
            cache["qs_sym"] = qs_sym
        st["cache"] = cache
        qs_state_save(st)
    qs_paused = now_ts < st.get("paused_until", 0)

    # ค่าที่ใช้ มาจาก cache เสมอ (รอบนี้เพิ่งดึง หรือของเดิมของ series เดียวกัน)
    iv_settle = iv_settle_chg = atm_v2v = None
    smile_src = None
    if cache.get("v2v"):
        snap["vs_rows"] = [tuple(r) for r in cache["v2v"]["vs"]]
        atm_v2v = cache["v2v"]["atm"]
        # IVS = ATMVol ของ CME เอง (vol ที่ ATM ณ F ตอน settle -- ตัวเลขที่ CME โชว์เป็น
        # VolSettle) ไม่ใช่อ่านเส้นที่ F ปัจจุบัน: 11 ก.ย. 26 ATMVol 44.99 = เส้นที่ 4,374
        # (F settle) ส่วนที่ F 4,338 ตอนเช้าได้ 45.29
        iv_settle = atm_v2v if atm_v2v is not None else iv_at(snap["vs_rows"], snap["F"])
        smile_src = "vol2vol"
    if cache.get("settle"):
        iv_settle_chg = iv_at([tuple(r) for r in cache["settle"]["chg"]], snap["F"])
        if smile_src is None:
            vs_settle = [tuple(r) for r in cache["settle"]["vs"]]
            iv_settle = iv_at(vs_settle, snap["F"])
            # ladder "(All)" ยาวถึง 3000-6000 และปีกไกลมี vol หลักร้อย (ของจริงแต่ทำให้
            # smile ที่ plot เพี้ยนหมด) -- ตัดที่ 2.5x ATM กติกาเดียวกับ smile ที่คำนวณเอง
            if iv_settle:
                vs_settle = [(k, v) for k, v in vs_settle if v <= iv_settle * 2.5]
            snap["vs_rows"] = vs_settle
            smile_src = "settle sheet"
    iv_settle = round(iv_settle, 2) if iv_settle is not None else None
    iv_settle_chg = round(iv_settle_chg, 2) if iv_settle_chg is not None else None
    snap["smile_src"] = smile_src or "live"
    smile_at = (cache.get("v2v") if smile_src == "vol2vol" else cache.get("settle")) or {}
    snap["smile_ts"] = "{:%H:%M}".format(datetime.fromtimestamp(smile_at["ts"])) if smile_at.get("ts") else None

    # IV หลักที่ใช้คิด SD = ช่อง "vol" ของจุด 0DTE (ตัวเลขที่หน้า EVC โชว์)
    # ⚠️ ห้ามใช้ "fwd": forward vol ที่ติดกับจุดไหนคือช่วง "หลัง" expiry นั้นไปถึง expiry
    # ถัดไป ไม่ใช่วันนี้ (11 ก.ย. 26: OG2U6 vol 44.99 แต่ fwd 18.36 = ช่วงข้ามเสาร์-อาทิตย์)
    # ไล่ fallback: event -> ATMVol ของ Vol2Vol (ตัวเลขเดียวกันเมื่อยังไม่ re-mark)
    # -> settle -> computed
    snap["iv_event"] = ev0.get("vol") if ev0 else None
    snap["iv_settle"] = iv_settle
    snap["iv_settle_chg"] = iv_settle_chg
    if snap["iv_event"] is not None:
        snap["iv"], snap["iv_src"] = snap["iv_event"], "event"
    elif atm_v2v is not None:
        snap["iv"], snap["iv_src"] = atm_v2v, "vol2vol"
    elif iv_settle is not None:
        snap["iv"], snap["iv_src"] = iv_settle, "settle"
    # IVCHG ใส่ได้เฉพาะเมื่อ IV เป็น settle: ฝั่ง Pine คิด vol = IV - IVCHG ซึ่งเป็นสูตร
    # ของคู่ settle เท่านั้น เอา settle chg ไปลบ event vol หรือ ATMVol ที่ re-mark แล้ว
    # จะได้ค่าที่ไม่มีความหมาย
    snap["iv_chg"] = iv_settle_chg if snap["iv_src"] == "settle" else None
    snap["qs_sym"] = qs_sym

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
    # clip ตัดให้เหลือ F ± 4σ (DTE ที่เหลือจริง ไม่ใช่ 0.6) -- chain ของ barchart กว้างกว่า
    # CME มากจน paste ลงช่องของ indicator ไม่พอ / ยอดรวมใน JSON/กราฟยังคิดทั้ง chain
    # ถ้ายังยาวเกินเพดาน (DTE เยอะ เช่นเช้ามืดหรือ series วันจันทร์ตอนเสาร์) ลดทีละ 0.5σ
    def build_clip(k):
        win = clip_window(meta["F"], meta["iv"] or snap.get("iv_settle"), meta["dte"], k)
        inwin = (lambda s: win[0] <= s <= win[1]) if win else (lambda s: True)
        return "\n".join([
            header,
            "ID;" + ";".join("{}:{}:{}".format(s, p, c) for s, p, c in id_rows if inwin(s)),
            "OI;" + ";".join("{}:{}:{}".format(s, p, c) for s, p, c in oi_rows if inwin(s)),
            "VS;" + ";".join("{}:{:.2f}".format(s, v) for s, v in vs_rows if inwin(s)),
        ]) + "\n"
    clip_k = CLIP_SD
    clip = build_clip(clip_k)
    while len(clip) > CLIP_MAX_CHARS and clip_k > 1:
        clip_k -= 0.5
        clip = build_clip(clip_k)
    if clip_k < CLIP_SD:
        print("[{:%Y-%m-%d %H:%M:%S}] clip ยาวเกิน {} ตัวอักษร -> ลดช่วงเหลือ ±{}σ".format(
            now, CLIP_MAX_CHARS, clip_k), file=sys.stderr)

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
        "smile_src": snap.get("smile_src"),  # vol2vol / settle sheet / live
        "smile_ts": snap.get("smile_ts"),    # เวลาที่ดึง smile ของ CME มา (cache ได้ถึง 2 ชม.)
        # เส้น delta แบบ CME (5/15/25/35/45Δ) คิดเองจาก bid/ask -- ไม่ได้ยิงใครเพิ่ม
        "delta": snap.get("delta") or [],
        # ตัวเบรก QuikStrike: paused_until = epoch ที่จะกลับมายิงอีก (None = ปกติ)
        "qs": {"paused_until": st.get("paused_until") if qs_paused else None,
               "reason": st.get("pause_reason") if qs_paused else None},
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
        # ข้อมูลรายสไตรค์ให้กราฟใน widget (ช่วง ±4σ เดียวกับ clip แต่ไม่ถูกบีบตามความยาว)
        "chart": chart_rows(meta, snap, id_rows, oi_rows),
        "changes": changes,
    }

    new_state = json.dumps({
        "series": meta["series"], "time": "{:%H:%M}".format(now),
        "id": {str(s): [p, c] for s, p, c in id_rows},
        "oi": {str(s): [p, c] for s, p, c in oi_rows},
    })
    writes = [(JSON_OUT, json.dumps(data, ensure_ascii=False)),
              (CLIP_OUT, clip),
              (CHART_OUT, chart_html(snap, now, ev0))]
    if baseline:
        writes.append((PREV_STATE, new_state))
    if curve:
        writes.append((CURVE_OUT, json.dumps(curve)))
    if ev_fresh:          # ts ของไฟล์นี้ = เวลาที่ดึงจาก QuikStrike จริง ไม่ใช่เวลาที่ยืม cache
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
    return {
        "ts": now.timestamp(), "series": meta["series"], "und_sym": snap.get("und_sym"),
        "F": meta["F"], "dte": meta["dte"], "iv_settle_chg": snap.get("iv_settle_chg"),
        "id_rows": id_rows, "oi_rows": oi_rows,
        "iv_live_rows": snap.get("iv_live_rows") or [],
    }


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
