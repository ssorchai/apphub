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

## เฟส 1 — daemon ตัวเดียวแทน cron ⏳ โค้ดเสร็จ รอติดตั้ง

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
(gold_fetcher ยังรันผ่าน cron ไปก่อน ค่อยย้ายเข้ามาเมื่อผ่านข้อ 2)
**ถอยกลับ** `bash goldhub/deploy/install.sh uninstall` แล้ว uncomment cron — 1 นาที

**ผลทดสอบ 20 ก.ย. 11:00** รัน daemon แบบ foreground หนึ่งรอบ เทียบกับ baseline:
ตรงกันทุกค่า (series IY3U26, F 4390.7, iv_event 14.93, intraday 1190/1371, OI 2625/3246,
chart rows 67/69/52, clip 2020 ตัวอักษร) ต่างแค่ DTE กับ timestamp ตามเวลาที่เดินไป
รอบใช้เวลา 8.3 วินาที / health เขียนลง store ถูกต้อง / นัดรอบถัดไป 11:07 ตรงกับนาทีของ cron เดิม

**เหลือสองคำสั่งที่ต้องรันเอง** (sandbox ของ session แก้ crontab และสั่ง launchctl ไม่ได้)
ดูท้ายไฟล์นี้

---

## เฟส 2 — เปิด HTTP API แล้วให้หน้าจอดึงผ่าน API

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
- ย้าย `weather_fetcher.py` + `rain_nowcast.py` เข้า `weatherhub/service/`
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
- เครื่อง sleep แล้วตื่น งานกลับมาเดินเอง
- reboot/logout-login แล้ว `RunAtLoad` ทำงาน
- `kill <pid>` แล้ว KeepAlive ปลุกใหม่ภายใน 30 วินาที

**ตอนย้าย gold ต้องระวัง**
- loop ของ gold_fetcher ออกแบบมาให้จบที่ 290 วินาทีแล้วให้ cron ปลุกใหม่ — ใน daemon
  ต้องเป็น loop ต่อเนื่อง (ผลพลอยได้: `gold_live.js` จะไม่ขาดช่วงทุก 5 นาทีอีก)
- `curl_cffi` + path ของ brew curl ใต้ environment ของ launchd ไม่เหมือน cron ต้องทดสอบ
- ย้าย anchor รายวันที่ gold_fetcher ยิง QuikStrike เอง มาใช้ `underlying_for()` ของ
  cme_fetcher แทน = ตัดการพึ่ง CME ออกอีกจุด และเข้ามาอยู่ใต้ตัวเบรกเดียวกัน

**ตรวจว่าเฟส 1 ผ่าน:** หลังติดตั้งแล้วรอถึงนาทีที่ :07 ของชั่วโมงถัดไป แล้วดู log ว่ามีบรรทัด
`ok [barchart]` และ `/tmp/cme_putcall.json` มี timestamp ใหม่ / widget บน desktop ยังขึ้นปกติ
