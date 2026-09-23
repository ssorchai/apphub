# apphub

บริการเก็บข้อมูล + แสดงผล แยกเป็นบริการอิสระต่อกัน หนึ่งงาน = หนึ่งโฟลเดอร์
(service + widget ของงานนั้นอยู่ด้วยกัน) โครงเหมือนกันทุกงาน หน้าจอฝั่งไหนก็ดึงได้
ด้วยวิธีเดียวกัน — Übersicht บน Mac, เบราว์เซอร์, Termux บน Android, Rainmeter บน Windows

```
apphub/
├── common/hub/        skeleton ใช้ร่วม: scheduler, HTTP server, state store, retention, health
├── goldhub/           ทอง 0DTE (พอร์ต 8787)
│   ├── service/       ตัวดึงข้อมูล + ตารางเวลา + API
│   ├── widgets/       Übersicht widget + หน้ากราฟ
│   └── deploy/        launchd plist / Dockerfile
└── weatherhub/        อากาศ (พอร์ต 8788)
    ├── service/
    ├── widgets/
    └── deploy/
```

แผนย้ายทีละเฟสอยู่ที่ [PLAN.md](PLAN.md) · โน้ตสำหรับพอร์ตไป Windows: [docs/windows.md](docs/windows.md)

## หลักการ

- **ตัวเก็บข้อมูลแยกจากตัวแสดงผล** บริการเป็น daemon ตัวเดียวต่องาน มีตารางเวลาในตัว
  (ไม่ใช้ cron) แล้วเปิด HTTP API ที่ localhost หน้าจอทุกตัวกินข้อมูลจาก API เดียวกัน
- **แต่ละงานพังแยกกัน** goldhub ล่มไม่กระทบ weatherhub และ deploy แยกกันได้
- **stdlib อย่างเดียว** (urllib + http.server + threading) ให้รันได้ทั้ง macOS และ Linux/cloud
  โดยไม่ต้องลงอะไรเพิ่ม
- **ข้อมูลเก็บ 7 วัน** ใต้ `~/Library/Application Support/apphub/<service>/` (macOS)
  หรือ `$APPHUB_DATA` (cloud) มีงานล้างของเก่าทุกวัน

## API ที่ทุกบริการต้องมี

| endpoint | คืออะไร |
|---|---|
| `GET /api/state` | JSON ก้อนหลัก มี `schema_version` เสมอ / รองรับ `?fields=a,b` |
| `GET /api/flat` | `key=value` บรรทัดละตัว สำหรับ Rainmeter / shell / Excel |
| `GET /api/health` | งานแต่ละตัวรันล่าสุดเมื่อไหร่ สำเร็จไหม รอบถัดไปเมื่อไหร่ |
| `GET /api/chart` | หน้าเว็บของงานนั้น (ถ้ามี) |

รองรับ `ETag` / `If-None-Match` ให้ client ที่ poll บ่อย (มือถือ) ได้ `304` แทนก้อนเต็ม
และใส่ CORS header ให้คนอื่นเอาไปต่อยอดได้

## endpoint เฉพาะงาน

- **goldhub**: `GET /api/clip` — ข้อความ paste ลงช่อง P/C ของ indicator ใน TradingView
- **weatherhub**: `GET /api/state?lat=&lon=` — ข้อมูลตามพิกัดที่ผู้เรียกส่งมา
