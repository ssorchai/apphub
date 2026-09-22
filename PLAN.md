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

## เฟส 3 — เปลี่ยนคาบเป็น 5 นาที + ticker

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

---

## เฟส 4 — มือถือ + weatherhub

**มือถือ**
- `goldhub/mobile/termux/` — ให้ลองดึง `/api/clip` ก่อน (timeout 5 วิ)
  ถ้าไม่ได้ค่อยตกไปใช้โค้ด scrape เดิมที่มีอยู่ ได้ทั้งความง่ายและความทน
- ผลพลอยได้: เมื่อดึงผ่าน Mac ได้ มือถือจะเลิกยิง QuikStrike จาก IP อีกวง
  เหลือ IP เดียวที่คุยกับ CME และอยู่ใต้ตัวเบรกเดียวกัน
- เปิดให้เข้าจากนอกเครื่อง: bind เพิ่มเฉพาะ IP ของ Tailscale (ไม่ใช่ 0.0.0.0) + token
  **ข้อจำกัดที่ต้องยอมรับ: Mac หลับเมื่อไหร่ มือถือดึงไม่ได้**

**weatherhub** (พอร์ต 8788, โครงเดียวกัน)
- ~~ย้าย `weather_fetcher.py` + `rain_nowcast.py` เข้า `weatherhub/service/`~~
  ✅ ทำไปก่อนแล้ว 21 ก.ย. เพราะอยากปิด cron ให้หมดในวันเดียวกับที่ย้าย gold
  (daemon `com.apphub.weatherhub` งาน radar + nowcast ทุก 5 นาที `align=True`)
  **ที่เหลือของเฟส 4 คือ API + พิกัดจากผู้เรียก ยังไม่ได้ทำ**
- `/api/state?lat=&lon=` — ไม่ส่งมาใช้ default, cache ต่อช่องกริด ~0.05°
  (กันยิง upstream ซ้ำ และไม่เก็บพิกัดตรงๆ ของผู้ใช้)
- เรดาร์ผูกกับพื้นที่: อยู่นอก bbox กรุงเทพฯ = ไม่มี layer เรดาร์ ส่งเฉพาะค่ารายจุด
- `weatherhub/deploy/Dockerfile` — เผื่อขึ้น cloud ปรับผ่าน env
  `APPHUB_PORT` / `APPHUB_DATA` / `APPHUB_TOKEN`

**เสร็จเมื่อ** มือถือกดปุ่มเดียวได้ clip ผ่าน VPN และ weatherhub ตอบตามพิกัดที่ส่งมา
**ถอยกลับ** มือถือยังมีโค้ดเดิมอยู่ในเครื่อง ใช้ได้ทันที / weatherhub แยก process
ไม่กระทบ goldhub

---

## เฟส 5 — เก็บกวาด

- ลบ cron ทั้งสามบรรทัด (หลังจากทุกอย่างอยู่ใน launchd แล้ว)
- `~/src/my-cronjob/` เหลือเป็นประวัติ ใส่ README ชี้มา apphub เหมือนสามโฟลเดอร์ก่อนหน้า
- ปรับ `docs/pipeline-notes.md` ให้ตรงกับของจริงหลังย้าย
- อัปเดต memory ของ session ให้ชี้ path ใหม่ทั้งหมด

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

ค่อยลบ comment ทิ้งตอนเฟส 5 หลังปล่อยให้เดินสัก 2-3 วัน
