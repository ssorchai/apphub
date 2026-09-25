# เลิกใช้แล้ว (25 ก.ย. 2026) — ของจริงอยู่ที่ `claude_code/apphub`

**ห้ามแก้ไฟล์ในโฟลเดอร์นี้** ไม่มีอะไรในนี้ถูกรันหรือถูกอ่านโดยระบบอีก
งานทั้งหมดรวมอยู่ใน repo เดียวคือ apphub (github.com/ssorchai/apphub)

ไฟล์ทั้งหมดย้ายไปแล้ว:
- `fetchers/*.py` -> `apphub/goldhub/service/` + `apphub/weatherhub/service/`
- `widgets/*.jsx` -> `apphub/<hub>/widgets/` (สามการ์ดเดิมรวมเป็น `gold-dashboard.jsx`)
- `old/` -> `apphub/goldhub/legacy/first-version/` + `apphub/weatherhub/legacy/first-version/`
- `README.md` -> `apphub/goldhub/docs/pipeline-notes.md`

ประวัติ git ของโฟลเดอร์นี้ไม่หาย — fetch เข้าไปเป็น branch `archive/mac-widget` ของ apphub แล้ว
ดูได้ด้วย `git -C ~/src/claude_code/apphub log --oneline archive/mac-widget`

สำเนาทั้งโฟลเดอร์ (รวม .git) อยู่ใน `claude_code/_archive/retired-projects-2026-09-25.tar.gz`
