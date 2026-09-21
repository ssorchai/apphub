import base64
import json
import os
import time
import warnings
warnings.filterwarnings("ignore")  # กัน NotOpenSSLWarning ของ urllib3 เปื้อน log
import requests
from datetime import datetime

# ดึงภาพเรดาร์หนองจอก — แหล่งหลัก: เว็บสำนักการระบายน้ำ กทม. (ต้นทางเรดาร์จริง)
# fallback: TMD (mirror, อยู่หลัง Imperva WAF ที่เคย block IP เรา — แตะเฉพาะตอน กทม. ล่ม)
# มารยาทกันโดน block: 1 request ต่อรอบ, Referer ถูกต้อง, ไม่ retry รัวในรอบเดียว
BMA_PAGE_URL = "https://weather.bangkok.go.th/Radar/RadarNongchok.aspx"
BMA_IMG_URL = "https://weather.bangkok.go.th/Radar/ImageHandlerNongchok.ashx"
TMD_IMG_URL = "https://weather.tmd.go.th/pic_bmanck.jpg"
JSON_PATH = "/tmp/weather_meta.json"

HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
MIN_IMAGE_BYTES = 5000  # กันภาพเสีย/หน้า error มาแทนภาพจริง


def atomic_write(path, obj):
    temp = path + ".tmp"
    with open(temp, "w") as f:
        json.dump(obj, f)
    os.replace(temp, path)


def fetch_bma(session):
    """ตัวส่งภาพของเว็บ กทม. ยอมให้ดึงเมื่อมี Referer ถูกต้อง (กัน hotlink)
    cert chain ของเขาไม่ครบ เลยต้อง verify=False"""
    r = session.get(
        "{}?{}".format(BMA_IMG_URL, datetime.now().strftime("%Y%m%d%H%M%S")),
        headers=dict(HEADERS, Referer=BMA_PAGE_URL), timeout=30, verify=False)
    r.raise_for_status()
    ct = r.headers.get("Content-Type", "")
    if not ct.startswith("image"):
        raise ValueError("got {} instead of image".format(ct or "unknown"))
    return r.content, ct.split(";")[0]


def fetch_tmd(session):
    r = session.get(TMD_IMG_URL, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return r.content, r.headers.get("Content-Type", "image/jpeg").split(";")[0]


def main():
    session = requests.Session()
    img_data = mime = via = None
    errors = []
    for name, fetch in (("BMA", fetch_bma), ("TMD", fetch_tmd)):
        try:
            img_data, mime = fetch(session)
            if len(img_data) < MIN_IMAGE_BYTES:
                raise ValueError("image too small ({} bytes)".format(len(img_data)))
            via = name
            break
        except Exception as e:
            errors.append("{}: {}".format(name, e))
            img_data = None
    if img_data is None:
        raise RuntimeError("all sources failed — " + "; ".join(errors))
    if errors:
        print("⚠️ fallback in use: {}".format("; ".join(errors)))

    metadata = {
        "last_update": datetime.now().strftime("%H:%M"),
        "source": "BMA Radar (Nong Chok)",
        "via": via,
        "mime": mime,
        "img_base64": base64.b64encode(img_data).decode("utf-8"),
        "ts": int(time.time()),
    }
    atomic_write(JSON_PATH, metadata)
    print("✅ radar updated ({} KB via {})".format(len(img_data) // 1024, via))


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
