# ย้ายแล้ว → apphub/goldhub/

- `widgets/cme-putcall.jsx` → `apphub/goldhub/widgets/`
- `fetchers/cme_fetcher.py` → `apphub/goldhub/service/`
- `README.md` (บันทึกกลไกทั้งหมดของ pipeline) → `apphub/goldhub/docs/pipeline-notes.md`

**ห้ามแก้ไฟล์ในโฟลเดอร์นี้อีก** เก็บไว้เป็นประวัติเท่านั้น
(ย้าย 20 ก.ย. 2026 / สำเนาสำรอง: `claude_code/_archive/mac_widget-2026-09-20.tar.gz`)

หมายเหตุ: ตัวที่ cron รันจริงตอนนี้ยังเป็น `~/src/my-cronjob/cme_fetcher.py`
และ widget ที่แสดงผลจริงคือ `~/Library/Application Support/Übersicht/widgets/`
จะเปลี่ยนมาใช้ apphub เมื่อทำเฟส 1 เสร็จ
