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
ใกล้หมดอายุสุด จาก CME QuikStrike Vol2Vol แล้วส่งต่อขึ้น TradingView ผ่าน clipboard

- **แหล่งข้อมูล**: `cmegroup-tools.quikstrike.net/User/QuikStrikeView.aspx?pid=40&pf=6&viewitemid=IntegratedV2VExpectedRange`
  — backend auto-login ให้เมื่อ Referer เป็น cmegroup.com (ไม่ต้องมี account) GET แรกได้แท็บ
  Intraday แล้ว POST จำลอง `__doPostBack` (WebForms: ส่ง `__VIEWSTATE` กลับ + `__EVENTTARGET`
  = `...lbOI`) เพื่อสลับไปแท็บ Open Interest — ข้อมูลฝังใน HTML เป็น `$create(...Chart, {...})`
  รายละเอียดกลไก/ข้อจำกัดของข้อมูล (Vol คือ settle เมื่อคืน ฯลฯ) ดูโปรเจกต์ `~/src/claude_code/cme_scraping`
- **cme_fetcher.py**: รายชั่วโมงพอ (Intraday สะสมทั้งวัน / OI นิ่งจนถึง refresh เช้า) เขียน
  `/tmp/cme_putcall.json` (ให้ widget) + `/tmp/cme_putcall_clip.txt` (string สำหรับ Pine)
  + `/tmp/cme_curve.json` (futures curve ให้ gold_fetcher ใช้ทำ Theory Diff — ดึงทุก 12 ชม.
  เพราะ carry ขยับช้า และการดึงกิน 3 page load ซึ่งเป็นตัวถ่วงเวลาหลักตอนเซิร์ฟช้า)
- **Fallback chain: QuikStrike → pageth → Barchart** (ทดสอบครบสายกับเหตุล่มจริง 17 ก.ค.):
  - **pageth** (github mirror): เช็คความสดจาก commit ล่าสุดก่อน (>20 นาที = ตัดทิ้ง เพราะ
    บอทเขาตายพร้อม QuikStrike เสมอ — ช่วยเฉพาะเคสฝั่งเราพัง เช่น IP โดนแบน)
  - **Barchart** (feed CME อิสระ, delayed 10-15 นาที): โหลดหน้า → cookie/XSRF → core-api
    `quotes/get?list=futures.options` ได้ volume+OI รายสไตรค์เต็ม chain / discovery เลือก
    ประเภทตามวันในสัปดาห์ ("Friday Weekly Options" ฯลฯ) แล้วอ่าน dropdown สัปดาห์ทั้งลิสต์
    เลือกวันหมดอายุใกล้สุดเอง (**default ของ barchart เชื่อไม่ได้** — มัน roll ข้าม series
    ที่ยังเทรดอยู่) วันศุกร์มีรหัสสร้างตรง `IG{week}{month}{yy}` เป็น candidate เสริม
    / ไม่มี IV+smile → inherit จาก clip เดิมของวันเดียวกัน (settle นิ่งทั้งวันโดยนิยาม)
  - งบเวลาเป็น**ต่อแหล่ง** (100/30/75s) — ถ้าเป็นงบรวม แหล่งแรกที่ช้าจะกินหมดแล้วตัดสิทธิ์
    แหล่งสำรอง / JSON มี field `source` และ widget ขึ้นป้าย "via barchart" เมื่อไม่ใช่ QS
- **เวลา QuikStrike ล่ม** (เจอจริง 17 ก.ค. 2026 — DB ฝั่งเขา timeout): เซิร์ฟตอบ
  **HTTP 200 พร้อมหน้า `/Error/ErrorPage.aspx?MSG=Timeout+expired...`** ดู status code
  อย่างเดียวไม่พอ → `_check_page()` จับหน้า error/login ก่อน parse, `MAX_RUNTIME=100s`
  กันค้าง (ไม่งั้น per-socket timeout × redirect hop × retry = ค้าง 4 นาที),
  exit code **2 = ฝั่ง CME ล่ม** / 1 = error อื่น / 0 = ปกติ
  — ล้มเหลวแล้ว**ไม่เขียนทับไฟล์เดิม** widget ขึ้น STALE เองหลัง 2 ชม. และกด ↻ เองได้
- **cme-putcall.jsx**: สรุป P/C + ratio bar + Top Active + ธงแดงเมื่อ |IV Chg| > 2 (ตลาด
  reprice vol — กรอบ SD จาก settle เชื่อไม่ได้) **คลิก widget = copy clip ลง clipboard**
  แล้วไปวางในช่อง "Paste P/C Data" ของ indicator `oi_block.pine` (โปรเจกต์ `tdw_indi`)
- format ของ clip: บรรทัด meta `F:...|D:...|S:...|IV:...|IVCHG:...|DTE:...` ตามด้วย
  `ID;strike:put:call;...` และ `OI;strike:put:call;...` (เฉพาะ strike ที่ put+call > 0)
  และ `VS;strike:vol%;...` (settle vol ทุก strike — ฝั่ง Pine ใช้วาด volatility smile)

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
