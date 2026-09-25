#!/bin/bash
# ติดตั้ง goldhub เป็น LaunchAgent (เฟส 1)
# ใช้: bash install.sh          ติดตั้ง/โหลดใหม่
#      bash install.sh widgets   copy widget ขึ้น Übersicht อย่างเดียว
#      bash install.sh uninstall ถอดออก (widget ยังอยู่บนจอ)
set -e
LABEL=com.apphub.goldhub
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="$HERE/$LABEL.plist"

# --- widget -> Übersicht --------------------------------------------------- #
# โฟลเดอร์ widgets ของ Übersicht เป็น "ปลายทาง" เท่านั้น ไม่ใช่ git repo แล้ว
# (เลิกเป็น repo 25 ก.ย. 26 ประวัติเก่า 37 commit ย้ายมาอยู่ branch
#  archive/ubersicht-widgets ของ repo นี้) ต้นทางที่แก้ = widgets/ ใน repo นี้ที่เดียว
# ชื่อโฟลเดอร์มี Ü แบบ NFD ตามที่ macOS เก็บ -> ใช้ glob เลี่ยงปัญหา encoding
WIDGET=gold-dashboard.jsx
deploy_widget() {
  local dirs=("$HOME/Library/Application Support"/*bersicht/widgets)
  local dst="${dirs[0]}"
  if [ ! -d "$dst" ]; then
    echo "ข้าม widget: ไม่เจอโฟลเดอร์ Übersicht (ไม่ได้ลง / ไม่ใช่ Mac)"
    return 0
  fi
  cp "$HERE/../widgets/$WIDGET" "$dst/$WIDGET"
  echo "deploy $WIDGET -> $dst"   # Übersicht โหลดใหม่เองเมื่อไฟล์เปลี่ยน
}

if [ "$1" = "widgets" ]; then          # แก้ .jsx แล้วส่งขึ้นจอ ไม่ยุ่งกับ launchd
  deploy_widget
  exit 0
fi

# dist ของหน้าเว็บ (web/dist/*.js) ไม่ต้อง build ที่นี่ -- api.py สร้างให้เองเมื่อ .jsx ใหม่กว่า

if [ "$1" = "uninstall" ]; then
  launchctl bootout "gui/$UID/$LABEL" 2>/dev/null || launchctl unload "$PLIST" 2>/dev/null || true
  rm -f "$PLIST"
  echo "ถอด $LABEL แล้ว — อย่าลืม uncomment บรรทัด cme ใน crontab ถ้าจะกลับไปใช้ cron"
  echo "widget ยังอยู่บนจอ (ถอย daemon แล้ว widget อ่านไฟล์ /tmp ต่อได้เอง)"
  exit 0
fi

mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs/apphub"
cp "$SRC" "$PLIST"
launchctl bootout "gui/$UID/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$UID" "$PLIST" 2>/dev/null || launchctl load "$PLIST"
sleep 2
launchctl print "gui/$UID/$LABEL" 2>/dev/null | grep -E "state|pid" | head -3 || launchctl list | grep "$LABEL"
echo "log: ~/Library/Logs/apphub/goldhub.log"
deploy_widget
