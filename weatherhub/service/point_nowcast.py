"""nowcast รายจุด: ฝนจะเริ่มตก / หยุดตกกี่โมง ที่พิกัดไหนก็ได้ -- คิดจากเฟรมที่เก็บไว้ (frames.py)

ต่างจาก rain_nowcast.py (ตัวแจ้งเตือน 16:xx ใช้ loop GIF ของ กทม. + รัศมี 10 กม.):
  - ใช้ภาพนิ่งที่งาน radar ดึงอยู่แล้ว -> คิดได้ทุก 5 นาทีโดยไม่ยิงต้นทางเพิ่ม
  - ถามที่ "จุด" (รัศมี POINT_RADIUS_KM) ไม่ใช่ "มีฝนในรัศมี 10 กม." -- บอกได้ทั้งเริ่มและหยุด
  - หา motion เฉพาะหน้าต่างรอบพื้นที่ที่สนใจ (MOTION_WINDOW_KM) ไม่ใช่ทั้งภาพ 240 กม.
    ฝนคนละฟากของเรดาร์มักเคลื่อนคนละทาง ใช้ vector เดียวทั้งภาพจะเพี้ยน
  - ยังเป็น advection ล้วน (ฝนเคลื่อนตามทิศเดิม ไม่เกิดใหม่/ไม่สลาย) เหมือนตัวเดิม
    ฝน convective ที่ก่อตัวกับที่จะทายไม่ได้ -- ความแม่นลดลงเร็วหลัง ~30 นาที

เวลา: t=0 = เวลาที่ดึงเฟรมล่าสุดได้ (ครั้งแรกที่ภาพเปลี่ยน) ภาพเรดาร์จริงช้ากว่านั้น
(เห็นบนภาพ 15:35 ตอนดึง 15:42 วันที่ 25 ก.ย.) -> ชดเชยด้วย PRODUCT_LAG_MIN

snapshot (/tmp/weather_point_nowcast.json) เก็บ mask ฝนแบบ run-length ต่อแถว ให้ API
คิดพิกัดไหนก็ได้เองโดยไม่ต้องเปิดภาพ
"""
import json
import math
import os
import time

from PIL import Image

import frames
import rain_nowcast as rn

SNAP_PATH = "/tmp/weather_point_nowcast.json"
POINT_RADIUS_KM = 2.0          # "ฝนตกที่จุดนี้" = มีฝนในรัศมีนี้ (ภาพ 1 ds px ~0.6 กม.)
STEP_MIN = 5
LOOKAHEAD_MIN = 60
REF_TARGET_MIN = 30            # หา motion เทียบกับเฟรมราว 30 นาทีก่อน
REF_MIN_MIN, REF_MAX_MIN = 10, 50
MOTION_WINDOW_KM = 60          # หน้าต่างรอบ AOI สำหรับหา motion
AOI = rn.LOCATIONS["Office"]   # ศูนย์กลางพื้นที่ที่สนใจ (กรุงเทพฯ)
PRODUCT_LAG_MIN = 7            # ภาพเรดาร์ช้ากว่าเวลาที่ดึงได้ (วัดจากเวลาบนภาพ 1 ครั้ง -- ปรับได้)


def _window(pts, cx, cy, r):
    return {(x, y) for (x, y) in pts if (x - cx) ** 2 + (y - cy) ** 2 <= r * r}


def _rle(pts):
    """{y: [[x0, x1], ...]} -- 55k จุดเหลือไม่กี่พันช่วง"""
    rows = {}
    for x, y in sorted(pts, key=lambda p: (p[1], p[0])):
        r = rows.setdefault(y, [])
        if r and r[-1][1] == x - 1:
            r[-1][1] = x
        else:
            r.append([x, x])
    return {str(y): v for y, v in rows.items()}


def unrle(rows):
    return {(x, int(y)) for y, spans in rows.items() for a, b in spans for x in range(a, b + 1)}


def _pick_ref(listing):
    """เฟรมอ้างอิงสำหรับ motion: ใกล้ 30 นาทีก่อนเฟรมล่าสุดที่สุด (ในช่วง 10-50 นาที)"""
    latest = listing[-1][0]
    cands = [(abs((latest - ts) / 60 - REF_TARGET_MIN), ts, n) for ts, n in listing[:-1]
             if REF_MIN_MIN <= (latest - ts) / 60 <= REF_MAX_MIN]
    return min(cands)[1:] if cands else None


def update(folder):
    """วิเคราะห์เฟรมล่าสุดแล้วเขียน snapshot -- คืน dict สรุปสั้นๆ (หรือ None ถ้ายังไม่มีเฟรม)"""
    listing = frames.listing(folder)
    if not listing:
        return None
    ts, name = listing[-1]
    rain, heavy = rn.rain_points(Image.open(os.path.join(folder, name)).convert("RGB"))
    motion = ref_ts = None
    ref = _pick_ref(listing)
    if ref:
        ref_ts, ref_name = ref
        old, _ = rn.rain_points(Image.open(os.path.join(folder, ref_name)).convert("RGB"))
        cx, cy = rn.latlon_to_ds_px(*AOI)
        r = MOTION_WINDOW_KM / rn.KM_PER_PX / rn.DS
        steps = (ts - ref_ts) / 60.0 / STEP_MIN
        v = rn.motion_vector(_window(old, cx, cy, r), _window(rain, cx, cy, r), steps)
        if v is None:        # ในหน้าต่างมีฝนน้อยไป -> ลองทั้งภาพ
            v = rn.motion_vector(old, rain, steps)
        motion = v
    snap = {"ts": ts, "ref_ts": ref_ts, "made": int(time.time()),
            "motion": list(motion) if motion else None,
            "rain_px": len(rain), "heavy_px": len(heavy),
            "rain": _rle(rain), "heavy": _rle(heavy)}
    if motion:
        d, spd = rn.describe_motion(motion)
        snap["from_dir"], snap["speed_kmh"] = d, round(spd, 1)
    tmp = SNAP_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(snap, f, separators=(",", ":"))
    os.replace(tmp, SNAP_PATH)
    return {k: snap.get(k) for k in ("ts", "ref_ts", "rain_px", "heavy_px", "from_dir", "speed_kmh")}


def load_snapshot(txt):
    s = json.loads(txt)
    s["rain"], s["heavy"] = unrle(s["rain"]), unrle(s["heavy"])
    return s


_OFFSETS = None


def _offsets():
    global _OFFSETS
    if _OFFSETS is None:
        r = POINT_RADIUS_KM / rn.KM_PER_PX / rn.DS
        n = int(math.ceil(r))
        _OFFSETS = [(dx, dy) for dx in range(-n, n + 1) for dy in range(-n, n + 1) if dx * dx + dy * dy <= r * r]
    return _OFFSETS


def forecast(snap, lat, lon, now=None):
    """timeline ของจุดนี้: level ทุก STEP_MIN นาที (0 ไม่มี / 1 ฝน / 2 ฝนหนัก) นับจาก "ตอนนี้"

    ตำแหน่งของฝนที่เวลา t = mask ล่าสุดเลื่อนไป v*t -> จุด p มีฝนที่ t ถ้า mask มีฝนที่ p - v*t
    """
    now = now or time.time()
    obs = snap["ts"] - PRODUCT_LAG_MIN * 60          # เวลาจริงของภาพ (โดยประมาณ)
    v = snap.get("motion") or (0.0, 0.0)             # ไม่มี motion = ถือว่าฝนอยู่กับที่ (persistence)
    px, py = rn.latlon_to_ds_px(lat, lon)
    rain, heavy = snap["rain"], snap["heavy"]
    offs = _offsets()
    lead0 = (now - obs) / 60.0                        # ภาพเก่าไปกี่นาทีแล้ว = ต้องฉายไปข้างหน้าเท่านี้ก่อน
    steps = []
    for k in range(LOOKAHEAD_MIN // STEP_MIN + 1):
        lead = lead0 + k * STEP_MIN                    # นาทีนับจากเวลาภาพ
        sx = px - v[0] * lead / STEP_MIN
        sy = py - v[1] * lead / STEP_MIN
        cx, cy = int(round(sx)), int(round(sy))
        cells = [(cx + dx, cy + dy) for dx, dy in offs]
        level = 2 if any(c in heavy for c in cells) else 1 if any(c in rain for c in cells) else 0
        steps.append(level)

    def first(pred, start=0):
        for i in range(start, len(steps)):
            if pred(steps[i]):
                return i
        return None

    at = lambda i: None if i is None else int(now + i * STEP_MIN * 60)
    if not snap.get("motion"):
        # ยังไม่รู้ทิศ (เฟรมอ้างอิงไม่พอ / ฝนไม่มีทิศชัด) -- บอกได้แค่ "ตอนนี้" อย่าเดาเริ่ม/หยุด
        return {"predictable": False, "raining_now": steps[0] > 0, "level_now": steps[0],
                "start_at": None, "start_min": None, "stop_at": None, "stop_min": None,
                "heavy_at": None, "timeline": steps[:1]}
    raining = steps[0] > 0
    start = None if raining else first(lambda lv: lv > 0)
    stop = first(lambda lv: lv == 0) if raining else (first(lambda lv: lv == 0, start) if start is not None else None)
    heavy_i = first(lambda lv: lv == 2)
    return {
        "predictable": True, "raining_now": raining, "level_now": steps[0],
        "start_at": at(start), "start_min": None if start is None else start * STEP_MIN,
        "stop_at": at(stop), "stop_min": None if stop is None else stop * STEP_MIN,
        "heavy_at": at(heavy_i), "timeline": steps,
    }
