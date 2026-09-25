"""nowcast รายจุด: ฝนจะเริ่มตก / หยุดตกกี่โมง ที่พิกัดไหนก็ได้ -- คิดจากเฟรมที่เก็บไว้ (frames.py)

ต่างจาก rain_nowcast.py (ตัวแจ้งเตือน 16:xx ใช้ loop GIF ของ กทม. + รัศมี 10 กม.):
  - ใช้ภาพนิ่งที่งาน radar ดึงอยู่แล้ว -> คิดได้ทุก 5 นาทีโดยไม่ยิงต้นทางเพิ่ม
  - ถามที่ "จุด" (รัศมี POINT_RADIUS_KM) ไม่ใช่ "มีฝนในรัศมี 10 กม." -- บอกได้ทั้งเริ่มและหยุด
  - หา motion เฉพาะหน้าต่างรอบพื้นที่ที่สนใจ (MOTION_WINDOW_KM) ไม่ใช่ทั้งภาพ 240 กม.
    ฝนคนละฟากของเรดาร์มักเคลื่อนคนละทาง ใช้ vector เดียวทั้งภาพจะเพี้ยน
  - advection + **แนวโน้มสลายตัว** (เพิ่ม 25 ก.ย.): ตัวเดิมเป็น advection ล้วน วันแรกที่ใช้
    ฝนชั้นกว้างรอบ Home แทบไม่ขยับแต่บางลงเรื่อยๆ (สัดส่วนฝนในรัศมี 10 กม. 0.61 -> 0.34 ใน 15 นาที)
    โมเดลทาย "ตกทั้งชั่วโมง" แต่หยุดจริง 16:00 -- ตอนนี้ตามกลุ่มฝนย้อนหลัง 30 นาที (Lagrangian)
    วัดสัดส่วนฝนรอบๆ ลากเส้นตรง ถ้าคาดว่าต่ำกว่า F_DRY = ฝนสลายแล้ว
    ยังทายฝนที่ "ก่อตัวใหม่" ไม่ได้ (เริ่มตกทายจากฝนที่เคลื่อนเข้ามาเท่านั้น) ความแม่นลดเร็วหลัง ~30 นาที

เวลา: ts ของเฟรม = เวลาในภาพ (frames.py อ่านด้วย OCR) -- ภาพออกช้ากว่านั้น 5-7 นาที
จึงต้องฉายจากเวลาในภาพไปถึง "ตอนนี้" ก่อน แล้วค่อยนับ 60 นาทีข้างหน้า

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
# ภาพหาย/ต้นทางล่ม: เฟรมล่าสุดเก่ากว่านี้ (นับจากเวลาในภาพ) = ไม่ทาย -- ฉายต่อจากภาพเก่าเรื่อยๆ
# จะดูเหมือนข้อมูลสดทั้งที่ไม่ใช่ (ปกติภาพช้า 5-10 นาที -> 20 นาที = หายไปแล้ว ~2 รอบ)
STALE_MIN = 20
# ตอน BMA ล่มแล้วใช้ภาพจาก TMD: TMD อัปเดตแค่ ~15 นาที + ช้า ~13 นาที -> 20 นาทีเกือบทุกรอบ (25 ก.ย. คืน)
# ยอมให้เก่ากว่านี้ได้ แลกกับช่วงต้นของแถบทายที่เป็นอดีตไปแล้ว
STALE_MIN_TMD = 30


def stale_limit(via):
    """เกณฑ์ภาพเก่า (นาที) ตามต้นทางของภาพล่าสุด -- via จาก weather_meta.json"""
    return STALE_MIN_TMD if via == "TMD" else STALE_MIN
TREND_WINDOW_MIN = 30          # ใช้เฟรมย้อนหลังเท่านี้หาแนวโน้ม
TREND_MIN_SPAN = 10            # ต้องมีข้อมูลห่างกันอย่างน้อยเท่านี้ถึงเชื่อแนวโน้ม
TREND_RADIUS_KM = 10           # วัดสัดส่วนฝนรอบๆ ในรัศมีนี้
F_DRY = 0.22                   # สัดส่วนฝนรอบๆ ต่ำกว่านี้ จุดกลางมักแห้งแล้ว (Home 1/2 หยุดที่ 0.23/0.19
                               # ยังตกที่ 0.24 -- ได้จากเหตุการณ์เดียว 25 ก.ย. ควรปรับเมื่อมีข้อมูลมากขึ้น)
AOI = rn.LOCATIONS["Office"]   # ศูนย์กลางพื้นที่ที่สนใจ (กรุงเทพฯ)


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


def _masks(folder, name, cache):
    if name not in cache:
        cache[name] = rn.rain_points(Image.open(os.path.join(folder, name)).convert("RGB"))
    return cache[name]


def analyze(folder, listing, cache=None):
    """snapshot จากเฟรมใน listing (ล่าสุด = ตัวสุดท้าย) -- แยกออกมาให้ backtest เรียกซ้ำได้"""
    cache = {} if cache is None else cache
    ts, name = listing[-1]
    rain, heavy = _masks(folder, name, cache)
    motion = ref_ts = None
    ref = _pick_ref(listing)
    if ref:
        ref_ts, ref_name = ref
        old, _ = _masks(folder, ref_name, cache)
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
            "rain": _rle(rain), "heavy": _rle(heavy),
            # เฟรมย้อนหลังสำหรับแนวโน้ม (ฝนอย่างเดียว) -- ไม่รวมเฟรมล่าสุด
            "hist": [{"ts": t, "rain": _rle(_masks(folder, n, cache)[0])} for t, n in listing[:-1]
                     if 0 < (ts - t) / 60 <= TREND_WINDOW_MIN]}
    if motion:
        d, spd = rn.describe_motion(motion)
        snap["from_dir"], snap["speed_kmh"] = d, round(spd, 1)
    return snap


def update(folder):
    """วิเคราะห์เฟรมล่าสุดแล้วเขียน snapshot -- คืน dict สรุปสั้นๆ (หรือ None ถ้ายังไม่มีเฟรม)"""
    listing = frames.listing(folder)
    if not listing:
        return None
    snap = analyze(folder, listing)
    tmp = SNAP_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(snap, f, separators=(",", ":"))
    os.replace(tmp, SNAP_PATH)
    return {k: snap.get(k) for k in ("ts", "ref_ts", "rain_px", "heavy_px", "from_dir", "speed_kmh")}


def load_snapshot(txt):
    s = json.loads(txt)
    s["rain"], s["heavy"] = unrle(s["rain"]), unrle(s["heavy"])
    for h in s.get("hist") or []:
        h["rain"] = unrle(h["rain"])
    return s


_DISK = {}


def _disk(r_km):
    if r_km not in _DISK:
        r = r_km / rn.KM_PER_PX / rn.DS
        n = int(math.ceil(r))
        _DISK[r_km] = [(dx, dy) for dx in range(-n, n + 1) for dy in range(-n, n + 1) if dx * dx + dy * dy <= r * r]
    return _DISK[r_km]


def _frac(mask, x, y):
    cx, cy = int(round(x)), int(round(y))
    d = _disk(TREND_RADIUS_KM)
    return sum((cx + dx, cy + dy) in mask for dx, dy in d) / len(d)


def trend(snap, x, y):
    """(สัดส่วนฝนรอบ (x,y) ในภาพล่าสุด, ความชันต่อนาที | None) -- ตามกลุ่มฝนย้อนเวลาด้วย motion"""
    v = snap.get("motion") or (0.0, 0.0)
    obs = snap["ts"]
    f_now = _frac(snap["rain"], x, y)
    pts = [(0.0, f_now)]
    for h in snap.get("hist") or []:
        back = (obs - h["ts"]) / 60.0                  # นาทีก่อนภาพล่าสุด
        pts.append((-back, _frac(h["rain"], x - v[0] * back / STEP_MIN, y - v[1] * back / STEP_MIN)))
    span = max(t for t, _ in pts) - min(t for t, _ in pts)
    if len(pts) < 2 or span < TREND_MIN_SPAN:
        return f_now, None
    mt = sum(t for t, _ in pts) / len(pts)
    mf = sum(f for _, f in pts) / len(pts)
    den = sum((t - mt) ** 2 for t, _ in pts)
    return f_now, sum((t - mt) * (f - mf) for t, f in pts) / den


_OFFSETS = None


def _offsets():
    global _OFFSETS
    if _OFFSETS is None:
        r = POINT_RADIUS_KM / rn.KM_PER_PX / rn.DS
        n = int(math.ceil(r))
        _OFFSETS = [(dx, dy) for dx in range(-n, n + 1) for dy in range(-n, n + 1) if dx * dx + dy * dy <= r * r]
    return _OFFSETS


def forecast(snap, lat, lon, now=None, use_trend=True, stale_min=STALE_MIN, features=False):
    """timeline ของจุดนี้: level ทุก STEP_MIN นาที (0 ไม่มี / 1 ฝน / 2 ฝนหนัก) นับจาก "ตอนนี้"

    ตำแหน่งของฝนที่เวลา t = mask ล่าสุดเลื่อนไป v*t -> จุด p มีฝนที่ t ถ้า mask มีฝนที่ p - v*t
    features=True: แนบค่าดิบทุกช่อง (level ก่อนตัดด้วยแนวโน้ม, สัดส่วนฝนรอบๆ, ความชัน) ให้ verify เก็บไว้
    จูน F_DRY/รัศมีย้อนหลังได้โดยไม่ต้องมีภาพ -- ช่องที่ advection แห้งอยู่แล้วไม่คิดแนวโน้ม (None)
    """
    now = now or time.time()
    obs = snap["ts"]                                  # เวลาในภาพ
    v = snap.get("motion") or (0.0, 0.0)             # ไม่มี motion = ถือว่าฝนอยู่กับที่ (persistence)
    px, py = rn.latlon_to_ds_px(lat, lon)
    rain, heavy = snap["rain"], snap["heavy"]
    offs = _offsets()
    lead0 = (now - obs) / 60.0                        # ภาพเก่าไปกี่นาทีแล้ว = ต้องฉายไปข้างหน้าเท่านี้ก่อน
    steps = []
    raw, fs, ss = [], [], []
    trend_info = None
    for k in range(LOOKAHEAD_MIN // STEP_MIN + 1):
        lead = lead0 + k * STEP_MIN                    # นาทีนับจากเวลาภาพ
        sx = px - v[0] * lead / STEP_MIN
        sy = py - v[1] * lead / STEP_MIN
        cx, cy = int(round(sx)), int(round(sy))
        cells = [(cx + dx, cy + dy) for dx, dy in offs]
        level = 2 if any(c in heavy for c in cells) else 1 if any(c in rain for c in cells) else 0
        raw.append(level)
        f_now = slope = None
        if level and use_trend:
            # กลุ่มฝนที่จะมาถึงจุดนี้ตอน lead: ตอนนี้อยู่ที่ (sx, sy) -- ถ้าแนวโน้มบอกว่าสลายแล้ว = แห้ง
            f_now, slope = trend(snap, sx, sy)
            if slope is not None:
                if k == 0:
                    trend_info = {"frac_now": round(f_now, 2), "per_10min": round(slope * 10, 3)}
                if f_now + slope * lead < F_DRY:
                    level = 0
        fs.append(None if f_now is None else round(f_now, 4))
        ss.append(None if slope is None else round(slope, 5))
        steps.append(level)

    def first(pred, start=0):
        for i in range(start, len(steps)):
            if pred(steps[i]):
                return i
        return None

    at = lambda i: None if i is None else int(now + i * STEP_MIN * 60)
    if lead0 > stale_min:
        return {"predictable": False, "reason": "stale", "age_min": int(lead0), "t0": int(now),
                "raining_now": None, "level_now": None, "start_at": None, "start_min": None,
                "stop_at": None, "stop_min": None, "heavy_at": None, "timeline": []}
    if not snap.get("motion"):
        # ยังไม่รู้ทิศ (เฟรมอ้างอิงไม่พอ / ฝนไม่มีทิศชัด) -- บอกได้แค่ "ตอนนี้" อย่าเดาเริ่ม/หยุด
        return {"predictable": False, "reason": "no_motion", "t0": int(now), "raining_now": steps[0] > 0, "level_now": steps[0],
                "start_at": None, "start_min": None, "stop_at": None, "stop_min": None,
                "heavy_at": None, "timeline": steps[:1]}
    raining = steps[0] > 0
    start = None if raining else first(lambda lv: lv > 0)
    stop = first(lambda lv: lv == 0) if raining else (first(lambda lv: lv == 0, start) if start is not None else None)
    heavy_i = first(lambda lv: lv == 2)
    out = {
        "predictable": True, "t0": int(now), "raining_now": raining, "level_now": steps[0],
        "start_at": at(start), "start_min": None if start is None else start * STEP_MIN,
        "stop_at": at(stop), "stop_min": None if stop is None else stop * STEP_MIN,
        "heavy_at": at(heavy_i), "timeline": steps, "trend": trend_info,
    }
    if features:
        out["features"] = {"lead0": round(lead0, 2), "raw": raw}
        if any(f is not None for f in fs):         # แห้งทั้งชั่วโมง = ไม่ต้องเก็บ (ประหยัดที่)
            out["features"].update(f=fs, s=ss)
    return out
