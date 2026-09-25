# แผนย้ายเป็น apphub — ทำเป็นเฟส

หลักการของทุกเฟส: **ของเดิมต้องใช้งานได้ตลอด** แต่ละเฟสมีเงื่อนไข "ถือว่าเสร็จ",
วิธีทดสอบ และวิธีถอยกลับที่ทำได้ภายในไม่กี่นาที

สถานะตอนเริ่มแผน (20 ก.ย. 2026): cron 3 บรรทัดรัน `~/src/my-cronjob/*.py`,
Übersicht โหลด widget จาก `~/Library/Application Support/Übersicht/widgets/`,
มือถือรัน Termux ที่ scrape เองทั้งหมด

---

## เฟส 0 — จับ baseline ไว้เทียบ ✅ เสร็จ 20 ก.ย. 2026

ถ้าไม่มีตัวเทียบ จะไม่รู้ว่าเฟสถัดไปทำให้ค่าเพี้ยนไหม

- เก็บ output ของรอบ cron ปัจจุบันไว้: `cme_putcall.json`, `cme_putcall_clip.txt`,
  `gold_data.json`, `cme_chart.html` ลง `_archive/baseline-YYYYMMDD/`
- จดค่าที่ต้องตรงกันหลังย้าย: `series`, `F`, `dte`, `iv_event`, ยอด intraday/OI,
  ความยาว clip, จำนวน strike ใน chart

**ผลจริง** เก็บไว้ที่ `_archive/baseline-20260920/` (output ของรอบ cron 10:07 + crontab เดิม
+ `BASELINE.json` ที่สรุปค่าสำคัญ)

---

## เฟส 1 — daemon ตัวเดียวแทน cron ✅ เสร็จ 21 ก.ย. 2026

เป้าหมายคือ **เปลี่ยนตัวขับเคลื่อน ไม่เปลี่ยนพฤติกรรม** output ต้องเหมือนเดิมทุกไบต์
(ยกเว้น timestamp) ยังไม่มี API ยังไม่เพิ่มฟีเจอร์ ยังไม่เปลี่ยนคาบ

**ไฟล์ที่ทำ**
- `common/hub/` — skeleton: `scheduler.py` (งาน + คาบ + timeout + try/except ต่อ งาน +
  รู้เวลาตลาดปิด), `store.py` (atomic write + data dir + retention 7 วัน + cap 200 MB),
  `health.py`, `log.py`
- `goldhub/service/app.py` — ประกาศงาน: ราคาสดทุก 5 วิ, cme ทุกชั่วโมง (คงคาบเดิมไว้ก่อน),
  housekeeping วันละครั้ง
- `goldhub/service/cme_fetcher.py` / `gold_fetcher.py` — แก้ให้ถูกเรียกเป็นฟังก์ชันได้
  (แยก `main()` ออกจาก side effect) **ห้ามแตะ logic การดึงข้อมูล**
- `goldhub/deploy/com.apphub.goldhub.plist` — launchd `RunAtLoad` + `KeepAlive`
  log ไป `~/Library/Logs/apphub/goldhub.log`

**ย้าย state ที่หายไม่ได้** จาก /tmp ไป `~/Library/Application Support/apphub/goldhub/`
(`qs_state.json` ย้ายไปแล้ว ที่เหลือคือ baseline ของ ticker ในเฟส 3)
ไฟล์ /tmp ทุกตัวยังเขียนเหมือนเดิมตามที่ตกลงไว้

**ทดสอบ**
1. ปิด cron บรรทัด cme ก่อน (comment ไว้ ไม่ลบ) แล้วรัน daemon แบบ foreground
2. รอ 2 รอบ เทียบ `cme_putcall.json` กับ baseline ทีละ field
3. ดึงปลั๊ก: kill process ดูว่า launchd ปลุกใหม่จริง
4. ทดสอบเครื่อง sleep แล้วตื่น ดูว่างานกลับมาเดินเอง

**เสร็จเมื่อ** ค่าตรง baseline, launchd ปลุกเองได้, cron ฝั่ง cme ปิดถาวร
(gold_fetcher ย้ายตามมาแล้ว 21 ก.ย. — เหลือ weather ที่ยังเป็น cron รอเฟส 4)
**ถอยกลับ** `bash goldhub/deploy/install.sh uninstall` แล้ว uncomment cron — 1 นาที

**ผลทดสอบ 20 ก.ย. 11:00** รัน daemon แบบ foreground หนึ่งรอบ เทียบกับ baseline:
ตรงกันทุกค่า (series IY3U26, F 4390.7, iv_event 14.93, intraday 1190/1371, OI 2625/3246,
chart rows 67/69/52, clip 2020 ตัวอักษร) ต่างแค่ DTE กับ timestamp ตามเวลาที่เดินไป
รอบใช้เวลา 8.3 วินาที / health เขียนลง store ถูกต้อง / นัดรอบถัดไป 11:07 ตรงกับนาทีของ cron เดิม

**เหลือสองคำสั่งที่ต้องรันเอง** (sandbox ของ session แก้ crontab และสั่ง launchctl ไม่ได้)
ดูท้ายไฟล์นี้

**ย้าย gold_fetcher เข้ามาแล้ว 21 ก.ย. 09:55** — ปิดบรรทัด cron ของ gold (comment ไว้)
และเพิ่มงาน `gold` คาบ 5 วินาทีใน daemon ผ่าน `goldhub/service/gold_job.py`

- `gold_fetcher.py` **ไม่ถูกแก้เลย** — gold_job เรียก `gf.tick()` เองทุกรอบ แทนที่จะเรียก
  `main()` ที่วนเองจนครบ 290 วินาทีแล้วจบ (`RUN_SECONDS`/`--once` เลยไม่ถูกใช้ในโหมด daemon)
- ของที่เดิมทำครั้งเดียวต่อรอบ cron ต้องมีคนสั่งเอง ไม่งั้นค้างข้ามวัน: gold_job เรียก
  `refresh()` ทุก 300 วินาที = ดึง open ของวันจาก Yahoo ใหม่ + เปิดโอกาสให้ `due()` ของ
  anchor/spread ทำงานตามรอบวันของมัน
- **ตัดการต่อตรงไป CME ออกจาก gold แล้ว** เดิม `fetch_cme_anchor()` ยิง QuikStrike วันละครั้ง
  เพื่อหาสัญญาที่ 0DTE อ้างอิง ตอนนี้อ่าน `und_sym` ที่ cme_fetcher resolve ไว้ใน
  `/tmp/cme_putcall.json` ถ้าไม่มีไฟล์ค่อยใช้ `underlying_for()` ซึ่งคิดจากปฏิทินล้วนๆ
  ไม่แตะเน็ต -> เหลือทางเดียวที่แตะ CME คือ cme_fetcher ที่มีตัวเบรกของตัวเอง
- สัญญาอ้างอิงเปลี่ยนเมื่อไหร่ ต้องล้าง `roll_state` ด้วย ไม่งั้น spread ที่คิดไว้เป็นของคู่สัญญาเดิม
  (เดิมไม่มีปัญหานี้เพราะ process เกิดใหม่ทุก 5 นาที)
- แถมสองอย่างที่จำเป็นเพราะมีงานคาบสั้น: `scheduler` log error ซ้ำเฉพาะตอนข้อความเปลี่ยน
  (+ บรรทัด "กลับมาปกติ (พลาดไป N รอบ)") และ `health` หน่วงการเขียนไฟล์เหลืออย่างมาก 15 วินาที
  ส่วน `log()` เขียนทีละบรรทัดใต้ล็อก เพราะ print จากหลาย thread ทำบรรทัดซ้อนกันจริง

**ผลทดสอบ 21 ก.ย. 09:52–09:57** gold 25 รอบใน 126 วินาที (คาบ 5.0 วิ พอดี) fails 0
ค่าตรงกับของ cron ทุกช่อง: `Gold Futures (Oct 26)` anchored=True sym GCV6 open 4381.8
spread Dec->Oct 34.2 / `gold_live.js` อัปเดตทุก 5 วินาทีไม่ขาดช่วงอีกแล้ว
(เดิมเงียบ ~10 วินาทีทุกต้นรอบ cron)

---

## เฟส 2 — เปิด HTTP API แล้วให้หน้าจอดึงผ่าน API ✅ เสร็จ 22 ก.ย. 2026

**ไฟล์ที่ทำ**
- `common/hub/server.py` — `ThreadingHTTPServer`, routing สั้นๆ, `ETag`/`If-None-Match`,
  CORS, token ผ่าน query string (ปิดได้), bind เฉพาะ 127.0.0.1 ในเฟสนี้
- `goldhub/service/api.py` — `/api/state` (มี `schema_version`, รองรับ `?fields=`),
  `/api/clip` (text/plain), `/api/chart` (หน้ากราฟที่เดิมเขียนเป็นไฟล์), `/api/flat`, `/api/health`
- `goldhub/widgets/cme-putcall.jsx` — เปลี่ยน `command` เป็น `fetch('http://127.0.0.1:8787/api/state')`
  **แบบมีทางถอย**: ถ้า fetch พังให้กลับไปอ่านไฟล์ /tmp แบบเดิม
  (ยืนยันแล้วว่า Übersicht มี `NSAllowsArbitraryLoads: true` จึงยิง http ไป localhost ได้)

**ทดสอบ**
- `curl -s localhost:8787/api/health | python3 -m json.tool`
- ยิงซ้ำด้วย `If-None-Match` ต้องได้ `304`
- เปิด `/api/chart` ในเบราว์เซอร์ เทียบกับ `/tmp/cme_chart.html`
- ปิด daemon แล้วดูว่า widget ตกไปอ่านไฟล์ได้จริง

**เสร็จเมื่อ** widget ใช้ API เป็นทางหลัก และ fallback ทำงานเมื่อ daemon ดับ
**ถอยกลับ** widget มีสวิตช์ในไฟล์ ตั้งกลับเป็นโหมดไฟล์อย่างเดียว

**ผลทดสอบ 22 ก.ย. 10:15–10:18**
- ทุก route ตอบถูก: `/api/state` (มี `schema_version` + `age` เป็นวินาที) · `?fields=live` คืนแค่ที่ขอ ·
  `/api/flat` 58 บรรทัด · `/api/health` · 404 · POST ได้ 501 (อ่านอย่างเดียวจริง)
- `If-None-Match` ได้ 304 · CORS `*` มา · Host แปลก (`evil.example.com`) ได้ 403 = กัน DNS rebinding
- `/api/clip` และ `/api/chart` ตรงกับไฟล์ /tmp ทุกไบต์ · เปิด `/api/chart` ในเบราว์เซอร์แล้ว
  ราคาสดขึ้น (หน้ากราฟขอ `gold_live.js` แบบ relative จึงต้องมี route `/api/gold_live.js`)
- **fallback ทดสอบของจริง**: ติดตั้ง widget ใหม่ตอน API ยังไม่ขึ้น → footer ขึ้น `Sync 10:07 · file`
  ข้อมูลครบทุกช่อง → เปิด API → footer เหลือ `Sync 10:16` (มาทาง API)

**ตัดสินใจระหว่างทำ**
- API **อ่านจากไฟล์ /tmp ตาม mtime** ไม่ใช่เก็บผลของ daemon ไว้ในหน่วยความจำ เพราะปุ่ม refresh
  ยังรัน fetcher เป็น process แยก ถ้าจำแค่ผลของ daemon กด refresh แล้วจอจะค้างของเก่าจนรอบชั่วโมง
- ปุ่ม refresh **ยังรัน fetcher เอง** ไม่ได้เปลี่ยนเป็นยิง API เพราะกฎข้อ 1 (API ห้ามสั่งดึง upstream)
  แต่ย้าย path ไปเป็นสำเนาใน apphub แล้ว (เนื้อหาเหมือน my-cronjob ทุกไบต์)
- พอร์ตชน/เปิด API ไม่ได้ → log แล้วเดินต่อ งานดึงข้อมูลห้ามพังเพราะ API
- widget ยังส่งข้อมูลต่อให้ render ในรูปแบบ string เดิม (cme + `@@LIVE@@` + gold) โค้ดวาดกราฟไม่ต้องแตะเลย

---

## เฟส 3 — เปลี่ยนคาบเป็น 5 นาที + ticker ✅ เสร็จ 23 ก.ย. 2026

**ไฟล์ที่ทำ**
- `goldhub/service/app.py` — snapshot Barchart เป็นทุก 5 นาที ส่วน QuikStrike
  ยังรายชั่วโมง + cache 2 ชม. + ตัวเบรกเหมือนเดิม (ห้ามเพิ่ม request ไป CME)
- `goldhub/service/ticker.py` — เขียนใหม่จาก `cme_ticker.py.old`:
  diff ยอดสะสมกับรอบก่อน, กัน `dp < 0` (session ใหม่ล้างยอด), FIFO ตามจำนวน,
  Most Active แบบ rate, ประวัติ ATM IV จาก bid/ask
  state ไปอยู่ที่ Application Support (รอด reboot ต่างจากของเดิมที่อยู่ /tmp)
- `goldhub/widgets/cme-ticker.jsx` — ต่อกับ `/api/state` (ส่วน ticker)
- **แยก baseline ของ "Δ CHANGES SINCE"** ให้ยังเทียบรายชั่วโมงเหมือนเดิม
  ไม่ให้กลายเป็นเทียบ 5 นาทีโดยไม่ตั้งใจ

**ของแถมที่ทำได้เพราะเป็น Barchart** ตรวจว่า event หนึ่งเป็นก้อนเดียวหรือทยอย
ด้วยข้อมูลรายนาที ยิงเฉพาะ strike ที่เข้าเกณฑ์ **จำกัดไม่เกิน 3 ตัวต่อรอบ**

**ทดสอบ**
- เทียบ event ที่ ticker จับได้กับข้อมูลรายนาทีของ Barchart ย้อนหลัง
- นับจำนวน request จริงต่อวัน ต้องอยู่ราว 860 ครั้งไป Barchart และ **ไม่เพิ่ม**ไป CME
- ปล่อยข้ามคืนหนึ่งรอบ ดูว่าตอน series roll (00:30 ไทย) ประวัติถูกล้างถูกต้อง

**เสร็จเมื่อ** ticker เดินได้ข้ามวันโดยไม่มี event ปลอม และ request ไป CME เท่าเดิม
**ถอยกลับ** ตั้งคาบกลับเป็นชั่วโมงและปิดงาน ticker ในคอนฟิก (ไม่ต้องแก้โค้ด)

**ทำไปแล้ว 22 ก.ย. 10:15–10:45**
- `cme_fetcher.main(use_qs=, baseline=)` ค่า default = พฤติกรรมเดิมเป๊ะ (cron เก่า / ปุ่ม refresh)
  - `use_qs=False` ไม่แตะ QuikStrike เลย ไม่เขียน qs_state ไม่เขียน eventvol.json
    event vol ยืมจาก cache ใหม่ `cache["ev"]` ที่รอบรายชั่วโมงเก็บไว้ (อายุไม่เกิน 2 ชม.)
  - `baseline=False` ไม่เขียน PREV_STATE -> "Δ CHANGES SINCE" ยังนับจากรอบรายชั่วโมง
  - `main()` คืน dict รายสไตรค์ให้ ticker ใช้ต่อในหน่วยความจำ (ไม่ต้องมีไฟล์กลาง)
  - ชื่อพารามิเตอร์เป็น `use_qs` เพราะข้างในมีตัวแปร `qs = QSClient()` อยู่แล้ว ชนกันจะพังเงียบ
- **จำรหัส series ที่ยืนยันแล้ว** (`_series_memo`): WEEK_CODES เดาวันอังคารนี้เป็น I0DU26
  แต่ของจริง I0EU26 ทุกรอบเลยโหลด chain ผิดตัวทิ้งหนึ่งก้อน + probe อีกหนึ่ง = 4 request
  หลังจำ = **2 request ต่อรอบ ≈ 580/วัน** (ต่ำกว่าที่ประเมินไว้ 860) ตัวตรวจชื่อยังทำงานทุกรอบ
- `app.py` งาน cme ทุก 5 นาทีบนกริด :02 :07 :12 … (`align` + `offset=120` ตัวใหม่ใน scheduler)
  `want_qs()`: QuikStrike เฉพาะรอบ :07 + รอบแรกหลัง start + หลับข้าม :07 (ห่างเกิน 65 นาที)
  และห่างกันอย่างน้อย 20 นาทีเสมอ — จำลองทั้งวันแล้ว ได้ชั่วโมงละครั้งที่ :07
  series roll ระหว่างรอบ Barchart-only -> ดึง QuikStrike ของ series ใหม่ทันที (วันละครั้ง)
- `ticker.py` เขียนใหม่ กินข้อมูลรอบเดียวกับ snapshot = **0 request เพิ่ม** (เดิมยิง QuikStrike เอง)
  กับดักใหม่ข้อ 3: ขาดช่วงเกิน 12 นาที (หลับ/ปิด) ตั้ง baseline ใหม่ ไม่นับยอดช่วงที่หายเป็น event
  Barchart ให้ทั้ง chain -> strike ที่ไม่อยู่ในรอบก่อน = 0 จริง นับได้เลย (ต่างจากหน้าต่างของ QuikStrike)
  ทดสอบด้วย snapshot จำลอง 6 เคส (baseline / +15 / strike ใหม่ / ยอดลด / ขาดช่วง 40 นาที / series ใหม่) ผ่านหมด
- `/api/ticker` แยกจาก `/api/state` · widget `cme-ticker.jsx` ใช้ API + fallback ไฟล์ ปุ่ม Reset
  แค่ลบ state แล้วรอรอบถัดไป (ของเดิมยิง QuikStrike ทันที ผิดกฎข้อ 1)
- **บั๊กที่เจอตอนติดตั้ง widget**: พอ `command` เป็นฟังก์ชัน Übersicht ยังยิง `UB/COMMAND_RAN`
  เองโดยไม่มี output ถ้า updateState รับ event ชื่อนี้ไปเขียนทับ ข้อมูลจะถูกล้างจนการ์ดไม่ขึ้นเลย
  ต้องใช้ event ชื่อของเราเอง (`DATA`) ตัว cme-putcall รอดเพราะใช้ `DATA` มาตั้งแต่เฟส 2

**ผลรอบจริง** 10:27 (start + QuikStrike) / 10:32 / 10:37 ตรงนาที · สองรอบหลังไม่มีบรรทัด eventvol
qs_state กับ eventvol.json ไม่ถูกแตะ · IV event 23.84 มาจาก cache · changes ยังนับจาก 10:27
ticker ตั้ง baseline รอบแรก รอบถัดมาเห็น flow เล็กๆ ที่ 4365 (ช่วงเอเชียเงียบ) ประวัติ IV 23.31 → 23.04

**22 ก.ย. 10:54 — ถอด Δ CHANGES ฝั่ง Intraday ออกจากการ์ด P/C** (ซ้ำกับ ticker + Most Active)
ให้ ticker แยกคอลัมน์ P / C แทน `+n` รวม — ฝั่ง OI ยังเก็บไว้เพราะ ticker ไม่ได้ติดตาม OI
fetcher ยังคำนวณ `changes.intraday` ใน JSON ต่อ (ใครใช้ API อยู่ไม่พัง) แค่การ์ดไม่โชว์
**11:00 — ถอดฝั่ง OI ด้วย** (OI ของ Barchart อัปเดตวันละครั้ง ช่องขึ้น `no fills` แทบทั้งวัน)
การ์ด P/C ไม่มี Δ CHANGES แล้วทั้งสองฝั่ง / ticker ใส่ตัวอักษรกำกับ `P+33` `C+6` ในช่องเลย
`changes` ทั้งก้อนยังอยู่ใน JSON/API

**11:08 — สองเรื่องที่แก้เพิ่ม**
- IV ของ ticker อ่านที่ **F ของ Barchart** (`meta.iv_F`) ไม่ใช่ราคาสด: smile สร้างจาก quote ที่ช้า
  10-15 นาที อ่านที่ราคาสด = ปนสองช่วงเวลา (11:02 ห่างกัน 3.6 จุด) delta ยังใช้ราคาสดตั้งใจ
- **restart แล้วยิง QuikStrike ซ้ำ**: เวลา QuikStrike ครั้งล่าสุดอยู่แค่ในหน่วยความจำ restart ทีไร
  นับเป็นรอบแรก (11:07:42 ยิงซ้ำห่างรอบ 11:07 แค่ 42 วินาที — และวันนี้ restart ไปหลายรอบ)
  ตอนนี้เก็บที่ `state/qs_last.json` restart 11:08:30 ไม่ยิงแล้ว / หลัง reboot ห่างเกิน 65 นาทีก็ยิงตามปกติ
- **ยืนยันรอบ :07 แล้ว** 11:07:00 ยิง QuikStrike ตรงนาที (eventvol.json 11:07:10)

**ตรวจกับข้อมูลรายนาทีของ Barchart 23 ก.ย. 10:45** (`queryminutes.ashx` ต่อ leg เช่น `IY9U6|4410C`)
event ทั้ง 5 ตัวของวันนี้ตรงกับไม้จริงแบบ 1:1 ทุกตัว:

| event ของเรา | ไม้จริง | ช้ากว่า |
|---|---|---|
| 09:22 4400 C+10 | 09:08 vol 10 | 14 นาที |
| 09:32 4415 C+20 | 09:20 vol 20 | 12 นาที |
| 09:37 4395 C+27 | 09:26 vol 25 | 11 นาที |
| 09:52 4395 C+25 | 09:37 vol 25 | 15 นาที |
| 10:07 4410 C+30 | 09:55 vol 30 | 12 นาที |

- **ทุก event เป็นก้อนเดียว** (ไม้เดียวจบในนาทีเดียว 100%) ไม่มีการทยอยซอยในวันนี้
- ไม้ที่ต่ำกว่าเกณฑ์ 10 ถูกข้ามถูกต้อง (09:07:1, 09:11:3, 09:17:3, 09:42:3)
- **ช้ากว่าไม้จริง 11-15 นาที** = ดีเลย์ของ Barchart (~10) + กริด 5 นาทีของเรา -> ticker บอกว่า
  "มีของเข้าเมื่อ ~12 นาทีก่อน" ไม่ใช่ตอนนี้ ใช้เป็นบริบท ไม่ใช่สัญญาณเข้าออเดอร์
- ยอดต่าง +2 ที่ 4395: ไม่ใช่ของเราผิด -- **ชุดรายนาทีของ Barchart ตกไม้ไปเอง** เทียบยอดทั้ง session
  ต่อ leg: quote 52/15/61/54 vs รายนาที 50/11/61/53 (ต่าง +2/+4/0/+1) ยอดของ ticker ที่ 4395 (52)
  เท่ากับ quote พอดี = เราอ่านครบ

**ของแถมที่เคยวางไว้ (ยิงรายนาทีเองทุกรอบ) ไม่ทำ** — ผลวันนี้บอกว่า event เป็นก้อนเดียวหมด
และรายนาทีก็ตกไม้ ถ้าจะทำจริงควรเป็นโหมดตรวจย้อนหลังแบบนี้ (เรียกเมื่ออยากรู้) ไม่ใช่ยิงทุกรอบ

**ข้ามคืนผ่านแล้ว 2 คืน** (22->23 ก.ย.): series roll I0EU26 -> IY9U26 ล้างประวัติถูกต้อง `new=0`
ไม่มี event ปลอมจากช่วงเครื่องปิด / 0 fails

### บันทึกเหตุการณ์ 24 ก.ย. — วันหมดอายุรายเดือน เราหยิบ series ผิดตัว

ผู้ใช้ทักว่า "ใน CME วันนี้เป็น OGV6 รหัส series หลักเลย" ตรวจแล้วจริง: 25 ก.ย. 26 เป็นวันหมดอายุ
option **รายเดือน** ของ GCV26 และวันนั้นมีสองสัญญาหมดอายุพร้อมกัน

| บน barchart | ชื่อเต็ม | OI |
|---|---|---|
| `IG4U26` | Gold Friday Week 4 Options Sep '26 | 4,675 / 5,860 |
| `GCV26` | Gold Oct '26 (= OGV6 ของ CME) | **65,808 / 129,879** |

`weekly_candidates()` สร้างแต่รหัส weekly จาก `WEEK_CODES` ไม่เคยมีตัวรายเดือนในรายการเลย
เราเลยใช้ตัวเล็กกว่า 20 เท่ามาทั้งวัน (ตัวเลข OI/Intraday/smile/delta ผิดชุดหมด)

**แก้แล้ว**: เพิ่ม `monthly_option_symbol(d)` -- ถ้า d ตรงกับ `month_option_expiry()` ของเดือนไหน
ให้คืนสัญลักษณ์ chain รายเดือน (ซึ่งบน barchart คือสัญลักษณ์ futures เอง เช่น `GCV26`) แล้ว
`weekly_candidates` วางตัวนี้ไว้**หน้า**รหัส weekly ของวันเดียวกัน

ตัวตรวจชื่อ series ยังทำงานเหมือนเดิมกับรหัส weekly ส่วน chain รายเดือนชื่อไม่มีวันหมดอายุให้ตรวจ
(`Gold Oct '26 …`) จึงเชื่อได้เพราะรหัสสร้างจากปฏิทิน ไม่ใช่การเดา

**ยืนยันเวลาหมดอายุตรงกับ CME**: ตอน 00:32 QuikStrike บอก dte 2.0 สำหรับ 25 ก.ย. ส่วนสูตรเรา
(12:30 CT) ให้ 1.999 -- ตรงกัน แปลว่ารายเดือนหมดเวลาเดียวกับ weekly

**ผลข้างเคียงที่ยอมรับ**: series เปลี่ยนกลางวัน -> ticker ล้างประวัติตั้ง baseline ใหม่ (event ของ
weekly ที่จับได้ช่วงเช้าหายไป ถูกต้องแล้วเพราะคนละสัญญา) และมี QuikStrike เพิ่มหนึ่งครั้งตามกลไก roll

**แก้ต่ออีกชั้น (เช้าเดียวกัน)**: ผู้ใช้ทักว่า CME โชว์ OGV6 เหลือ **0.65 DTE** แต่เราโชว์ 1.66
-> `month_option_expiry()` ขาดเงื่อนไขของ CME ที่ว่า "ถ้า business day ที่ 4 ตรงวันศุกร์
ให้เลื่อนขึ้นมาหนึ่งวันทำการ" 25 ก.ย. เป็นศุกร์ ของจริงจึงเป็น **24 ก.ย.** (วันนี้)
เติมเงื่อนไขแล้ว DTE เหลือ 0.653 ตรงกับ CME

ผลที่ตามมาของการแก้วันเดียวนี้:
- 0DTE ของ**วันนี้**คือ GCV26 (OGV6) ไม่ใช่ของพรุ่งนี้ -> คืนนี้ 00:30 ไทย (พฤ 12:30 CT) จะ roll
- **สัญญาอ้างอิงเลื่อนมา roll เร็วขึ้นหนึ่งวันทำการ**: ตั้งแต่ series ที่หมดอายุ 25 ก.ย. เป็นต้นไป
  ใช้ GCZ26 (เดิมคิดว่าเริ่มจันทร์ 28)
- ฝั่ง QuikStrike จุด EVC ที่แมตช์จะเป็นของ 24 ก.ย. = OGV6 ตัวรายเดือนเอง ไม่ใช่ OG4U6 อีกต่อไป
  (ประเด็น "อาจหยิบ weekly" ที่จดไว้ก่อนหน้าจึงหมดไปเอง)
- cache ของ QuikStrike ผูกกับวันหมดอายุ พอวันที่เปลี่ยนเลยถูกล้าง IV ตกไปใช้ค่า computed
  ชั่วคราวจนถึงรอบ :07 ถัดไป

**ข้อจำกัดที่ยังเหลือ**: กฎเต็มของ CME มี "หรือวันก่อนวันหยุด" ด้วย เราไม่มีปฏิทินวันหยุด
เดือนไหนที่ business day ที่ 4 ติดวันหยุด วันที่ที่คำนวณได้จะช้าไปหนึ่งวัน

---

## เฟส 3.5 — dashboard เป็นหน้าเว็บ ⏳ เริ่ม 22 ก.ย. 2026

**ทำแล้ว (22 ก.ย.)**
- `http://127.0.0.1:8787/dashboard` เสิร์ฟโดย goldhub เอง ดับเบิลคลิกการ์ดบน desktop = เปิดหน้านี้
  (daemon ดับ -> ถอยไปเปิด /tmp/cme_chart.html แบบเดิม)
- **โค้ดชุดเดียว**: หน้าเว็บ (`goldhub/web/dashboard.html`) โหลด `widgets/gold-dashboard.jsx` ไฟล์เดียวกับ
  Übersicht มา transpile ด้วย Babel ในเบราว์เซอร์ แล้ววน initialState -> command -> updateState -> render
  แบบเดียวกับ Übersicht / ตัว widget เช็ค `WEB` เฉพาะจุดที่ต้องใช้ shell
  - copy -> `navigator.clipboard` (มีทางสำรอง textarea ตอนไม่ใช่ secure context เช่นเปิดผ่าน IP อื่น)
  - ดับเบิลคลิกบนเว็บ = เปิดกราฟแบบ CME (/api/chart)
  - **ไม่มีปุ่ม refresh และ Reset บนเว็บ** — ต้องรัน fetcher / ลบไฟล์ ซึ่งผ่าน API ไม่ได้ (กฎข้อ 1)
  - ยิง API ไม่ได้ = คงข้อมูลเดิม ขึ้น `· offline` (เว็บไม่มีไฟล์ /tmp ให้ถอย)
- เสิร์ฟ .jsx จาก repo ตาม mtime -> แก้หน้าตาแล้ว reload หน้าเว็บได้เลย ไม่ต้อง restart daemon
- ทดสอบใน browser pane: หน้าตาเหมือน desktop, hover กราฟได้, console ไม่มี error,
  `isSecureContext` = true ที่ 127.0.0.1

**ต่อจากนี้ (ยังไม่ทำ)**
1. ~~เลิกพึ่ง CDN + Babel ในเบราว์เซอร์~~ ✅ 22 ก.ย. 12:45 — **ไม่ต้องดาวน์โหลดอะไรเลย**
   ทุกอย่างมีใน Übersicht.app อยู่แล้ว: React/ReactDOM 16.13.1 (UMD) + node v16 + @babel 7.11.6
   - `web/vendor/` = React สองไฟล์ (~130 KB, MIT) รุ่นเดียวกับที่ Übersicht ใช้ -> desktop กับเว็บเหมือนกันเป๊ะ
   - `web/build.js` แปลง .jsx -> `web/dist/gold-dashboard.js` (ห่อเป็น factory ที่ window.APPHUB_WIDGETS)
   - goldhub build เองเมื่อ .jsx ใหม่กว่า dist (แก้แล้ว reload หน้าเว็บได้เลย) / .jsx พัง = log บรรทัด error
     พร้อมตำแหน่ง แล้วเสิร์ฟ dist ตัวล่าสุดที่ดีต่อ / dist ถูก commit ไว้ เครื่องที่ไม่มี Übersicht ก็เสิร์ฟได้
   - เปิดหน้าหนึ่งครั้ง = 4 ไฟล์จาก 127.0.0.1 ล้วน (เดิม ~3 MB จาก jsdelivr ทุกครั้ง) ไม่มี error ใน console
2. **layout มือถือ** — การ์ดกว้างตายตัว 1,062px จอเล็กต้องเรียงเป็นแนวตั้ง
   (ราคาสด -> F/SD -> กราฟ -> ticker) ผ่าน `window.innerWidth` ใน WEB เท่านั้น desktop ไม่กระทบ
3. **เปิดจากเครื่องอื่น** (ผูกกับเฟส 4) — bind IP ของ Tailscale + token: หน้าเว็บรับ `?token=`
   แล้วแนบใน fetch ทุกตัว / Host check ต้องเพิ่มชื่อเครื่องใน Tailscale
4. poll ด้วย `If-None-Match` ให้ได้ 304 (มือถือประหยัดเน็ต) — server รองรับแล้ว ฝั่งเว็บยังไม่ส่ง
5. เพิ่มส่วน weatherhub ในหน้าเดียวกัน (อนาคตอยากรวมทุกอย่าง) ตอนที่ weatherhub มี API

---

## เฟส 4 — มือถือ + weatherhub

**ขั้น 1 — เปิดให้เครื่องอื่นเข้าได้ ✅ 23 ก.ย. 2026**
- `common/hub/config.py` -> `~/Library/Application Support/apphub/config.json` สิทธิ์ 0600
  สร้างเองครั้งแรกพร้อม token สุ่ม / `bind` = address ที่เปิดเพิ่มจาก loopback (กรอง 0.0.0.0 ทิ้ง)
  / `hosts` = ชื่อที่ยอมใน Host check / เตือนใน log ถ้าสิทธิ์ไฟล์หลวม / **ไม่ log ค่า token**
- `Api` เปิด listener หนึ่งตัวต่อ address (ไม่ใช้ 0.0.0.0 แล้วมากรองทีหลัง) address ไหนเปิดไม่ได้
  ก็ข้ามตัวนั้น ขอแค่ loopback ขึ้นก็พอ
- **token บังคับเฉพาะเครื่องอื่น** loopback ยังเรียกเปล่าๆ ได้ -> widget/หน้าเว็บบนเครื่องไม่ต้องแก้
- รับ token ได้ 3 ทาง: header `X-Apphub-Token`, `?token=`, **cookie** -- ทางที่สามจำเป็นเพราะ
  `<script src>` ของหน้าเว็บแนบ header เองไม่ได้: เข้า `/dashboard?token=…` ครั้งเดียวแล้ว
  เซิร์ฟเวอร์ set cookie (7 วัน, SameSite=Lax) ไฟล์ย่อยกับ fetch ตามมาได้เอง
- ทดสอบผ่านหมด: loopback ไม่มี token 200 · LAN ไม่มี token 401 · token ผิด 401 ·
  token ถูกทั้ง header และ query 200 · Host ปลอม 403 · cookie ใช้ได้ทั้ง widget.js และ /api/state ·
  token ไม่โผล่ใน log
- **Tailscale ยังไม่ได้ติดตั้งบนเครื่องนี้** ตอนนี้ทดสอบด้วย LAN IP ลงเมื่อไหร่แค่เพิ่ม IP ใน `bind`

**มือถือ** (ขั้น 3) — **เปลี่ยนแผน 24 ก.ย.: termux ต้อง standalone ไม่พึ่ง Mac/VPN**
- หน้าที่เดียวของมันคือดึง P/C ไปแปะให้ indicator ตอนไม่ได้อยู่หน้าเครื่อง จึงต้องทำงานได้
  ทุกที่โดยไม่ต้องมี VPN -> **ยกเลิก**แนวคิดเดิมที่จะให้ดึง `/api/clip` ก่อนแล้ว fallback
- **ตัวที่เอาไปติดตั้งจริงคือ `setup_cme_termux.sh`** ซึ่งฝังโค้ด `.py` ทั้งไฟล์ไว้ข้างในเป็น heredoc
  แก้ `.py` อย่างเดียวไม่ถึงมือถือ (24 ก.ย. 26 พลาดมาแล้ว) -> หลังแก้ `.py` ต้องรัน
  `python3 sync_setup.py` เสมอ (`--check` ไว้เช็คว่าตรงกันไหม)
- ราคาที่ต้องจ่าย: เป็นโค้ดคนละชุดกับ `cme_fetcher.py` **บั๊กต้องแก้สองที่เสมอ**
  (24 ก.ย. ยก 3 อย่างไปใส่: ปฏิทินวันหยุด + กฎศุกร์/วันก่อนวันหยุด + chain รายเดือนมาก่อน weekly)
  มีสคริปต์เทียบฟังก์ชันวันที่/series ของสองไฟล์ให้ตรงกันก่อน commit
- มือถือยังยิง QuikStrike เองจาก IP อีกวง = ยอมรับตามการตัดสินใจนี้
- เปิดให้เข้าจากนอกเครื่อง: bind เพิ่มเฉพาะ IP ของ Tailscale (ไม่ใช่ 0.0.0.0) + token
  **ข้อจำกัดที่ต้องยอมรับ: Mac หลับเมื่อไหร่ มือถือดึงไม่ได้**

**weatherhub** (พอร์ต 8788, โครงเดียวกัน)
- ~~ย้าย `weather_fetcher.py` + `rain_nowcast.py` เข้า `weatherhub/service/`~~
  ✅ ทำไปก่อนแล้ว 21 ก.ย. เพราะอยากปิด cron ให้หมดในวันเดียวกับที่ย้าย gold
  (daemon `com.apphub.weatherhub` งาน radar + nowcast ทุก 5 นาที `align=True`)
- ✅ **API ฝั่ง server (25 ก.ย. 26)** `weatherhub/service/api.py` พอร์ต 8788
  `/api/state?lat=&lon=`, `/api/radar` (ภาพ jpeg ตรงๆ), `/api/health`, `/`
  - พิกัดมาจาก location service ของอุปกรณ์ที่เรียก ปัดเป็นกริด 0.05° ก่อนทำอะไรทั้งนั้น
    ตอบกลับเป็นค่าที่ปัดแล้ว ไม่ log / ไม่ส่งมา = `weather.default` ใน config.json หรือ Office
  - **ค่ารายจุดมาจากเรดาร์อย่างเดียว** (ผู้ใช้เลือก: ไม่เพิ่มแหล่งใหม่ และไม่เพิ่มรอบโหลด
    loop GIF -- ยังโหลดเฉพาะตอนเช็ค 16:xx): ตำแหน่งบนภาพเป็น % (วาง marker ได้เลย),
    ระยะ/ทิศจากหนองจอก, ETA ฝนหนักจากรอบเช็คล่าสุด (`nowcast.age` บอกว่าเก่าแค่ไหน)
  - rain_nowcast เขียน `/tmp/weather_nowcast.json` (จุดฝนหนัก + motion) ทุกครั้งที่วิเคราะห์
    API คิด ETA ของพิกัดไหนก็ได้จากไฟล์นี้ -> ไม่ยิง upstream (กฎข้อ API อ่านอย่างเดียว)
  - นอกวงเรดาร์ 120 กม. = `in_coverage:false`, `img_pct` / `nowcast` เป็น null
  - `FileCache` ย้ายจาก goldhub/api.py ไปอยู่ `common/hub/filecache.py` ใช้ร่วมกัน
- ✅ **widget ใช้ API (25 ก.ย. 26)** `radar-weather.jsx` เป็น function command:
  ขอพิกัดจาก `navigator.geolocation` ซึ่ง Übersicht ต่อเข้า CoreLocation ของแอปเอง
  (Resources/geolocation.js + NSLocationUsageDescription -- ไม่ต้องลงอะไรเพิ่ม, ครั้งแรก macOS
  ถามสิทธิ์ Location ของ Übersicht) ทุก 10 นาที timeout 8 วิ (shim ไม่เคยเรียก onError)
  -> `/api/state?lat=&lon=` -> จุดเขียว "เครื่องนี้" จาก `img_pct` + บรรทัด ETA ฝน (nowcast
  อายุ < 1 ชม.) / ภาพจาก `/api/radar` / API ล่มถอยไป cat /tmp เดิม ("· file")
  จุด Office/Home ตายตัวยังอยู่ / ⬜ หน้าเว็บ: geolocation ต้องเป็น secure context
  (https หรือ localhost) มือถือเข้าผ่าน IP ตรงๆ จะขอพิกัดไม่ได้
- ⬜ `weatherhub/deploy/Dockerfile` — เผื่อขึ้น cloud ปรับผ่าน env
  `APPHUB_PORT` / `APPHUB_DATA` / `APPHUB_TOKEN`

**เสร็จเมื่อ** มือถือกดปุ่มเดียวได้ clip ผ่าน VPN และ weatherhub ตอบตามพิกัดที่ส่งมา
**ถอยกลับ** มือถือยังมีโค้ดเดิมอยู่ในเครื่อง ใช้ได้ทันที / weatherhub แยก process
ไม่กระทบ goldhub

---

## เฟส 5 — เก็บกวาด

- ✅ **ลบ cron ทั้งสามบรรทัดแล้ว (25 ก.ย. 26)** — `crontab -r` เพราะเหลือแต่ comment ที่ชี้ไป
  `my-cronjob` ซึ่งเลิกใช้แล้ว (ถอยกลับไม่ได้จริงอยู่ดี) daemon เดินมา 4 วันไม่มีปัญหา
  ตอนนี้ `crontab -l` = "no crontab"
- ✅ **รวมทุกโฟลเดอร์เข้า apphub (25 ก.ย. 26)** — แทนข้อ "ใส่ README ชี้มา apphub" เดิม
  เพราะผู้ใช้เลิกใช้ `cme_scraping` / `mac_widget` / `tdw_indi` / `my-cronjob` ทั้งหมด
  - ตรวจไฟล์ที่ทับกันก่อน: fetcher 4 ตัวกับ widget เหมือน apphub ทุก byte ส่วน
    `cme-putcall.jsx`, `cme-ticker.jsx`, `INTRADAY-TICKER-EXPLAINED.md`, `oi_block.pine`
    ของ apphub **ใหม่กว่า** -> ไม่มีอะไรต้อง copy ย้อนกลับ
  - ย้ายเข้ามาใหม่ 26 ไฟล์ (260 KB): `goldhub/research/` (backtest_sd.py + CSV 2 รุ่น
    + README สรุปข้อสรุป 2σ/3σ SL 25$), `goldhub/legacy/quikstrike/` (fetch_all.py,
    capture/parse/build_table + samples), `goldhub/legacy/first-version/`,
    `weatherhub/legacy/first-version/`
  - ประวัติ git ทั้ง 3 repo fetch เข้ามาเป็น branch `archive/mac-widget` (58),
    `archive/tdw-indi` (15), `archive/my-cronjob` (40) — tag save-*/savepoint-1 ทุกตัว
    เป็น ancestor ของ master แล้ว (ตรวจด้วย merge-base) จึงไม่ต้องเก็บ tag
  - ที่ไม่ย้าย: `captures/` 156 ไฟล์จากการสำรวจ มิ.ย., `.pw-profile`, `session.json`,
    `.claude/settings.local.json` (allowlist ผูกกับ path เดิม) -> อยู่ในถุง
    `_archive/retired-projects-2026-09-25.tar.gz` (6 MB, มี .git ของทุก repo)
  - **ยังไม่ลบโฟลเดอร์** (ผู้ใช้เลือกปล่อยไว้ก่อน) ใส่ `RETIRED.md` กำกับไว้ทั้งสี่ที่แล้วว่า
    ห้ามแก้ ของจริงอยู่ apphub และประวัติอยู่ branch ไหน — ลบได้ทุกเมื่อ แต่ต้องสั่งจาก session
    ที่ไม่ได้ cd อยู่ใน `cme_scraping` (เป็น working dir ของ session ที่ทำงานนี้)
  - memory: copy ไปไว้ที่ project dir ของ apphub ด้วย (`-Users-sorachai-src-claude-code-apphub`)
    และดึง `mac-widget-architecture` ของ project dir เก่ามารวมเป็น `widget-data-sources`
    (แหล่งราคา + ข้อกำหนด TLS/UA + georeference เรดาร์) — สองที่ sync กันแล้ว
- ✅ **โฟลเดอร์ widget ของ Übersicht เลิกเป็น git repo (25 ก.ย. 26)**
  - เดิม `~/Library/Application Support/Übersicht/widgets/` เป็น git repo แยก (37 commit,
    branch master + tag save-2/3/4) ทำให้มีต้นทาง 2 ที่ ต้อง sync มือทุกครั้ง
  - เช็คก่อนลบ: `radar-weather.jsx` กับ `gold-update.jsx` ตรงกับใน apphub ทุก byte,
    `cme-putcall.jsx` ใน apphub ใหม่กว่า (มีโค้ดเฟส 2), save-2/3/4 เป็น ancestor ของ master
    (ไม่มี commit ที่ไม่อยู่ใน master) -> ไม่มีเนื้อหาไหนหายจากการลบ
  - ประวัติเก็บไว้เป็น branch `archive/ubersicht-widgets` ของ repo นี้ (fetch เข้ามาทั้ง 37 commit
    แล้ว push ขึ้น GitHub) ไม่ใช่ไฟล์ bundle ให้ดูย้อนหลังใน GitHub ได้ตรงๆ
    tag `save-2/3/4` ถอดออก (commit ยังอยู่: 78bf717, 78bf717, 1c800af)
  - deploy widget กลายเป็นคำสั่งเดียว `bash <hub>/deploy/install.sh widgets`
    (install เต็มรูปก็ copy widget ให้ในตัว / uninstall ไม่ลบ widget ออกจากจอ)
  - โฟลเดอร์นั้นเหลือแต่ `gold-dashboard.jsx`, `radar-weather.jsx`, `.DS_Store`
- ✅ ปรับ `docs/pipeline-notes.md` + `goldhub/README.md` ให้ตรงกับของจริงหลังย้าย (25 ก.ย. 26)
- ✅ อัปเดต memory ของ session ให้ชี้ path ใหม่ (25 ก.ย. 26) — บันทึกของ 23-25 ก.ย. เพิ่มครบ
  (เฟส 3.5/4, series รายเดือน + ปฏิทินวันหยุด, atm_iv, termux standalone, เลิก repo Übersicht)
  ⚠️ memory ผูกกับ working dir: `~/.claude/projects/-Users-sorachai-src-claude-code-cme-scraping/memory/`
  ถ้าเปิด session ใหม่โดย cd เข้า apphub ตรงๆ memory ชุดนี้จะไม่ถูกโหลด

---

## สิ่งที่ตัดสินใจไว้แล้ว

| เรื่อง | สรุป |
|---|---|
| ภาษา | Python 3 stdlib (ยกเว้น `curl_cffi` ที่ราคาสดต้องใช้หนี Cloudflare) |
| deploy | macOS = launchd LaunchAgent ต่อบริการ / cloud = Docker หรือ systemd |
| เริ่มรัน | launchd `RunAtLoad` ตอน login + `KeepAlive` ปลุกเมื่อ process ตาย |
| ตลาดปิด | scheduler หยุดงานฝั่งทองช่วงเสาร์และช่วงพักรายวัน |
| retention | 7 วัน + cap 200 MB ลบจากเก่าสุด (ประเมินจริงราว 0.9 MB/วัน) |
| /tmp | ยังเขียนเหมือนเดิมทุกไฟล์ ถือเป็นของแถมไว้คุ้ย ไม่ใช่ทางส่งข้อมูลหลัก |
| พอร์ต | goldhub 8787 / weatherhub 8788 |

## ตัดสินใจเพิ่ม (20 ก.ย. 2026)

- **ticker แยกเป็น `/api/ticker`** ไม่รวมใน `/api/state` เผื่อทำ dashboard หลายเวอร์ชัน
  และให้ client ที่สนใจแค่ ticker poll ถี่ได้โดยไม่ลากก้อนใหญ่มาด้วย
- **widget ticker เป็นการ์ดแยก** (อนาคตอยากรวมทุกอย่างเป็นหน้าเดียว — ออกแบบ API
  ให้พร้อมรวมไว้ก่อน คือทุก endpoint คืนก้อนที่ประกอบกันได้ ไม่ผูกกับ layout)
- **token คงที่ในคอนฟิก** ไม่สุ่มใหม่ตอน start เพราะแบบสุ่มจะทำให้ปุ่มบนมือถือ/Rainmeter
  พังเงียบๆ ทุกครั้งที่ launchd restart service
  - เก็บที่ `~/Library/Application Support/apphub/config.json` สิทธิ์ 0600 ไม่เข้า git
  - รับได้ทั้ง header `X-Apphub-Token` และ query string (Rainmeter ใส่ header ไม่สะดวก)
  - ไม่ log ค่า token / bind เฉพาะ loopback + IP ของ Tailscale ไม่ใช่ 0.0.0.0
  - เฟส 2 ยังไม่ต้องใช้ (ผูก 127.0.0.1 อยู่แล้ว) เริ่มบังคับตอนเฟส 4

## กฎที่ห้ามละเมิด

1. **API อ่านจาก cache อย่างเดียว** request จากข้างนอกห้ามกระตุ้นให้ไปดึง upstream
   ไม่งั้นใครยิงถี่ๆ = เราไปถล่ม CME/Barchart แทน (อันตรายกว่าข้อมูลรั่ว)
2. **QuikStrike ต้องอยู่ใต้ตัวเบรกและ cache เดิมเสมอ** ไม่ว่าจะเพิ่มฟีเจอร์อะไร
3. **ห้ามยิง www.cmegroup.com** (WAF แบน IP เครื่องนี้ไว้แล้ว ใช้ได้แค่เป็น Referer)


---

## คำสั่งที่ต้องรันเองเพื่อจบเฟส 1

sandbox ของ session แก้ crontab ไม่ได้ (คำสั่งค้างรอ permission) และไม่ควรสั่ง launchctl
แทนเจ้าของเครื่อง — สองคำสั่งนี้รันเองครั้งเดียว

```bash
# 1) ปิดบรรทัด cme ใน crontab (ไฟล์เตรียมไว้แล้ว มี comment บอกวิธีถอยกลับ)
crontab /tmp/ct.new && crontab -l

# 2) ติดตั้ง LaunchAgent แล้วดูว่า start จริง
bash /Users/sorachai/src/claude_code/apphub/goldhub/deploy/install.sh
tail -f ~/Library/Logs/apphub/goldhub.log
```

ถ้า `/tmp/ct.new` หายไปแล้ว (reboot) ให้แก้ด้วย `crontab -e` เอง: ใส่ `#` หน้าบรรทัด
`7 * * * * ... cme_fetcher.py`

### ขั้นสองของเฟส 1 — ย้าย gold_fetcher (นัดไว้ 21 ก.ย. 2026)

ปล่อยให้ cme เดินหนึ่งวันก่อน เพื่อแยกให้ออกว่าถ้ามีปัญหาเกิดจากตัวไหน
**เช็คก่อนย้าย gold:**
- รอบ :07 มาตรงทุกชั่วโมง (ดู `~/Library/Logs/apphub/goldhub.log`)
- เครื่อง sleep แล้วตื่น งานกลับมาเดินเอง ✅ เดินเอง แต่เลื่อนตามเวลาที่หลับ — แก้แล้ว 21 ก.ย. (ดูบันทึกท้ายไฟล์)
- reboot/logout-login แล้ว `RunAtLoad` ทำงาน
- `kill <pid>` แล้ว KeepAlive ปลุกใหม่ภายใน 30 วินาที

**ตอนย้าย gold ต้องระวัง**
- loop ของ gold_fetcher ออกแบบมาให้จบที่ 290 วินาทีแล้วให้ cron ปลุกใหม่ — ใน daemon
  ต้องเป็น loop ต่อเนื่อง (ผลพลอยได้: `gold_live.js` จะไม่ขาดช่วงทุก 5 นาทีอีก)
- `curl_cffi` + path ของ brew curl ใต้ environment ของ launchd ไม่เหมือน cron ต้องทดสอบ
- ย้าย anchor รายวันที่ gold_fetcher ยิง QuikStrike เอง มาใช้ `underlying_for()` ของ
  cme_fetcher แทน = ตัดการพึ่ง CME ออกอีกจุด และเข้ามาอยู่ใต้ตัวเบรกเดียวกัน

### บันทึกเหตุการณ์ 20 ก.ย. 17:15 — รันซ้อนสามตัว

ตรวจงานรอบ 17:15 แล้วพบว่า health บอก `runs 4` ทั้งที่ log มีแค่ 2 รอบ และ `started_at`
เป็นเวลา 11:00 ทั้งที่ process ของ launchd เริ่ม 16:35 — ไล่ดูพบว่า **process ทดสอบ
ที่รันจาก shell ตอน 10:59 กับ 11:00 ยังไม่ตาย** (คำสั่ง `pkill -f "apphub/goldhub/service/app.py"`
ไม่โดน เพราะรันด้วย `cd service && python3 app.py` argv จึงเป็น `app.py` เฉยๆ)
ตอน 17:07 จึงมีสาม process ยิง QuikStrike/Barchart พร้อมกัน (เห็นชัดในไฟล์ history
ที่มีสองบรรทัด ts ห่างกัน 0.08 วินาที)

**ผลกระทบ** ไม่มีข้อมูลเสียหาย (ทุกตัวเขียนค่าเดียวกัน) ตัวเบรก QuikStrike ไม่ทำงาน
(`net_fail 0`, ไม่มี pause ใหม่) แต่เป็นความเสี่ยงโดนบล็อกที่เราพยายามเลี่ยงที่สุด

**แก้แล้ว** ฆ่า process ค้างทั้งสอง + เพิ่ม `common/hub/lock.py` (flock) ให้หนึ่งบริการ
มีได้ process เดียว ตัวที่สองจะ log ว่าชนกับ pid ไหนแล้วออกด้วย exit 0 (ไม่ให้ launchd
วน restart) ทดสอบแล้ว: สั่ง `python3 app.py` ซ้ำได้ข้อความ "มี goldhub ตัวอื่นรันอยู่แล้ว (pid 18270) — ออก"

**ตรวจว่าเฟส 1 ผ่าน:** หลังติดตั้งแล้วรอถึงนาทีที่ :07 ของชั่วโมงถัดไป แล้วดู log ว่ามีบรรทัด
`ok [barchart]` และ `/tmp/cme_putcall.json` มี timestamp ใหม่ / widget บน desktop ยังขึ้นปกติ

### บันทึกเหตุการณ์ 21 ก.ย. 09:15 — รอบ :07 เลื่อนตามเวลาที่เครื่องหลับ

ตรวจงานเช้าวันจันทร์แล้วพบว่าข้ามคืนมา cme รันแค่ 3 รอบ (17:17 → 02:33 → 08:23) แทนที่จะ
เป็นชั่วโมงละครั้ง และรอบที่นัดไว้ 09:07 มายิงจริง 09:16:09 (ช้า 9.2 นาที)

**สาเหตุ** `Event.wait(วินาที)` ของ Python บน macOS นับเวลาด้วยนาฬิกาที่ **หยุดเดินตอนเครื่องหลับ**
วัดยืนยันได้จาก `time.clock_gettime`: ตั้งแต่ boot มา `CLOCK_MONOTONIC` = 41.5 ชม. (เท่านาฬิกาจริง)
แต่ `CLOCK_UPTIME_RAW` = 6.9 ชม. → เครื่อง (โน้ตบุ๊กใช้แบต) หลับไปเกือบ 35 ชม.
ของเดิมคำนวณ due แล้วรอยาวรวดเดียว เวลาที่หลับจึงไม่ถูกนับ รอบเลยเลื่อนออกไปเท่าที่หลับพอดี:
08:23:38 → นัด 09:07 เครื่องหลับ ๆ ตื่น ๆ อีก ~9 นาทีก่อน full wake 08:45:55 → ยิง 09:16

**ไม่ใช่ปัญหาของ cron แบบเดิม** เพราะ cron ยิงตามนาฬิกาจริง (แต่ถ้าหลับข้ามรอบก็หายไปเลย
ไม่ตามเก็บ) ของเราตามเก็บให้ แค่เวลาเพี้ยน

**แก้แล้ว** `scheduler.py` เปลี่ยนจากรอยาวรวดเดียวเป็นรอทีละ `TICK` = 30 วินาที แล้วเทียบ
`time.time()` (นาฬิกาจริง) ใหม่ทุกครั้ง + ถ้าช้าเกิน `LATE_WARN` = 120 วินาทีให้ขึ้น log ว่า
"ยิงช้า N นาที (เครื่องหลับ/หยุดชั่วคราว?)" จะได้เห็นเองครั้งหน้าโดยไม่ต้องมานั่งไล่

**สิ่งที่ยังต้องยอมรับ** ถ้าเครื่องหลับคร่อมนาทีที่ :07 จริง ๆ รอบนั้นจะไปยิงตอนตื่น (ช้าได้เป็นชั่วโมง)
ไม่มีทางเลี่ยงบนเครื่องที่หลับ นอกจากตั้ง wake schedule ของ macOS ซึ่งยังไม่ทำ

**เรื่องอื่นที่เจอรอบเดียวกัน**
- 08:23 รอบนั้นขึ้น `barchart: ทุก candidate ว่าง` = เช้าวันจันทร์ก่อนตลาดเดิน Barchart ยังไม่มีแถว
  ของ session ใหม่ ตัว fetcher ไม่เขียนทับไฟล์เดิม (ถูกต้องตามที่ออกแบบ) รอบ 09:16 กลับมาปกติ
- ปุ่ม refresh ใน widget ยังเรียก `/Users/sorachai/src/my-cronjob/cme_fetcher.py` (path เก่า)
  ใช้งานได้ แต่ต้องเปลี่ยนตอนเฟส 5 หรือตอนเปิด API ในเฟส 2

**เคยใส่ flock ใน `cme_fetcher.main()` แล้วถอดออก (21 ก.ย.)** เพราะการยิงทับกรณีนี้เกิดจาก
คนกดปุ่ม refresh เอง ไม่ใช่ของที่เกิดซ้ำเองโดยอัตโนมัติ ไม่คุ้มกับการมีล็อกตัวที่สองให้ดูแล
ถ้าเฟส 2 ทำให้ widget ยิง API แทนการรัน fetcher เอง เรื่องนี้ก็หมดไปโดยปริยาย

### 21 ก.ย. 10:55 — crontab ว่างแล้ว

`crontab -l` ไม่เหลือบรรทัดที่ทำงานเลย (เหลือแต่ comment ไว้เป็นทางถอย 3 บรรทัด)
ทุกงานเดินด้วย launchd สองตัว: `com.apphub.goldhub` (cme รายชั่วโมง + gold ทุก 5 วิ)
และ `com.apphub.weatherhub` (radar + nowcast ทุก 5 นาที)

ค่อยลบ comment ทิ้งตอนเฟส 5 หลังปล่อยให้เดินสัก 2-3 วัน — ✅ ลบแล้ว 25 ก.ย. (ดูเฟส 5)
