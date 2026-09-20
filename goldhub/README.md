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

ของเดิมอยู่ที่ `claude_code/tdw_indi/oi_block.pine` (git 14 คอมมิต) — ยังไม่ได้ลบ
ถ้าจะเลิกใช้ที่เดิม ค่อยใส่ README ชี้มาที่นี่

## ที่มาของโค้ดเดิม

- `my-cronjob/cme_fetcher.py` → service/ (Barchart, QuikStrike, clip, กราฟ)
- `my-cronjob/gold_fetcher.py` → service/ (ราคาสด, curve)
- `cme_scraping/cme_ticker.py` → service/ (ticker — ต้องเขียนส่วนดึงข้อมูลใหม่เป็น Barchart)
- `mac_widget/widgets/cme-putcall.jsx` → widgets/
- `cme_scraping/cme-ticker.jsx` → widgets/
