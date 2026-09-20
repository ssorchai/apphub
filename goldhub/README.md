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

`indicator/dxy_pulse.pine` — ตัวเล็กแยกต่างหาก ไม่เกี่ยวกับ clip: จับ "การกระชาก" ของ
ดอลลาร์ด้วย z-score (ไม่ใช่ % ตั้งแต่เปิดตลาด) เพื่อดูก่อนเข้าไม้สวนว่าแรงที่ดันทอง
มาจากดอลลาร์หรือจากฝั่งทองเอง · ตั้งค่ามาสำหรับ TF 5 นาที (หน้าต่าง 3 แท่ง = 15 นาที)
ใช้ TVC:DXY เพราะ ICEUS:DX1! ดีเลย์ในบัญชีที่ใช้อยู่

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

## ของที่ยังรันอยู่จริงตอนนี้ (ยังไม่ย้าย)

- cron รัน `~/src/my-cronjob/cme_fetcher.py` + `gold_fetcher.py`
- Übersicht โหลด widget จาก `~/Library/Application Support/Übersicht/widgets/`

ไฟล์ใน repo นี้คือ **ต้นทางที่ทางการ** แก้ที่นี่ที่เดียว แล้วค่อย deploy ออกไป
(ระหว่างเฟสย้าย ยังต้อง copy ไปทับของเดิมเหมือนที่ทำอยู่)
