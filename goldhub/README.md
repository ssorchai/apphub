# goldhub (พอร์ต 8787)

ทอง 0DTE: ดึง Barchart + QuikStrike + ราคาสด แล้วเสิร์ฟให้ widget / กราฟ / มือถือ

## ตารางงานในบริการ (ไม่ใช้ cron)

| งาน | คาบ | หมายเหตุ |
|---|---|---|
| ราคา future สด | 5 วินาที | investing + yahoo (ยกมาจาก gold_fetcher.py) |
| snapshot Barchart | 5 นาที | chain เดียวได้ volume/OI/bid-ask/smile → ใช้ทั้ง clip, กราฟ, ticker |
| QuikStrike | 1 ชั่วโมง | event vol / Vol2Vol / Settlement Sheet + cache 2 ชม. + ตัวเบรก |
| ticker diff | 5 นาที | ต่อจาก snapshot ในรอบเดียวกัน ไม่ดึงซ้ำ |
| housekeeping | วันละครั้ง | ลบข้อมูลเก่ากว่า 7 วัน |

## endpoint

`/api/state` `/api/clip` `/api/chart` `/api/flat` `/api/health`

## indicator/

`indicator/oi_block.pine` — indicator ฝั่ง TradingView ที่กิน clip จาก `/api/clip`
อยู่ในโฟลเดอร์เดียวกับ service เพราะ **format ของ clip กับตัว parser ใน Pine ต้องแก้คู่กันเสมอ**
(header `F:|D:|S:|IV:|IVCHG:|DTE:|IVS:|IVSCHG:` + บรรทัด `ID;` `OI;` `VS;`)
Pine ข้าม key ที่ไม่รู้จัก → เพิ่ม key ใหม่ได้โดยไม่ต้องอัปเดต indicator ทันที
แต่ถ้าเปลี่ยนความหมายของ key เดิม ต้องแก้ทั้งสองฝั่งในคอมมิตเดียวกัน

`indicator/dxy_pulse.pine` — ตัวเล็กแยกต่างหาก ไม่เกี่ยวกับ clip: แสดง **รูปคลื่น**ของแรง
ดอลลาร์เป็นแถบ z ใต้กราฟ (ตัวเลขอย่างเดียวบอกรูปทรงของคลื่นไม่ได้) รองรับสองไม้:
**A** ราคาถึง zone แล้ว DXY ฉีกจบ → ◆ บนกราฟราคา · **B** ราคาวนที่ zone แล้ว DXY เริ่มฉีก
→ ▲▼ (ทิศทองตรงข้าม DXY) · พื้นหลังกราฟติดสีเฉพาะช่วงที่ยังฉีกอยู่ (วาดข้ามแผงด้วย
`force_overlay` ของ Pine v6) · ช่องใส่ระดับ zone ทำให้ alert ยิงเฉพาะตอนราคาอยู่ใกล้ zone
ตั้งค่ามาสำหรับ TF 5 นาที (หน้าต่าง 3 แท่ง = 15 นาที) ใช้ TVC:DXY เพราะ ICEUS:DX1! ดีเลย์

ของเดิมอยู่ที่ `claude_code/tdw_indi/oi_block.pine` (git 14 คอมมิต) — ยังไม่ได้ลบ
ถ้าจะเลิกใช้ที่เดิม ค่อยใส่ README ชี้มาที่นี่

## โครงโฟลเดอร์

```
goldhub/
├── service/     cme_fetcher.py (Barchart+QuikStrike+clip+กราฟ), gold_fetcher.py (ราคาสด)
│                cme_ticker.py.old = ต้นฉบับ ก.ค. 2026 ยังรันไม่ได้ ใช้เป็นต้นแบบ logic
├── widgets/     cme-putcall.jsx (การ์ดหลัก), cme-ticker.jsx (ticker — ยังไม่ได้ต่อของใหม่)
├── indicator/   oi_block.pine — ฝั่ง TradingView ที่กิน /api/clip
├── mobile/      termux/ — สคริปต์บน Android (จะเปลี่ยนมาดึงผ่าน API แทนการ scrape เอง)
├── docs/        pipeline-notes.md (บันทึกกลไกทั้งหมด), INTRADAY-TICKER-EXPLAINED.md
└── deploy/      launchd plist / Dockerfile
```

## ต้นทาง / ปลายทาง

repo นี้เป็น **ต้นทางเดียว** แก้ที่นี่ที่เดียวแล้ว deploy ออกไป ไม่มี repo อื่นให้ sync
(cron ปิดหมดแล้ว 24 ก.ย. 26 / โฟลเดอร์ widgets ของ Übersicht เลิกเป็น git repo 25 ก.ย. 26
ประวัติเก่า 37 commit ย้ายมาอยู่ branch `archive/ubersicht-widgets` ของ repo นี้)

| ของ | ปลายทาง | คำสั่ง deploy |
|---|---|---|
| service | LaunchAgent `com.apphub.goldhub` | `bash deploy/install.sh` |
| `widgets/gold-dashboard.jsx` | `~/Library/Application Support/Übersicht/widgets/` | `bash deploy/install.sh widgets` |
| `web/dist/gold-dashboard.js` | เสิร์ฟจาก repo ตรงๆ | api.py build เองเมื่อ `.jsx` ใหม่กว่า |

`install.sh` เต็มรูป = ลง LaunchAgent + copy widget ให้ในตัว ส่วน `install.sh widgets`
คือ copy widget อย่างเดียว (ใช้ตอนแก้หน้าตา ไม่ต้องรีสตาร์ท daemon)
