#!/bin/bash
# ติดตั้ง weatherhub เป็น LaunchAgent (เฟส 1 - ย้ายจาก cron 21 ก.ย.)
# ใช้: bash install.sh          ติดตั้ง/โหลดใหม่
#      bash install.sh uninstall ถอดออก (กลับไปใช้ cron ได้ทันที)
set -e
LABEL=com.apphub.weatherhub
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
SRC="$(cd "$(dirname "$0")" && pwd)/$LABEL.plist"

if [ "$1" = "uninstall" ]; then
  launchctl bootout "gui/$UID/$LABEL" 2>/dev/null || launchctl unload "$PLIST" 2>/dev/null || true
  rm -f "$PLIST"
  echo "ถอด $LABEL แล้ว — อย่าลืม uncomment บรรทัด weather ใน crontab ถ้าจะกลับไปใช้ cron"
  exit 0
fi

mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs/apphub"
cp "$SRC" "$PLIST"
launchctl bootout "gui/$UID/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$UID" "$PLIST" 2>/dev/null || launchctl load "$PLIST"
sleep 2
launchctl print "gui/$UID/$LABEL" 2>/dev/null | grep -E "state|pid" | head -3 || launchctl list | grep "$LABEL"
echo "log: ~/Library/Logs/apphub/weatherhub.log"
