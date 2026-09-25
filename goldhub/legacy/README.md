# legacy — โค้ดที่เลิกใช้แล้ว เก็บไว้อ่านเท่านั้น

ห้ามเอาไปรัน ไม่มีอะไรในนี้ทำงานได้กับแหล่งข้อมูลปี 2026 แล้ว
ย้ายมาจาก `claude_code/cme_scraping` + `claude_code/mac_widget` ตอนรวม repo 25 ก.ย. 26

## `quikstrike/` — ยุคที่ scrape CME QuikStrike ด้วย Playwright (มิ.ย.–ก.ค. 2026)

| ไฟล์ | คืออะไร |
|---|---|
| `fetch_all.py` | ตัวหลัก ดึง Vol2Vol Expected Range ทั้ง Intraday + OI แบบ headless |
| `capture.py` | รุ่นแรกสุด ต้องคลิกเอง ใช้ดักดู network |
| `parse.py`, `build_table.py` | แกะ payload ที่ capture ไว้เป็นตาราง |
| `samples/` | payload + output จริงจาก 2–3 ก.ค. 26 ไว้เทียบ format |

**ทำไมตาย**: CME ถอดข้อมูล Vol2Vol Intraday ออก (ก.ย. 26) แล้ว WAF ของ
`www.cmegroup.com` แบน IP นี้จากการ scrape — ห้ามแตะโดเมนนั้นอีก ระบบจริงย้ายไปใช้
Barchart core-api ล้วนแล้ว (ดู `service/cme_fetcher.py`)

ตัวที่ดึงข้อมูลได้จริงตอนนั้นเหลือ payload ฝั่ง OI ของ Vol2Vol เท่านั้น
กลไกทั้งหมด (marker `$create(UserControlsV2.QuikOptionsV2V.Chart`, postback `lbOI`,
การ auto-login ด้วย Referer cmegroup.com) บันทึกไว้ใน memory ของ session

## `first-version/` — widget/fetcher รุ่นแรกก่อนปรับปรุง

`gold-update.jsx` + `gold_fetcher.py` รุ่นที่ยังใช้ Playwright เปิดเว็บอ่านราคา
(ของจริงตอนนี้เป็น HTTP ล้วน) รุ่นฝั่งอากาศอยู่ที่ `weatherhub/legacy/first-version/`
