# weatherhub (พอร์ต 8788)

อากาศ: โครงเดียวกับ goldhub แต่**รับพิกัดจากผู้เรียก** เพื่อให้ deploy ขึ้น cloud แล้ว
มือถือส่ง GPS มาได้

## ต่างจาก goldhub

- `GET /api/state?lat=13.75&lon=100.5` — ไม่ส่งพิกัดมาก็ใช้ค่า default ในคอนฟิก
- cache ต่อ "ช่องตาราง" ปัดพิกัดเป็นกริด (~0.05°) กันยิง upstream ซ้ำและกันเก็บพิกัดตรงๆ
- เรดาร์เป็นภาพเฉพาะพื้นที่ (BMA = กรุงเทพฯ) เลือก layer ตาม bbox ถ้าอยู่นอกพื้นที่ = ไม่มีเรดาร์

## สถานะตอนนี้ (25 ก.ย. 2026)

daemon `com.apphub.weatherhub` (ย้ายจาก cron 21 ก.ย.) + API อ่านอย่างเดียวที่ 8788 (25 ก.ย.)

- `GET /api/state?lat=&lon=` -> `point` (พิกัดที่ปัดแล้ว, `in_coverage`, `distance_km`,
  `bearing_deg`, `img_pct` = ตำแหน่งบนภาพเรดาร์เป็น %), `radar` (meta ของภาพล่าสุด),
  `nowcast` (ETA ฝนหนักเข้ารัศมี 10 กม. ของจุดนั้น จากรอบเช็ค 16:xx ล่าสุด หรือ null)
- `GET /api/radar` -> ภาพเรดาร์ล่าสุด (jpeg) / `GET /api/health`
- `GET /api/frames?n=12` + `GET /api/frame?ts=` -> เฟรมย้อนหลัง (ภาพนิ่งที่งาน radar ดึงอยู่แล้ว เก็บ 2 ชม.
  ใน <store>/frames/ ภาพซ้ำไม่เก็บ -- ดู service/frames.py) ให้หน้าเว็บเล่นเป็นภาพเคลื่อนไหว ไม่ยิง กทม. เพิ่ม
- `GET /dashboard` -> หน้าเว็บเรดาร์ (radar-weather.jsx ตัวเดียวกัน โหมด WEB วาดเป็นหน้าเว็บเต็มรูป: ภาพใหญ่ + ตัวเล่นเฟรม + แผงสถานที่/ฝน)
  การ์ดบน desktop คลิกเดียว = เปิดหน้านี้ / บนหน้าเว็บดับเบิลคลิก = เรดาร์ loop ของ กทม.
- ค่ารายจุดคิดจากเรดาร์ที่มีอยู่แล้วล้วนๆ ไม่มีแหล่งอื่น และ API ไม่ยิง upstream เอง
- widget `radar-weather.jsx` ขอพิกัดผ่าน geolocation ของ Übersicht แล้วเรียก API (ถอยไปอ่าน /tmp ถ้า API ล่ม)
- ยังไม่ทำ: Dockerfile

- งาน `radar` ทุก 5 นาที = `weather_fetcher.main()` เขียน `/tmp/weather_meta.json`
- งาน `nowcast` ทุก 5 นาที = `rain_nowcast.run_check()` ซึ่งตัดสินใจเฉพาะ
  16:00/16:15/16:30/16:45 (รับคลาดเคลื่อนได้ 2 นาที) เตือนแล้วจบทั้งวัน
- สองงานนี้ **แยกกันตั้งใจ** ดึงภาพพังไม่ควรทำให้ nowcast ไม่ทำงาน (ของเดิมก็แยก)
- ทั้งคู่ตั้ง `align=True` ให้ยึดนาฬิกาจริงแบบ cron (:00 :05 :10 …) ไม่ใช่นับต่อจากรอบที่แล้ว
  ซึ่งจะเลื่อนสะสมจนหลุดหน้าต่างเวลาของ nowcast

ติดตั้ง/ถอด: `bash deploy/install.sh` / `bash deploy/install.sh uninstall`
log: `~/Library/Logs/apphub/weatherhub.log`

## ที่มาของโค้ดเดิม

- `my-cronjob/weather_fetcher.py`, `my-cronjob/rain_nowcast.py` (คัดลอกมาทั้งไฟล์ ไม่แก้ logic)
