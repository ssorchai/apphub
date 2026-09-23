# ย้าย apphub ไปรันบน Windows — โน้ตสำหรับตอนจะแปลงโค้ด

เขียน 23 ก.ย. 2026 · **เป็นเอกสารอย่างเดียว ยังไม่ได้แก้โค้ดใดๆ** · โค้ดที่อ้างถึงคือสถานะ ณ วันที่เขียน

เป้าหมายของเอกสารนี้: ถ้าวันหนึ่งจะเอา `goldhub` (และ `weatherhub`) ไปรันบนเครื่อง Windows
ให้รู้ล่วงหน้าว่าติดตรงไหนบ้าง แก้ยังไง และอะไรที่**ไม่ต้อง**แก้

> ทางที่ง่ายกว่ามากถ้าแค่อยากดูจอบน Windows: ปล่อย daemon ไว้บน Mac แล้วให้ Windows เปิด
> `http://<mac>:8787/dashboard` (ต้องทำเฟส 4 ก่อน: bind IP ของ Tailscale + token + เพิ่มชื่อ
> เครื่องใน Host check) — ไม่ต้องแก้โค้ดเลยสักบรรทัด และได้มือถือไปพร้อมกัน
> เอกสารนี้ว่าด้วยกรณี "ยกตัวดึงข้อมูลไปรันบน Windows จริง" เท่านั้น

---

## 1. ของที่พังทันที (ต้องแก้ก่อนถึงจะ start ได้)

### `common/hub/lock.py` — `import fcntl`

`fcntl` มีเฉพาะ Unix ดังนั้นบน Windows **import ไม่ผ่านตั้งแต่บรรทัดแรกของ service**

ทางแก้: แยกตามแพลตฟอร์มในไฟล์เดียว พฤติกรรมที่ต้องรักษาไว้คือ "ตัวที่สองต้องรู้ว่าชนกับ pid ไหน
แล้วออกเอง" และ "lock ต้องหลุดเองเมื่อ process ตาย" (ห้ามเหลือ pid file ค้างจนรอบหน้าไม่ยอมรัน)

```python
if os.name == "nt":
    import msvcrt
    # ล็อกไบต์แรกของไฟล์: msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
    # ปลดเมื่อ process ตายเหมือน flock / อ่าน pid ของเจ้าของต้องอ่านจากไฟล์ (ตำแหน่งอื่น)
else:
    import fcntl
```

ข้อควรระวัง: `LK_NBLCK` ล็อกจากตำแหน่ง cursor ปัจจุบัน 1 ไบต์ ต้อง `seek(0)` ก่อนเสมอ และการเขียน
pid ลงไฟล์ต้องไม่ทับไบต์ที่ล็อกอยู่ (เขียน pid ที่ offset 1 เป็นต้นไป หรือแยกไฟล์ `.pid` ต่างหาก)

---

## 2. path ที่ผูกกับ macOS

### 2.1 ไฟล์ผลลัพธ์ `/tmp/*` — 7 ไฟล์ใน 5 โมดูล

| ไฟล์ | บรรทัด | ค่า |
|---|---|---|
| `goldhub/service/cme_fetcher.py` | 75-79 | `JSON_OUT` `CLIP_OUT` `CURVE_OUT` `CHART_OUT` `EVENTVOL_OUT` |
| | 136 | `PREV_STATE` |
| | 698 | อ่าน `/tmp/gold_data.json` (hardcode ในฟังก์ชัน) |
| `goldhub/service/gold_fetcher.py` | 17-18 | `JSON_PATH` `LIVE_JS_PATH` |
| `goldhub/service/ticker.py` | 29 | `OUT` |
| `goldhub/service/api.py` | 66 | `FileCache("/tmp/cme_ticker.json")` |
| `weatherhub/service/weather_fetcher.py` | 16 | `JSON_PATH` |
| `weatherhub/service/rain_nowcast.py` | 23 | `STATE_PATH` |

ทางแก้ที่แนะนำ: ตัวช่วยกลางตัวเดียวใน `common/hub/` แล้วให้ทุกโมดูลเรียก

```python
def out_dir():
    return os.environ.get("APPHUB_OUT") or (tempfile.gettempdir() if os.name == "nt" else "/tmp")
```

**ห้ามเปลี่ยนค่าดีฟอลต์บน macOS** — widget ของ Übersicht, หน้ากราฟ `/tmp/cme_chart.html`
และสคริปต์ termux ล้วนอ้าง `/tmp/...` ตรงๆ อยู่ (ดู `goldhub/widgets/*.jsx` ฝั่ง fallback
และ `goldhub/mobile/termux/`)

### 2.2 cache ของ QuikStrike — `cme_fetcher.py:101`

`~/Library/Caches/cme-fetcher/qs_state.json` เก็บ **ตัวเบรก** (`paused_until`, `net_fail`) และ
cache ของ Vol2Vol/settle/event vol → ห้ามหายบ่อย ไม่งั้นจะยิง CME ถี่กว่าที่ออกแบบ

Windows: `%LOCALAPPDATA%\apphub\cme-fetcher\qs_state.json` (ผ่าน env `APPHUB_CACHE`)

### 2.3 `Store` — `common/hub/store.py:14`

มี `APPHUB_DATA` override อยู่แล้ว (ใช้ตอนขึ้น cloud/docker) แค่เติม fallback ของ Windows
ให้เป็น `%APPDATA%\apphub` แทน `~/Library/Application Support/apphub`

ของที่อยู่ใน Store และต้องรอด restart: `state/qs_last.json` (เวลา QuikStrike ครั้งล่าสุด),
`state/ticker_state.json` (baseline + ประวัติ ticker), `state/*.lock`, `history/`

### 2.4 curl ของ Homebrew — `cme_fetcher.py:133`, `gold_fetcher.py:22`

`CURL_BIN = "/usr/local/opt/curl/bin/curl"` — ที่ต้องระบุ path เต็มเพราะ curl ของ macOS
(LibreSSL) โดน investing บล็อก และ cron มองไม่เห็น curl ของ brew

Windows 10 ขึ้นไปมี `C:\Windows\System32\curl.exe` (สร้างจาก schannel) มาให้อยู่แล้ว
ทำเป็น env `CURL_BIN` แล้วดีฟอลต์เป็น `curl.exe` บน Windows / **ต้องทดสอบจริงว่า Yahoo กับ
เว็บ กทม. ยอมรับ** — ฝั่ง investing ไม่ผ่านทางนี้อยู่แล้ว (ใช้ `curl_cffi` ดู 3.1)

---

## 3. dependency

| ของ | Windows | หมายเหตุ |
|---|---|---|
| Python 3.9+ | ลงจาก python.org | โค้ดทั้งหมดเป็น stdlib ยกเว้นสองตัวล่าง |
| `curl_cffi` | `pip install curl_cffi` | มี wheel ของ Windows — **ยังไม่เคยทดสอบ** ว่า fingerprint chrome110/edge101 ยังผ่าน Cloudflare ของ investing ไหม |
| `requests`, `Pillow` | `pip install` | เฉพาะ weatherhub (ภาพเรดาร์ + nowcast) |
| Node/Babel | **ไม่ต้อง** | `api.py:81-82` หา node ของ Übersicht ถ้าไม่เจอจะข้ามการ build แล้วเสิร์ฟ `web/dist/gold-dashboard.js` ที่ commit ไว้ — หน้าเว็บทำงานได้ปกติ แค่แก้ `.jsx` แล้วไม่ rebuild ให้ |

---

## 4. ให้รันอัตโนมัติ (แทน launchd)

`goldhub/deploy/com.apphub.goldhub.plist` ทำสามอย่าง: RunAtLoad, KeepAlive, เขียน log
ต้องหาของเทียบเท่าบน Windows

**Task Scheduler** (ง่ายสุด ไม่ต้องลงอะไร)
- Trigger: `At startup` (+ `At log on` ถ้าต้องการ)
- Action: `pythonw.exe goldhub\service\app.py` (ใช้ `pythonw` ไม่งั้นมีหน้าต่าง console ค้าง)
- Settings: `Restart the task if it fails` ทุก 1 นาที (แทน KeepAlive) และ **ปิด**
  `Stop the task if it runs longer than...` (ดีฟอลต์ 3 วัน จะฆ่า daemon ทิ้ง)
- Conditions: ปิด `Start the task only if the computer is on AC power` ถ้าเป็นโน้ตบุ๊ก
- log: ต้อง redirect เอง (`app.py` เขียน stdout/stderr ล้วน) เช่นผ่าน `cmd /c ... >> log 2>&1`

**NSSM** ถ้าอยากได้ Service จริง (รันก่อน login, มี recovery ในตัว) — ต้องลงโปรแกรมเพิ่ม

---

## 5. หน้าจอบน Windows

- **ไม่มี Übersicht** = ไม่มีการ์ดลอยบน desktop การ์ดใน `goldhub/widgets/*.jsx` ใช้ไม่ได้ตรงๆ
- ตัวแทนคือ **หน้าเว็บ** `http://localhost:8787/dashboard` ซึ่งรันไฟล์ `.jsx` ตัวเดียวกัน
  เปิดแบบไร้กรอบให้เหมือน widget ได้: `msedge --app=http://localhost:8787/dashboard`
  (ใส่ใน Startup folder ได้ถ้าอยากให้เปิดเอง)
- **Rainmeter** กิน `GET /api/flat` ได้ตรงๆ (key=value บรรทัดละตัว ~58 บรรทัด) — ออกแบบ
  endpoint นี้ไว้เพื่อการนี้ตั้งแต่แรก ยังไม่มีคนเขียน skin
- ปุ่ม copy ของหน้าเว็บใช้ clipboard API ของเบราว์เซอร์ (ไม่ใช่ `pbcopy`) ใช้ได้บน Windows อยู่แล้ว

---

## 6. weatherhub (ถ้าจะย้ายด้วย)

- `rain_nowcast.py:155` แจ้งเตือนด้วย `osascript` ของ macOS → ต้องเปลี่ยนเป็น toast ของ Windows
  (เช่น PowerShell `New-BurntToastNotification` หรือ `win10toast`)
- เรดาร์เป็นภาพของ กทม. — ถ้าเครื่อง Windows ไม่ได้อยู่ไทยก็ไม่มีประโยชน์ จนกว่าจะทำเฟส 4
  (รับ lat/lon จากผู้เรียก)

---

## 7. กับดักที่ต้องระวัง

1. **ห้ามรันพร้อมกันสองเครื่อง** — flock/msvcrt กันได้แค่ภายในเครื่องเดียว ถ้า Mac กับ Windows
   รัน goldhub พร้อมกัน จะยิง QuikStrike/Barchart ซ้ำสองชุด ซึ่งเป็นสิ่งที่ทั้งโปรเจกต์พยายามเลี่ยง
   (ดูบันทึกเหตุการณ์ 20 ก.ย. ใน PLAN.md) — ถ้าจะย้าย ให้ `launchctl bootout` ฝั่ง Mac ก่อน
2. **IP ที่ใช้ยิง** — ถ้า Windows อยู่บ้านเดียวกันจะเป็น IP เดิม ไม่มีอะไรเปลี่ยน แต่ถ้าอยู่คนละที่
   ต้องถือว่าเป็น IP ใหม่ที่ยังไม่รู้ว่าโดน WAF ของ investing/Barchart หรือเปล่า
3. **เวลาและ timezone** — `cme_fetcher` คำนวณ session/DST ของ CT เอง (`us_dst`, `session_open_utc`)
   ใช้ UTC เป็นฐาน ไม่ได้พึ่ง timezone ของเครื่อง แต่ `ticker`/log แสดงเวลาท้องถิ่น
   ถ้าเครื่อง Windows ตั้ง timezone ไม่ใช่ไทย เวลาบนจอจะไม่ตรงกับที่คุยกันไว้
4. **`os.replace` atomic write** ใช้ได้บน Windows ✅ แต่จะ **fail ถ้าไฟล์ปลายทางเปิดค้างอยู่**
   โดยโปรแกรมอื่น (พฤติกรรมต่างจาก Unix) — ถ้าเปิด `cme_chart.html` ค้างในเบราว์เซอร์แล้วเจอ
   `PermissionError` ตอนเขียนทับ ให้สงสัยข้อนี้ก่อน
5. **ชื่อไฟล์ที่มี `|`** — symbol ของ leg แบบ `IY9U6|4400C` ใช้เป็น "ชื่อไฟล์" ไม่ได้บน Windows
   ตอนนี้ไม่มีที่ไหนเอาไปตั้งชื่อไฟล์ แต่ถ้าจะทำ cache รายเลกในอนาคตต้องระวัง

---

## 8. ลำดับที่แนะนำถ้าจะลงมือ

1. แก้ `lock.py` ให้ import ผ่านบน Windows (ข้อ 1) — ถ้าไม่ผ่านข้อนี้ ทดสอบอย่างอื่นไม่ได้เลย
2. รวม path เป็น `APPHUB_OUT` / `APPHUB_CACHE` / `APPHUB_DATA` (ข้อ 2) โดยดีฟอลต์ของ macOS
   ต้องเหมือนเดิมเป๊ะ แล้วรันบน Mac ให้ผ่านก่อน (ผลลัพธ์ต้องตรงกับ baseline เดิมทุกไบต์)
3. ค่อยไปลองบน Windows: รัน `python app.py` มือเปล่าก่อน ดู log ว่าผ่านถึงบรรทัด
   `ok [barchart]` ไหม — ตัวที่เสี่ยงสุดคือ `curl_cffi` กับ investing
4. ผ่านแล้วค่อยทำ Task Scheduler (ข้อ 4)
5. หน้าเว็บกับ Rainmeter (ข้อ 5) ทำทีหลังได้ ไม่กระทบตัวดึงข้อมูล
