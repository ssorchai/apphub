# เลิกใช้แล้ว (25 ก.ย. 2026) — ของจริงอยู่ที่ `claude_code/apphub`

**ห้ามแก้ไฟล์ในโฟลเดอร์นี้** ไม่มีอะไรในนี้ถูกรันหรือถูกอ่านโดยระบบอีก
งานทั้งหมดรวมอยู่ใน repo เดียวคือ apphub (github.com/ssorchai/apphub)

cron ถูกปิดหมดแล้ว 24 ก.ย. 26 — fetcher ทั้ง 4 ตัวรันเป็น LaunchAgent
(`com.apphub.goldhub` / `com.apphub.weatherhub`) จากไฟล์ใน `apphub/<hub>/service/` แทน
log ย้ายไป `~/Library/Logs/apphub/`

ประวัติ git ของโฟลเดอร์นี้ไม่หาย — fetch เข้าไปเป็น branch `archive/my-cronjob` ของ apphub แล้ว
ดูได้ด้วย `git -C ~/src/claude_code/apphub log --oneline archive/my-cronjob`

สำเนาทั้งโฟลเดอร์ (รวม .git) อยู่ใน `claude_code/_archive/retired-projects-2026-09-25.tar.gz`
