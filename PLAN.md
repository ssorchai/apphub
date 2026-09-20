# แผนย้ายเป็น apphub — ทำเป็นเฟส

หลักการของทุกเฟส: **ของเดิมต้องใช้งานได้ตลอด** แต่ละเฟสมีเงื่อนไข "ถือว่าเสร็จ",
วิธีทดสอบ และวิธีถอยกลับที่ทำได้ภายในไม่กี่นาที

สถานะตอนเริ่มแผน (20 ก.ย. 2026): cron 3 บรรทัดรัน `~/src/my-cronjob/*.py`,
Übersicht โหลด widget จาก `~/Library/Application Support/Übersicht/widgets/`,
มือถือรัน Termux ที่ scrape เองทั้งหมด

---

## เฟส 0 — จับ baseline ไว้เทียบ (ครึ่งชั่วโมง)

ถ้าไม่มีตัวเทียบ จะไม่รู้ว่าเฟสถัดไปทำให้ค่าเพี้ยนไหม

- เก็บ output ของรอบ cron ปัจจุบันไว้: `cme_putcall.json`, `cme_putcall_clip.txt`,
  `gold_data.json`, `cme_chart.html` ลง `_archive/baseline-YYYYMMDD/`
- จดค่าที่ต้องตรงกันหลังย้าย: `series`, `F`, `dte`, `iv_event`, ยอด intraday/OI,
  ความยาว clip, จำนวน strike ใน chart

**เสร็จเมื่อ** มีไฟล์ baseline ครบและจดค่าไว้แล้ว
**ถอยกลับ** ไม่มีอะไรให้ถอย ยังไม่แตะระบบ

---

## เฟส 1 — daemon ตัวเดียวแทน cron (ยังเขียน /tmp เหมือนเดิม)

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
**ถอยกลับ** `launchctl unload` แล้ว uncomment cron สองบรรทัด — กลับสภาพเดิมใน 1 นาที

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

## ที่ยังไม่ตัดสินใจ

- จะให้ `/api/state` รวม ticker ไว้ด้วย หรือแยก `/api/ticker` (แยกแล้ว widget ticker
  จะ poll ถี่กว่าโดยไม่ลากก้อนใหญ่มาด้วย)
- token: ตั้งค่าคงที่ในไฟล์คอนฟิก หรือสุ่มใหม่ทุกครั้งที่ start
- จะเก็บ widget ticker เป็นการ์ดแยก หรือรวมเข้าการ์ด cme-putcall
