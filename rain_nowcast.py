"""ตรวจฝนจากภาพเรดาร์ loop (nowcasting) แล้วแจ้งเตือนเมื่อฝนอยู่ใน/กำลังเข้ารัศมีรอบ Office/บ้าน

หลักการ: โหลด pic_bmancLoop.gif (12 frames ห่าง 5 นาที) → แยก pixel ฝนตามสี dBZ
→ เทียบ frame เก่า/ใหม่หา motion vector → ฉายไปข้างหน้า 60 นาที
เรียกใช้จาก weather_fetcher.py ทุกรอบ cron แต่ตัดสินใจเฉพาะ 16:00/16:15/16:30/16:45
เจอครั้งเดียว = จบทั้งวัน (แชร์ state กับไฟล์เดิม)

ทดสอบ: python3 rain_nowcast.py --test  (ข้าม gate เวลา/วัน ไม่ส่ง notification)
        python3 rain_nowcast.py --force (ข้าม gate และส่ง notification จริง)
"""
import json
import math
import os
import subprocess
import sys
import warnings
warnings.filterwarnings("ignore")
import requests
from datetime import datetime
from io import BytesIO
from PIL import Image, ImageSequence

LOOP_URL = "https://weather.tmd.go.th/pic_bmancLoop.gif"
STATE_PATH = "/tmp/weather_notify_state.json"  # ครั้งเดียวต่อวัน
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

# ---- Georeference (calibrate จากภาพจริง 2026-07-02) ----
RADAR_LATLON = (13.855, 100.856)   # เรดาร์หนองจอก = ศูนย์กลางวงแหวน
CENTER_PX = (483.0, 400.0)         # pixel ศูนย์กลางวงแหวนในภาพ 965x800
KM_PER_PX = 120.0 / 399.0          # วง 120 km รัศมี 399 px -> 0.3008 km/px

LOCATIONS = {
    "Office": (13.7733, 100.5426),
    "Home": (13.8873269, 100.6026284),
}
RADIUS_KM = 10.0

CHECK_HOUR = 16
CHECK_MINUTES = (0, 15, 30, 45)    # cron ทุก 5 นาที เอาเฉพาะ tick ที่ตรงหรือเลยมา <=2 นาที
FRAME_MINUTES = 5                  # ระยะห่างระหว่าง frame ใน GIF
LOOKAHEAD_MIN = 60
DS = 2                             # downsample 2 เท่าเพื่อความเร็ว (1 px = ~0.6 km)

THAI_DIRS = ["เหนือ", "ตะวันออกเฉียงเหนือ", "ตะวันออก", "ตะวันออกเฉียงใต้",
             "ใต้", "ตะวันตกเฉียงใต้", "ตะวันตก", "ตะวันตกเฉียงเหนือ"]


def latlon_to_ds_px(lat, lon):
    dlat_km = (lat - RADAR_LATLON[0]) * 110.9
    dlon_km = (lon - RADAR_LATLON[1]) * 111.32 * math.cos(math.radians(RADAR_LATLON[0]))
    x = CENTER_PX[0] + dlon_km / KM_PER_PX
    y = CENTER_PX[1] - dlat_km / KM_PER_PX
    return (x / DS, y / DS)


def is_heavy(c):
    """เหลือง/ส้ม/แดง/ชมพู = ฝนปานกลางขึ้นไป (~>=31 dBZ) — ใช้ตัดสินเตือน"""
    r, g, b = c
    if r >= 180 and g >= 120 and b <= 120: return True   # เหลือง/ส้ม
    if r >= 170 and g <= 90 and b <= 90: return True     # แดง
    if r >= 200 and b >= 150 and g <= 120: return True   # ชมพู/ม่วงแดง
    return False


def is_rain(c):
    """รวมเขียว (ฝนอ่อน) ด้วย — ใช้จับ motion ให้มีสัญญาณเยอะขึ้น"""
    r, g, b = c
    return is_heavy(c) or (g >= 140 and r <= 120 and b <= 120)


def rain_points(frame):
    """คืน (all_points, heavy_points) เป็น set ของพิกัด downsampled"""
    small = frame.resize((frame.width // DS, frame.height // DS))
    px = small.load()
    all_pts, heavy_pts = set(), set()
    for y in range(25, small.height - 10):
        for x in range(40, small.width - 5):          # ตัดแถบ legend ซ้าย
            if x >= 400 and y >= 330:                 # ตัดกล่องข้อความมุมล่างขวา
                continue
            c = px[x, y]
            if is_heavy(c):
                heavy_pts.add((x, y)); all_pts.add((x, y))
            elif is_rain(c):
                all_pts.add((x, y))
    return all_pts, heavy_pts


def motion_vector(old_pts, new_pts, steps):
    """หา shift (ds px ต่อ frame) ที่ทำให้ mask เก่าซ้อนทับ mask ใหม่มากสุด"""
    if len(old_pts) < 30 or len(new_pts) < 30:
        return None
    sample = list(old_pts)
    if len(sample) > 1500:
        sample = sample[:: len(sample) // 1500 + 1]
    best_score, best = -1, (0, 0)
    for dy in range(-50, 51, 2):
        for dx in range(-50, 51, 2):
            score = sum(1 for (x, y) in sample if (x + dx, y + dy) in new_pts)
            if score > best_score:
                best_score, best = score, (dx, dy)
    # ต้องซ้อนทับกันจริงพอสมควร ไม่งั้นถือว่าไม่มีทิศทางชัด (เช่นฝน pop-up กับที่)
    if best_score < len(sample) * 0.15:
        return None
    return (best[0] / steps, best[1] / steps)


def describe_motion(v):
    speed_kmh = math.hypot(v[0], v[1]) * DS * KM_PER_PX * (60.0 / FRAME_MINUTES)
    # ทิศที่ฝน "มาจาก" = สวนทางกับ vector การเคลื่อนที่ (แกน y ของภาพชี้ลง)
    bearing = (math.degrees(math.atan2(-v[0], v[1])) + 360) % 360
    return THAI_DIRS[int((bearing + 22.5) // 45) % 8], speed_kmh


def check_locations(heavy_pts, v):
    """คืน dict {ชื่อจุด: อีกกี่นาที (0 = ตกในรัศมีแล้ว)}"""
    results = {}
    r = RADIUS_KM / KM_PER_PX / DS
    for name, (lat, lon) in LOCATIONS.items():
        cx, cy = latlon_to_ds_px(lat, lon)
        if any((x - cx) ** 2 + (y - cy) ** 2 <= r * r for (x, y) in heavy_pts):
            results[name] = 0
            continue
        if v:
            for t in range(1, LOOKAHEAD_MIN // FRAME_MINUTES + 1):
                ox, oy = v[0] * t, v[1] * t
                if any((x + ox - cx) ** 2 + (y + oy - cy) ** 2 <= r * r for (x, y) in heavy_pts):
                    results[name] = t * FRAME_MINUTES
                    break
    return results


def build_message(results, v):
    parts = []
    for name in ("Office", "Home"):
        if name not in results:
            continue
        eta = results[name]
        if eta == 0:
            parts.append("ฝนอยู่ในรัศมี 10 กม. ของ {} แล้ว".format(name))
        else:
            parts.append("ฝนจะถึง {} ในอีก ~{} นาที".format(name, eta))
    msg = " / ".join(parts)
    if v:
        direction, speed = describe_motion(v)
        msg += " (มาจากทิศ{} ~{:.0f} กม./ชม.)".format(direction, speed)
    return msg


def notify(msg):
    subprocess.run([
        "osascript", "-e",
        'display notification "{}" with title "BMA Radar Alert" sound name "Glass"'.format(msg),
    ], check=True)


def already_notified_today(today):
    try:
        with open(STATE_PATH) as f:
            return json.load(f).get("date") == today
    except Exception:
        return False


def save_state(today, extra):
    temp = STATE_PATH + ".tmp"
    data = {"date": today}
    data.update(extra)
    with open(temp, "w") as f:
        json.dump(data, f)
    os.replace(temp, STATE_PATH)


def run_check(force=False, dry_run=False):
    now = datetime.now()
    if not force:
        in_window = now.hour == CHECK_HOUR and any(0 <= now.minute - m <= 2 for m in CHECK_MINUTES)
        if not in_window:
            return
        if already_notified_today(now.strftime("%Y-%m-%d")):
            return

    r = requests.get(LOOP_URL, headers=HEADERS, timeout=60)
    r.raise_for_status()
    gif = Image.open(BytesIO(r.content))
    frames = [f.convert("RGB") for f in ImageSequence.Iterator(gif)]
    if len(frames) < 2:
        raise ValueError("loop gif has {} frame(s)".format(len(frames)))

    # ใช้ frame ~30 นาทีก่อน เทียบ frame ล่าสุด หา motion
    back = min(6, len(frames) - 1)
    old_all, _ = rain_points(frames[-1 - back])
    new_all, new_heavy = rain_points(frames[-1])
    v = motion_vector(old_all, new_all, steps=back)
    results = check_locations(new_heavy, v)

    print("🌧 nowcast: rain_px={} heavy_px={} motion={} results={}".format(
        len(new_all), len(new_heavy),
        "({:.1f},{:.1f})".format(v[0], v[1]) if v else None, results))

    if not results:
        return
    msg = build_message(results, v)
    if dry_run:
        print("DRY-RUN notification:", msg)
        return
    notify(msg)
    save_state(now.strftime("%Y-%m-%d"), {"source": "radar", "results": results})
    print("🔔 radar notification sent: {}".format(msg))


if __name__ == "__main__":
    run_check(force=True, dry_run="--test" in sys.argv)
