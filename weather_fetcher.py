import base64
import json
import os
import re
import time
import warnings
warnings.filterwarnings("ignore")  # กัน NotOpenSSLWarning ของ urllib3 เปื้อน log
import requests
from datetime import datetime

# ดึงภาพเรดาร์ BMA (หนองจอก) จากหน้า TMD ตรงๆ ด้วย HTTP — ไม่ต้องใช้ Playwright
PAGE_URL = "https://weather.tmd.go.th/bma_nck.php"
FALLBACK_IMG_URL = "https://weather.tmd.go.th/pic_bmanck.jpg"
JSON_PATH = "/tmp/weather_meta.json"

HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
MIN_IMAGE_BYTES = 5000  # กันภาพเสีย/หน้า error มาแทนภาพจริง


def atomic_write(path, obj):
    temp = path + ".tmp"
    with open(temp, "w") as f:
        json.dump(obj, f)
    os.replace(temp, path)


def find_radar_url(session):
    """หา src ของภาพเรดาร์จากหน้าเว็บ ถ้าโครงหน้าเปลี่ยนก็ fallback เป็น URL ตรง"""
    try:
        html = session.get(PAGE_URL, headers=HEADERS, timeout=30).text
        for src in re.findall(r'<img[^>]+src="([^"]+)"', html, re.IGNORECASE):
            if "bmanck" in src.lower() or "bma" in src.lower():
                if src.startswith("http"):
                    return src
                return "https://weather.tmd.go.th/" + src.lstrip("/")
    except Exception as e:
        print("⚠️ page fetch failed, using fallback URL: {}".format(e))
    return FALLBACK_IMG_URL


def main():
    session = requests.Session()
    img_url = find_radar_url(session)

    r = session.get(img_url, headers=HEADERS, timeout=60)
    r.raise_for_status()
    img_data = r.content
    if len(img_data) < MIN_IMAGE_BYTES:
        raise ValueError("image too small ({} bytes), keeping previous data".format(len(img_data)))

    mime = r.headers.get("Content-Type", "image/jpeg").split(";")[0]
    metadata = {
        "last_update": datetime.now().strftime("%H:%M"),
        "source": "BMA Radar (Nong Chok)",
        "mime": mime,
        "img_base64": base64.b64encode(img_data).decode("utf-8"),
        "ts": int(time.time()),
    }
    atomic_write(JSON_PATH, metadata)
    print("✅ radar updated ({} KB)".format(len(img_data) // 1024))


if __name__ == "__main__":
    exit_code = 0
    try:
        main()
    except Exception as e:
        # ล้มเหลว = ไม่แตะไฟล์เดิม widget จะยังโชว์ภาพล่าสุดที่ดีอยู่
        print("❌ Error: {}".format(e))
        exit_code = 1

    # แจ้งเตือนฝนจากเรดาร์ (nowcasting) แยกอิสระจากการดึงภาพ — พังฝั่งหนึ่งอีกฝั่งยังทำงาน
    # ตัดสินใจเฉพาะ 16:00/16:15/16:30/16:45 เจอครั้งเดียวหยุดทั้งวัน (ดู rain_nowcast.py)
    try:
        import rain_nowcast
        rain_nowcast.run_check()
    except Exception as e:
        print("⚠️ rain nowcast check failed: {}".format(e))

    raise SystemExit(exit_code)
