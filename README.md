# Mac Desktop Widgets — Gold Price & BMA Rain Radar

Widget 2 ตัวบน desktop ของ macOS ผ่านแอป [Übersicht](https://tracesof.net/uebersicht/)
ข้อมูลถูกดึงโดย Python script ที่รันด้วย crontab แล้วเขียนเป็น JSON ใน `/tmp`
ให้ widget (JSX) อ่านไปแสดงผล — ทั้งระบบเป็น HTTP ล้วน ไม่มี headless browser

```
crontab (ทุก 5 นาที)
 ├─ gold_fetcher.py ──── loop ~290s, poll ทุก 5s ──▶ /tmp/gold_data.json ──▶ gold-update.jsx    (อ่านทุก 1.5s)
 └─ weather_fetcher.py ─ ครั้งเดียวต่อรอบ ─────────▶ /tmp/weather_meta.json ▶ radar-weather.jsx (อ่านทุก 60s)
      └─ rain_nowcast.py ─ เฉพาะ 16:00/15/30/45 ──▶ macOS Notification

crontab (รายชั่วโมง นาทีที่ 7)
 └─ cme_fetcher.py ──── ครั้งเดียวต่อรอบ ──▶ /tmp/cme_putcall.json ─────▶ cme-putcall.jsx (อ่านทุก 60s)
                                        └─▶ /tmp/cme_putcall_clip.txt ─▶ คลิก widget = pbcopy
                                             แล้วไป paste ลงช่อง "Paste P/C Data" ของ oi_block.pine (tdw_indi)
```

## ตำแหน่งไฟล์จริงที่ระบบใช้ (โฟลเดอร์นี้เป็นสำเนาเก็บ + เอกสาร)

| ไฟล์ในโฟลเดอร์นี้ | ตำแหน่ง deploy จริง |
|---|---|
| `fetchers/*.py` | `~/src/my-cronjob/` (git repo) |
| `widgets/*.jsx` | `~/Library/Application Support/Übersicht/widgets/` (git repo) |
| `old/` | เวอร์ชันแรกก่อนปรับปรุง (Playwright) เก็บไว้อ้างอิง |

crontab ปัจจุบัน:

```
*/5 * * * * /usr/bin/python3 /Users/sorachai/src/my-cronjob/weather_fetcher.py >> /tmp/weather_cron.log 2>&1
*/5 * * * * /usr/bin/python3 /Users/sorachai/src/my-cronjob/gold_fetcher.py >> /tmp/gold_cron.log 2>&1
7 * * * * /usr/bin/python3 /Users/sorachai/src/my-cronjob/cme_fetcher.py >> /tmp/cme_cron.log 2>&1
```

# Project 3: CME Put/Call Widget (Gold 0DTE)

ดึง Put/Call รายสไตรค์ (Intraday volume + Open Interest) ของ Gold option series
ใกล้หมดอายุสุด จาก **Barchart** แล้วส่งต่อขึ้น TradingView ผ่าน clipboard

- **ประวัติแหล่งข้อมูล**: เดิมใช้ CME QuikStrike Vol2Vol (พร้อม fallback pageth →
  Barchart, สร้างช่วงเหตุล่มจริง 17 ก.ค. 2026) แต่ **ก.ย. 2026 CME ถอด intraday ออก
  และใส่ bot detection โหด** → ย้าย Barchart ขึ้นเป็นแหล่งหลักตัวเดียว, ตัด Vol2Vol/pageth
  ทิ้งทั้งสาย (โค้ดยุค QuikStrike ดูได้จาก git history / โปรเจกต์ `~/src/claude_code/cme_scraping`)
- **Barchart** (feed CME ที่เขา license เอง, delayed 10-15 นาที): ก.ย. 2026 barchart
  ใส่ **AWS WAF JS challenge บนหน้า HTML ทุกหน้า** แต่ path `/proxies/core-api` ไม่โดน —
  เงื่อนไขจริงของ API มีแค่ header **`sec-fetch-site: same-origin`** (พิสูจน์ 10 ก.ย.:
  ไม่ต้องมี cookie/XSRF/WAF-token) → fetcher **ห้ามโหลดหน้า HTML** ทำทุกอย่างผ่าน API:
  - **discovery ไม่ใช้ dropdown แล้ว**: สร้างรหัส series จากตาราง `WEEK_CODES`
    (จันทร์ `IY1-5` / อังคาร `I0A-E` / พุธ `IY6-10` / พฤหัส `I0G-K` / ศุกร์ `IG1-5`
    ต่อด้วย month code + ปี เช่น `I0HU26` = พฤหัสสัปดาห์ 2 ก.ย. 26) แล้วยิง chain
    ไล่จากวันใกล้สุด — ตัวจริงยืนยันจาก `symbolName` ใน response
    ("Gold Thursday Week 2 Options Sep '26") ไม่เดาจากรหัส / series หมดอายุ = chain ว่าง
  - **chain เดียวได้ครบ**: volume, OI, lastPrice, bid/ask, `optImpliedVolatility`
    (ชื่อ field แกะจาก class ตารางหน้า volatility-greeks — `impliedVolatility` เฉยๆ
    คืน null / หน่วยเป็น % แล้ว) + underlying คิดจากกติกา monthly-option-expiry
    (weekly อ้าง GC เดือนมาตรฐานตัวใกล้สุดที่ option รายเดือนยังไม่หมด ณ วัน expiry)
  / **semantic เปลี่ยนจากยุค QuikStrike**: IV/smile เป็นค่า "ปัจจุบัน" (delayed)
  ไม่ใช่ settle เมื่อคืน และไม่มี IV Chg (ช่อง IVCHG ใน clip ว่าง — Pine รับได้อยู่แล้ว)
- **ค่า vol ทั้งหมดมาจาก QuikStrike (anonymous ได้)** ด้วย Referer trick เดิม 3 view /
  **viewitemid หาโดยจำลอง postback กดเมนูให้เซิร์ฟเวอร์เฉลยเอง** (ชื่อในเมนูใช้เป็น
  viewitemid ตรงๆ ไม่ได้ — เดาแล้วได้ error page ทุกตัว) / ทุก view เลือก expiration
  ด้วยวันหมดอายุจาก `title` ของ anchor (helper `_qs_open_expiry`):
  - `IntegratedV2VExpectedRange` (Vol2Vol) → **แท็บ Open Interest ยังมี chart payload ครบ**
    (แท็บ Intraday ว่าง): series Call/Put/Vol/**VolSettle**/Ranges + `ATMVol`, `FuturePrice`,
    `DTE` / หน่วย vol เป็นเศษส่วน (0.4499 = 44.99%) → **เส้น smile ที่ plot (`VS;`) ใช้
    เส้น VolSettle นี้** ทั้งโหมด Intraday และ OI ของ indicator และ **`IVS` = `ATMVol`**
    (vol ที่ ATM ณ F ตอน settle = ตัวเลขที่ CME โชว์เป็น VolSettle — ไม่ใช่อ่านเส้นที่ F
    ปัจจุบัน) / **ไม่โดนปิดช่วงเช้า** / ข้อจำกัด: ladder ราว 80 สไตรค์ตามกราฟ CME
    (11 ก.ย. 26: 4170–4570) ไม่มีตัวเลือกขยาย และไม่มี Vol Chg แล้ว (Subtitle ว่าง)
    / ⚠️ **OI ของ Vol2Vol ไม่ตรงกับ barchart** (11 ก.ย. เช้า: CME put/call 4,908/3,579
    vs barchart 6,455/4,929 บนสไตรค์เดียวกัน เช่น 4490C 4 vs 353) — ยังไม่ได้พิสูจน์ว่า
    ใครใหม่กว่า น่าจะเป็นคนละวันของ OI (fetcher ยังใช้ OI ของ barchart)
  - `IntegratedEventVolCalculator` (เมนู "EventVolCalculator") → **ช่อง `vol` ของจุด
    0DTE = IV หลักที่ใช้คิด SD** (ตัวเลขเดียวกับที่หน้า EVC โชว์ — ยืนยัน 11 ก.ย. 26:
    OG2U6 = 44.99) / ⚠️ **ห้ามใช้ `forwardVol`**: forward vol ที่ติดกับจุดไหนคือช่วง
    "หลัง" expiry นั้นไปถึงตัวถัดไป ไม่ใช่วันนี้ (OG2U6 fwd 18.36 = ช่วงข้ามเสาร์-อาทิตย์,
    G3WU6 16 ก.ย. fwd 44.8 = ช่วง 16→17 ที่มีประกาศ FOMC หลัง G3WU6 หมดอายุ)
    เอาเฉพาะจุด 0DTE พอ / ⚠️ ค่านี้ **re-mark ระหว่างวัน** เช้าเท่า settle แล้วขยับตามตลาด
  - `IntegratedSettlementSheet` (เมนู "Settlement Prices") → ตาราง `#pricing-sheet`
    ตัวเดียวกับที่ script ของเพื่อนอ่าน: settle vol + **Vol Chg** รายสไตรค์ของ CME →
    ตอนนี้เป็น**ที่มาเดียวของ `IVSCHG`** และเป็นสำรองของ smile เมื่อ Vol2Vol ล่ม
    (ตั้ง `ddlStrikes=(All)` แล้วตัดปีกที่ vol > 2.5×ATM ทิ้ง — ปีกไกลถึง 264%)
    / ⚠️ **ช่วงเช้าไทยตารางถูกปิด**: หน้าขึ้น "Today's settlements are not available
    for viewing until after 12:00am CT" → ได้ Vol Chg ตั้งแต่ **12:00 ไทย** (หน้าหนาว 13:00)
  - ลำดับ smile: Vol2Vol → Settlement Sheet → smile สดจาก bid/ask (JSON `smile_src`,
    กราฟเปลี่ยนป้ายเส้นเป็น "IV live" เมื่อไม่มี settle) / event vol กับ Vol2Vol ไม่โดนปิด
  - **ตรวจ smile ก่อนใช้ cache** (18 ก.ย. 26): QuikStrike เสิร์ฟ payload คนละรอบปนกันได้ —
    06:07 ไทยได้ ATMVol 25.2 แต่เส้นทั้งเส้น 39–42 (settle วัน FOMC ค้าง) กราฟจึงไม่ตรง CME
    → ถ้า |จุดต่ำสุดของเส้น − ATMVol| > `QS_SMILE_TOL` (3 จุด) ถือว่าเสีย ดึงใหม่ทันที
    (ถ้าของใหม่ยังไม่สอดคล้องอีก รอชั่วโมงหน้าค่อยลอง กันวนดึงทุกรอบ) / JSON มี `smile_ts`
    และหน้ากราฟโชว์ `smile vol2vol 09:58` ให้เห็นว่าค่าที่วาดดึงมาเมื่อไหร่
- **ลดความเสี่ยงโดน QuikStrike block** (11 ก.ย. 26):
  - **session เดียวต่อรอบ** (`QSClient`): หน้าแรกของ session ใหม่ QuikStrike redirect 3 ทอด
    (1 หน้า = 4 request) หน้าถัดไปแนบ `insid/qsid` เดิมไปเหมือนกดเมนูใน browser = 1 request
    / ตัวเก่าเปิด session ใหม่ทุกหน้า ~15 request/รอบ (~360/วัน, 72 session/วัน)
  - **cache ค่าที่นิ่งทั้งวัน**: Vol2Vol (VolSettle + ATMVol) และ Settlement Sheet (Vol Chg)
    ดึงใหม่เมื่อข้ามวัน CME (00:00 CT) **หรือ** cache เก่าเกิน 2 ชม. — ต้องมีเพดานอายุเพราะ
    12:05 ไทยวันที่ 11 Vol2Vol ยังโชว์ OI/EOD ของวันก่อน (ไม่ได้เปลี่ยนตรงเที่ยงคืน CT) /
    Settlement Sheet ที่ติดช่วงปิดจะนัดลองใหม่หลังเที่ยงคืน CT ทีเดียว ไม่ลองทุกชั่วโมง /
    Event Vol ยังดึงทุกรอบเพราะ re-mark ระหว่างวัน → รอบปกติ 4 request รอบเติม cache 9
  - cache อยู่ที่ `~/Library/Caches/cme-fetcher/qs_state.json` (**ไม่ใช่ /tmp** ซึ่ง macOS
    ล้างตอนบูต) และตัดสินจากสถานะ ไม่ใช่เวลาตายตัว → เครื่องปิด/restart ช่วงไหน รอบแรก
    หลังเปิดก็เติมส่วนที่ขาดเอง
  - **ตัวเบรก**: 403/429/เด้งหน้า login/หน้าตรวจบอท → หยุดยิง QuikStrike **12 ชม.** /
    error page ของเขา, HTTP 5xx หรือต่อไม่ได้ 2 รอบติด (ทั้งที่ barchart รอบเดียวกันผ่าน) →
    **2 ชม.** / สถานะอยู่ในไฟล์เดียวกัน รอดข้าม restart / ระหว่างพัก clip ยังออกครบ (IV ใช้
    ATMVol จาก cache) และ widget ขึ้น "⏸ QS paused → เวลา" / อยากปลดเองก่อนเวลา:
    `rm ~/Library/Caches/cme-fetcher/qs_state.json` (cache หายด้วย รอบถัดไปดึงใหม่ครบ)
  - มือถือ (Termux) ใช้กลไกเดียวกัน cache อยู่ที่ `~/cme-gold/qs_state.json` แต่ไม่นับเน็ต
    หลุดเป็นสัญญาณ (เน็ตมือถือหลุดบ่อยเป็นปกติ)
- **IV สำรองเมื่อ QuikStrike ล่ม**: barchart คืน `optImpliedVolatility=0` ทั้ง chain
  "ในวันหมดอายุของ series นั้นเอง" (หน้าเว็บจริงก็ว่าง = ทุกวันสำหรับ 0DTE) → fetcher
  **คำนวณเองแบบ Black-76** (bisection, r=0, t=dte/365 day-count เดียวกับสูตร SD) จาก
  **mid ของ bid/ask** ฝั่ง OTM — mid เป็น quote สด ต่างจาก lastPrice ที่ค้างได้ทั้งวัน /
  JSON มี `iv_src`: **event** (ปกติ) / vol2vol (ATMVol) / settle / computed / inherit
- ⚠️ **Intraday ของ barchart ต้องกรองตาม session**: ช่อง `volume` คือ volume ของ session
  ล่าสุดที่ leg นั้นมีการเทรด — สไตรค์ที่ยังไม่มีใครเทรดตั้งแต่เปิด session วันนี้ barchart
  ยังโชว์ volume ของเมื่อวานค้างไว้ (tradeTime ประทับเป็นวันที่ของ session ก่อน) พบ 11 ก.ย. 26
  09:50 ไทย: 3,821 จาก 4,553 สัญญาเป็นของเมื่อวาน → fetcher นับเฉพาะ leg ที่ `tradeTime` ≥
  เวลาเปิด session Globex ล่าสุด (17:00 CT อาทิตย์-พฤหัส = 05:00 ไทย / หน้าหนาว 06:00,
  ช่วงพัก 16:00-17:00 CT และเสาร์-อาทิตย์ได้ session ที่เพิ่งปิด) = พฤติกรรมเดียวกับแท็บ
  Intraday ของ CME เดิมที่เริ่มนับ 0 ทุก session / OI ไม่เกี่ยว (เป็นยอด EOD)
- DTE และการตัด series ที่หมดอายุคิดเป็น UTC: option ทองหมดอายุ 12:30 CT = 13:30 ET
  (00:30 ไทยหน้าร้อน / **01:30 หน้าหนาว** — ตัวเก่าตายตัวที่ 00:30)
- **Android (Termux)**: `~/src/claude_code/cme_scraping/termux/` — `cme_gold_termux.py`
  ใช้แหล่งและ format เดียวกับ fetcher นี้ (Barchart + QuikStrike, กรอง session, ±4σ)
  ติดตั้งด้วย `setup_cme_termux.sh` ไฟล์เดียว (ฝังตัวโปรแกรมไว้ข้างใน) คู่มือ `INSTALL_TH.txt`
- **ตัดสไตรค์หลุดโลก**: chain ของ barchart มีแถว strike 10,000 (put vol 90) ทั้งที่
  สไตรค์จริงไกลสุด 6,000 (หน้าเว็บ barchart ก็โชว์) → fetcher ทิ้งสไตรค์นอกช่วง
  0.5–1.5 เท่าของ F ทั้งใน clip, ยอดรวม และกราฟ
- ⚠️ **PricingSheet บน cmegroup-sso.quikstrike.net เข้าไม่ได้** (บังคับ SAML login ผ่าน
  auth.cmegroup.com, ban เป็นระดับบัญชี) — แต่ไม่ต้องใช้แล้วเพราะ Settlement Sheet
  ให้ข้อมูลชุดเดียวกันแบบ anonymous
- **cme_fetcher.py**: รายชั่วโมงพอ (Intraday สะสมทั้งวัน / OI นิ่งจนถึง refresh เช้า) เขียน
  `/tmp/cme_putcall.json` (ให้ widget) + `/tmp/cme_putcall_clip.txt` (string สำหรับ Pine)
  + `/tmp/cme_curve.json` (futures curve — ยุค barchart ได้ฟรีจาก quotes คอลเดียว
  เลยดึงทุกรอบ ไม่ต้อง gate 12 ชม. แบบเดิม; spread คิดใน feed เดียวกันเสมอ)
  + `/tmp/cme_chart.html` — **กราฟหน้าตาแบบ CME Vol2Vol** (แท่ง Put ส้ม/Call น้ำเงิน
  รายสไตรค์ สลับ Intraday/OI ได้, smile IV เส้นประแดงแกนขวา — smooth ตอน render
  ด้วย median-3 + weighted MA + Catmull-Rom โดยข้อมูลดิบใน clip ไม่ถูกแตะ,
  เส้น Future, SD band ±1-3σ วงในเข้มสุด, **cursor แบบ CME**: เส้นตั้งดูดเข้าสไตรค์ใกล้สุด
  + กล่องโชว์ Put/Call/Σ ทั้ง Intraday และ OI ของสไตรค์นั้น, Vol Settle ที่สไตรค์, delta
  และห่าง F กี่ σ — ใช้ pointer events ลากนิ้วบนมือถือได้, **ปุ่ม Δ** เปิดเส้น 5/15/25/35/45Δ
  แบบ CME ปิดไว้เป็นค่าเริ่มต้น จำค่าใน localStorage `cme.delta`) self-contained เปิด
  `open /tmp/cme_chart.html` ค้างไว้ได้ หน้า reload ตัวเองทุก 5 นาที
  / **ราคา Future สด**: gold_fetcher.py เขียน `/tmp/gold_live.js` (`window.GOLD_LIVE`)
  ทุกรอบที่เขียน gold_data.json (~5 วินาที) หน้ากราฟโหลดซ้ำผ่าน `<script src>` ทุก 5 วินาที
  (หน้า file:// ใช้ fetch อ่าน JSON ไม่ได้ แต่โหลด script ได้) → หัวกราฟโชว์ราคา + เปลี่ยนจาก
  open และเส้น Future หลักขยับตามราคาสด เส้นประจางคือราคาตอนดึงข้อมูล P/C / ใช้ราคาสด
  เฉพาะเมื่อ `sym` ตรงกับ underlying ของ series (GCV6 = GCV26) และไฟล์ไม่เก่าเกิน 3 นาที
  ไม่อย่างนั้นกลับไปใช้ F ของข้อมูล / ระยะ σ ใน cursor วัดจากราคาสด
  + `/tmp/cme_eventvol.json` — จุด event vol ของ **0DTE เท่านั้น** (vol + forward vol)
  / หัวกราฟโชว์ `VolSettle 31.54 (+3.69)` คู่กับ `EventVol 0DTE 44.99` โดย**ขีดเส้นใต้
  ตัวที่ใช้คิด SD จริง** / ส่วนเสริมจาก QuikStrike ใช้งบเวลาแยก (`QS_BUDGET` 45s)
  พังก็ข้าม ไม่กระทบข้อมูลหลักและ exit code
  / งบเวลารวม 90s (แหล่งเดียวแล้ว ไม่ต้องแบ่งงบต่อแหล่งแบบยุค fallback chain)
  exit code **2 = ฝั่งแหล่งข้อมูลล่ม** / 1 = error อื่น / 0 = ปกติ
  — ล้มเหลวแล้ว**ไม่เขียนทับไฟล์เดิม** widget ขึ้น STALE เองหลัง 2 ชม. และกด ↻ เองได้
- ⚠️ **www.cmegroup.com (WAF) แบน IP เครื่องนี้จากการ scrape แล้ว — ห้ามยิงตรง**
  (quikstrike.net เป็น infra คนละเจ้า/Bantix ใช้ Referer cmegroup.com ได้ตามเดิม)
- **เส้น delta (18 ก.ย. 26)** — `delta_levels()` ใน fetcher: ราคาที่ |delta| = 5/15/25/35/45%
  ทั้งฝั่ง put/call **คิดเองด้วย Black-76** จาก F สด + DTE จริง + IV รายสไตรค์จาก mid ของ
  bid/ask (`computed_iv_rows` ตัวเดียวกับ smile สำรอง → สะท้อนความเบ้จริง) **ไม่ยิงใครเพิ่ม**
  / bisection บนระยะห่างจาก F, ลง JSON คีย์ `delta` = `[{d, side, k}]`
  / หน้าเว็บ+widget เลื่อนเส้นทั้งชุดตาม F สด (`k + (liveF − F)`) เพราะ fetcher คิดไว้ตอนดึง
  / ซ่อนเส้นเมื่อ DTE < 0.02 หรือ smile เหลือน้อยกว่า 8 จุด (bid/ask หาย)
  / `greeks_rows()` ใส่ `chart.gk` = `[[strike, call delta, gamma]]` ไว้ใน JSON (ใช้ทำ
  ตัวชี้วัดถ่วงน้ำหนักได้ ไม่ต้องยิงเพิ่ม) — ปุ่ม Δw/γ ที่เคยลองทำ **ถอดออกแล้ว 18 ก.ย. 26**
  ตามที่เจ้าของงานสั่ง
  / **delta ของ TradingView ใช้ยืนยันได้** (`scanner.tradingview.com/options/scan2`,
  root = รหัส CME เช่น `OG3` + `underlying_symbol: COMEX:GCV2026`): delta/gamma ขึ้นกับ
  v·√t จึงตรงกับของเราแม้ **ค่า `iv` ของ TradingView ใช้ไม่ได้** — มันนับหมดอายุที่ ~16:00 CT
  (ปิด session) ไม่ใช่ 12:30 CT ทำให้ IV ต่ำกว่าจริง ~17% ที่ DTE 0.3 (ยิ่งใกล้ยิ่งเพี้ยน)
  ถ้าจะใช้ต้อง back out ใหม่จาก `theoPrice` ด้วยเวลาที่ถูก
- **cme-putcall.jsx**: สรุป P/C + ratio bar + Top Active + ช่อง IV โชว์ **event IV อย่างเดียว**
  (ขึ้น -- เมื่อดึงไม่ได้ เช่นช่วงตัวเบรกพัก; settle vol/Vol Chg ยังอยู่ใน clip คีย์ IVS/IVSCHG)
  + **กราฟ Put/Call รายสไตรค์ต่อด้านล่าง** (การ์ด 740×~713 เกือบจัตุรัส) ย่อจากหน้าเว็บ:
  แท่ง P/C, แถบ SD ±1-3σ, เส้น Vol Settle, เส้น Future สด + เส้นประราคาตอนดึงข้อมูล,
  ปุ่มสลับ Intraday/OI (กันคลิกทะลุไป copy), hover ดูดเข้าสไตรค์โชว์ P/C ทั้งสองชุด + vol + σ
  / **ปุ่มสลับแถบ SD**: `Open 0.6` (ค่าเริ่มต้น) = จุดกลางราคาเปิด + DTE 0.6 ใช้ค่าเดียวกับกล่อง
  SD Range / `CME` = จุดกลาง F ตอนดึงข้อมูล + DTE ที่เหลือจริง (แบบ Expected Range ของ CME)
  มุมซ้ายบนบอกว่ากรอบคิดจากอะไร ระยะ σ ใน hover ใช้กรอบเดียวกัน
  / **ปุ่ม Δ**: `ปิด` (ค่าเริ่มต้น) / `25Δ` (2 เส้น) / `ครบ` (5-45Δ 10 เส้น) + hover โชว์ delta
  ของสไตรค์นั้น / **ปุ่ม Δw** สลับแท่งเป็น delta-weighted, **ปุ่ม γ** เปิดแถบ gamma x OI
  (ทั้งคู่ปิดไว้เป็นค่าเริ่มต้น) / ค่าที่เลือก (ID/OI, SD, Δ, Δw, γ)
  จำใน localStorage คีย์ `cme-putcall.prefs` ไม่รีเซ็ตเมื่อ Übersicht โหลด widget ใหม่
  / ข้อมูลรายสไตรค์มาจากคีย์ `chart` ใน cme_putcall.json (fetcher เขียน ช่วง ±4σ) และราคาสด
  อ่าน `/tmp/gold_data.json` ตรงๆ (widget ไม่ติดข้อจำกัด file://) → command ต่อสองไฟล์ด้วยตัวคั่น
  `@@LIVE@@` และ refresh ทุก 5 วินาที / การ์ดยึดขอบล่าง (`bottom`) จึงสูงขึ้นไปทางด้านบน
  / ดูหน้าตาจริงโดยไม่ต้องจับภาพ desktop: เปิด `http://127.0.0.1:41416/1/` (เลข 1 = screen id
  ที่ widget ผูกอยู่ ดูได้จาก `/state/`) ในเบราว์เซอร์
  **ดับเบิลคลิก widget = เปิดกราฟ Intraday/OI** (`open /tmp/cme_chart.html` ในเบราว์เซอร์หลัก)
  / **คลิก widget = copy clip ลง clipboard** แล้วไปวางในช่อง "Paste P/C Data" ของ
  indicator `oi_block.pine` (โปรเจกต์ `tdw_indi`) / ป้าย "via ..." ขึ้นเมื่อ source
  ไม่ใช่ barchart (แหล่งหลักปัจจุบัน)
- **clip ส่งเฉพาะสไตรค์ใน F ± 4σ** โดย σ = F × IV × √(DTE ที่เหลือจริง/365) — ไม่ใช่
  DTE 0.6 (chain ของ barchart กว้างกว่า CME มาก clip เต็มยาว ~4,250 ตัวอักษร paste ลงช่อง
  text_area ของ TradingView ไม่เข้า เพดานราว 4,096) ช่วงแคบลงเองตามเวลาที่เหลือ (DTE 0.8 → ±365,
  0.3 → ±223, 0.05 → ±91) มีพื้นต่ำสุด ±25 (1 OI block) กันนาทีท้ายๆ ที่ σ หดจนเกือบไม่เหลือ /
  ถ้ายังยาวเกิน 4,000 ตัวอักษร (DTE เยอะ เช่น series วันจันทร์ตอนวันเสาร์) จะลดทีละ 0.5σ จน
  พอดี และบันทึกลง log / **ตัดเฉพาะ clip** — ยอด P/C ใน widget, JSON และกราฟยังคิดทั้ง chain
- format ของ clip: บรรทัด meta
  `F:...|D:...|S:...|IV:...|IVCHG:...|DTE:...|IVS:...|IVSCHG:...` ตามด้วย
  `ID;strike:put:call;...` และ `OI;strike:put:call;...` (เฉพาะ strike ที่ put+call > 0)
  และ `VS;strike:vol%;...` (settle vol รายสไตรค์ — ฝั่ง Pine ใช้วาด volatility smile
  และเป็น ladder ของ WormHole)
  - `IV`/`IVCHG` = ตัวที่ใช้คิด SD → ปกติ `IV` = **event vol** และ **`IVCHG` ว่างเสมอ**
    เพราะ Vol Chg เป็นของคู่ settle เอาไปลบ event vol จะไม่มีความหมาย (ฝั่ง Pine คิด
    vol = IV − IVCHG → ได้ event vol ตรงๆ ตามต้องการ)
  - `IVS`/`IVSCHG` = คู่ settle ของ CME (**คีย์ใหม่**) — parser ฝั่ง Pine จับคีย์ทีละตัว
    ด้วย if จึงข้ามคีย์ที่ไม่รู้จักเงียบๆ เข้ากันได้กับ indicator เวอร์ชันปัจจุบัน
    ถ้าจะเพิ่มโหมด SD จาก settle ค่อยไปอ่านคีย์นี้

---

# Project 1: Gold Price Widget

## ที่มาของข้อมูล

| ข้อมูล | แหล่ง | เหตุผล |
|---|---|---|
| ราคา last / change / % ของ **Gold Futures** (pair 8830) และ **XAU/USD Spot** (pair 68) | **investing.com mobile app API**<br>`https://aappapi.investing.com/get_screen.php?screen_ID=22&pair_ID={id}&lang_ID=1`<br>ต้องส่ง header `x-meta-ver: 14` | เป็นราคา realtime (lag ~5 วินาที) แหล่งเดียวกับหน้าเว็บ investing.com ที่เคย scrape ด้วย Playwright — API ฝั่ง www/api.investing.com โดน Cloudflare block แต่ API ของแอปมือถือไม่โดน |
| **ราคาเปิดวัน**ของ Futures | **Yahoo Finance** chart API<br>`https://query1.finance.yahoo.com/v8/finance/chart/GC=F` | ค่า open ของ Yahoo แม่นกว่า investing (คนละ session convention) แต่ราคา last ของ Yahoo ดีเลย์ 10 นาที (ข้อมูล CME realtime ต้องมี license) จึงใช้เฉพาะ open — ดึงครั้งเดียวต่อรอบ cron |
| วัน Settlement ของ series | จาก overview_table ของ investing (`Settlement Day`) | ใช้คำนวณ Theory Diff และจะอัปเดตเองเมื่อตลาด roll series |

แหล่งที่ลองแล้วตัดทิ้ง: CNBC quote API (ดีเลย์ 10 นาทีเท่ากัน), Swissquote public feed
(realtime แต่ไม่มี open/prev close), TradingView scanner (ต้อง auth), Yahoo spot
(symbol XAUUSD=X ถูกถอดไปแล้ว)

## กลไกของ `gold_fetcher.py`

- cron start ทุก 5 นาที → script loop ตัวเอง ~290 วินาที poll ทุก **5 วินาที** (รอบใหม่มาแทนพอดี ไม่ซ้อนกัน)
- ยิง request Futures + Spot **พร้อมกันคนละ thread** (ThreadPoolExecutor, แยก
  requests.Session คนละตัว) เพราะ Spread Diff ต้องมาจากราคา ณ จังหวะเดียวกัน
- **ห้ามใช้ค่าเก่า**: ฝั่งไหนดึงพลาด รอบนั้นเขียนฝั่งนั้นเป็น `null` และ `diff: null`
  → widget แสดง N/A (ไม่มีการเอาราคาเก่ามาคำนวณ diff เด็ดขาด)
- **Theory Diff** (cost of carry): `spot × CARRY_RATE × วันที่เหลือถึง settlement / 365`
  แล้วปัดเป็นขั้นละ 2.5 ตาม convention ของนักเทรด (2.5, 5, 7.5, 10, 12.5, ...)
  ค่า diff ทฤษฎีจะไหลลงเข้าหา 0 เมื่อใกล้ expire และกระโดดขึ้นเมื่อ roll series ใหม่
  — `CARRY_RATE = 0.02` (net carry = ดอกเบี้ย USD − gold lease rate) ปรับได้ที่หัวไฟล์
  ถ้า Δ (diff จริง − ทฤษฎี) เบี่ยงถาวร แปลว่า carry จริงเปลี่ยน ให้แก้ค่านี้
- เขียน JSON แบบ atomic (เขียน `.tmp` แล้ว `os.replace`) กัน widget อ่านไฟล์ครึ่งเดียว
- ทดสอบ: `python3 gold_fetcher.py --once` (ดึงรอบเดียวแล้วจบ)

## กลไกของ `gold-update.jsx`

- `cat /tmp/gold_data.json` ทุก **1.5 วินาที** (อ่านถี่กว่ารอบเขียน 3 เท่า กันจังหวะคร่อม)
- **ไฟ session**: ASIA 07:00–15:00 / LONDON 14:00–23:00 / NY 19:00–05:00 (เวลาไทย)
  คำนวณจากนาฬิกาเครื่องฝั่ง widget เอง — เปิด = เขียว, **LDN+NY ทับกัน (19–23 น. =
  GOLDEN TIME) = สีทอง**, ปิด = ส้ม, เสาร์–อาทิตย์ดับหมด
- **Δ Alert**: ถ้า |diff จริง − theory| > 2 (`DELTA_WARN`) ตัวเลข SPREAD DIFF กับ Δ
  เป็นสีแดง — ตามทฤษฎี basis ที่เบี้ยวจะถูก arbitrage (cash-and-carry) ลากกลับ
  ค่า fair เสมอ ไฟแดง = ตลาดหนึ่งกำลังวิ่งนำอีกตลาด หรือ carry กำลังเปลี่ยนจริง
- จุด **● STALE** สีส้ม = ข้อมูลใน JSON เก่ากว่า 3 นาที (fetcher ตาย/เน็ตหลุด)
- คลิก widget เปิด vol2vol.com

---

# Project 2: BMA Rain Radar Widget + แจ้งเตือนฝน

## ที่มาของข้อมูล

| ข้อมูล | แหล่งหลัก: เว็บ กทม. (ต้นทางจริง) | แหล่งสำรอง: TMD (mirror) |
|---|---|---|
| ภาพเรดาร์นิ่ง (แสดงบน widget) | `weather.bangkok.go.th/Radar/ImageHandlerNongchok.ashx` | `weather.tmd.go.th/pic_bmanck.jpg` |
| ภาพเรดาร์เคลื่อนไหว (nowcast) | `weather.bangkok.go.th/Radar/ImageHandlerNongchokAni.ashx` — GIF **12 frames ห่าง 5 นาที** (~55 นาทีย้อนหลัง) | `weather.tmd.go.th/pic_bmancLoop.gif` |

เรดาร์เป็นของ**สำนักการระบายน้ำ กทม. (BMA)** สถานีหนองจอก ทั้งสองแหล่งให้ภาพ
**ตัวเดียวกัน 965×800** (field `via` ใน JSON บอกว่ารอบนั้นมาจากไหน)

เหตุที่เรียงลำดับแบบนี้ + มาตรการกันโดน block (บทเรียน 2026-07-03 ที่ Imperva WAF
ของ TMD soft-block IP บ้าน — connect ได้แต่กลืน request เงียบๆ นาน ~11 ชม.):
- เว็บ กทม. เป็นหลัก: ตัว `.ashx` ต้องการแค่ header `Referer` ที่ถูกต้อง (กัน hotlink)
  ไม่ต้องมี cookie → **1 request ต่อ 5 นาที** เท่า browser ปกติ / cert chain
  ของเขาไม่ครบ ต้อง `verify=False`
- TMD จะถูกแตะ**เฉพาะรอบที่ กทม. ล่ม**เท่านั้น โอกาสสะสม request จนโดน WAF ต่ำมาก
- ไม่ retry รัวในรอบเดียว (พลาดแล้วรอ cron รอบถัดไป 5 นาที) และ loop GIF (4MB)
  ถูกดึงแค่ ~4 ครั้ง/วันตามรอบเช็คฝน
- ไฟล์นิ่งใน `weather.bangkok.go.th/Images/Radar/` เป็นของค้างเก่า (หยุดอัปเดต
  มิ.ย. 2026) **ห้ามใช้** — ต้องผ่าน ImageHandler เท่านั้น

ภาพส่งต่อเป็น JPEG เดิมไม่ re-encode (base64 ฝังใน JSON) — ต้นทางเป็น jpg อยู่แล้ว
แปลงเป็น PNG ไม่ได้ความคมคืนมา มีแต่ไฟล์บวม

## Georeference (ใจกลางของระบบตำแหน่ง)

- ศูนย์กลางวงแหวน = **สถานีเรดาร์หนองจอก `13.8348127, 100.8463349`**
  (พิกัดจริงจาก Google Maps pin) = pixel **(483, 400)** ในภาพ
- สเกล: วง 120 km มีรัศมี 399 px → **0.3008 กม./pixel**
- ผ่านการ verify กับ landmark อิสระ: ปากแม่น้ำเจ้าพระยา, ชายฝั่งบางปู, ดอนเมือง,
  สุวรรณภูมิ — ตกตรงตำแหน่งจริงทั้งหมด (แม่นระดับ ~1 กม.)
- จุดสนใจ: **Office** `13.7733, 100.5426` / **Home** `13.8873269, 100.6026284`
  → marker บน widget ที่ 38.7%/52.8% และ 41.0%/47.6% ของภาพ (จุดฟ้า = Office,
  ส้ม = Home, CSS overlay ไม่แตะตัวภาพ)
- ระวัง: สถานี "เรดาร์ตรวจอากาศ" ใน Google Maps ที่ 13.8987, 100.4656 (นนทบุรี)
  เป็นเรดาร์ของกรมอุตุฯ **คนละตัว** กับที่ผลิตภาพนี้

## กลไกของ `rain_nowcast.py` (แจ้งเตือนฝน)

ทำงานแบบ **radar nowcasting**: เห็นฝนจริงแล้วฉายการเคลื่อนที่ไปข้างหน้า

1. โหลด loop GIF → แยก pixel ฝนตามสีของ scale dBZ:
   - เขียวขึ้นไป (ฝนอ่อน ~10 dBZ+) → ใช้จับการเคลื่อนที่ (สัญญาณเยอะ)
   - **เหลือง/ส้ม/แดง/ชมพู (~31 dBZ+ = ฝนปานกลางขึ้นไป) → ใช้ตัดสินเตือน**
   - ประมวลผลบนภาพย่อ 2 เท่า (1 px ≈ 0.6 กม.) ทั้งรอบใช้เวลา < 1 วินาที
2. เทียบ mask ฝนของ frame ~30 นาทีก่อน กับ frame ล่าสุด หา shift ที่ซ้อนทับกัน
   มากสุด (mask correlation) → **motion vector** (ทิศ + ความเร็ว) — ถ้าซ้อนทับกัน
   น้อยกว่า 15% ถือว่าไม่มีทิศชัด (เช่นพายุก่อตัวกับที่) จะไม่ฉายอนาคต
3. ฉาย mask ฝนหนักไปข้างหน้าทีละ 5 นาทีจนถึง 60 นาที — ถ้าฝนอยู่ใน หรือจะเข้า
   **รัศมี 10 กม.** ของ Office/Home → แจ้งเตือน พร้อม ETA ทิศทาง ความเร็ว เช่น
   *"ฝนจะถึง Home ในอีก ~15 นาที (มาจากทิศตะวันตก ~14 กม./ชม.)"*
4. เงื่อนไขเวลา: ตัดสินใจเฉพาะ tick **16:00 / 16:15 / 16:30 / 16:45**
   **เจอครั้งเดียว = หยุดทั้งวัน** (state `/tmp/weather_notify_state.json` รีเซ็ตข้ามวัน)
5. Notification ผ่าน `osascript display notification` (ขึ้นในนาม Script Editor —
   ต้อง allow ใน Notification Settings และไม่ติด Focus/DND)

ข้อจำกัดที่ต้องรู้: เรดาร์เห็นแค่ฝนที่เกิดแล้ว มองหน้าได้ ~60 นาทีจาก 16:45
→ ฝนที่มาหลัง ~18:00 จะไม่มีการเตือน และพายุที่ก่อตัวเหนือหัวโดยไม่เคลื่อนจากไหน
จะถูกจับได้ก็ต่อเมื่อโผล่ในรัศมี 10 กม. แล้วเท่านั้น

ทดสอบ: `python3 rain_nowcast.py --test` (ข้าม gate เวลา/วัน ไม่ส่งแจ้งเตือน)
หรือ `--force` (ส่งแจ้งเตือนจริง)

## กลไกของ `weather_fetcher.py`

- ดึงหน้า `bma_nck.php` หา `<img>` ที่เป็นภาพเรดาร์ (fallback เป็น URL ตรงถ้าหน้าเปลี่ยน)
- กันภาพเสีย: ต้องได้ ≥ 5,000 bytes ถึงจะยอมรับ / เขียน JSON แบบ atomic /
  **ถ้าดึงพลาดจะไม่แตะไฟล์เดิม** widget โชว์ภาพดีล่าสุดต่อ
- เรียก `rain_nowcast.run_check()` ต่อท้ายทุกรอบ โดยแยก try/except อิสระ —
  ฝั่งภาพพังฝั่งเตือนยังทำงาน (และกลับกัน)

## กลไกของ `radar-weather.jsx`

- อ่าน JSON ทุก 60 วินาที (ภาพต้นทางอัปเดต ~5 นาที)
- เวลา update ที่ header เปลี่ยนเป็น **● สีส้ม** เมื่อภาพเก่ากว่า 20 นาที
- คลิก widget เปิดหน้า loop ของ TMD

---

# Design notes ของ widget ทั้งคู่

- Theme เลียนแบบ macOS desktop widget: พื้น `rgba(255,255,255,0.25)`, มุมโค้ง 22px,
  ฟอนต์ SF Pro, สีระบบ Apple, ความกว้าง radar = **344px** (วัดจาก widget แท้),
  gold = 290px (compact)
- **ห้ามใช้ `backdrop-filter`** — ใน Übersicht มันกระพริบ (ใส↔สีจัด) ทุกครั้งที่
  widget re-render ตามรอบ refresh
- เลขทั้งหมดใช้ `fontVariantNumeric: tabular-nums` กันตัวเลขเด้งซ้ายขวา

# Dependencies

- `/usr/bin/python3` (3.9, CommandLineTools) + `requests`, `Pillow` (ติดตั้งแบบ `pip install --user`)
- Übersicht + สิทธิ์ notification ของ Script Editor
- refresh widget ด้วย: `osascript -e 'tell application id "tracesOf.Uebersicht" to refresh'`
