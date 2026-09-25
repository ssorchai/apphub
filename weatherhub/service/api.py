"""API ของ weatherhub (พอร์ต 8788) — อ่านจากไฟล์ที่งาน radar/nowcast เขียนไว้แล้วเท่านั้น

พิกัดมาจากอุปกรณ์ที่เรียก (location service ของ Mac/มือถือ): `/api/state?lat=&lon=`
  - ปัดเป็นกริด GRID องศา (~5 กม.) ก่อนทำอะไรทั้งนั้น ตอบกลับเป็นค่าที่ปัดแล้ว และไม่ log พิกัด
  - ไม่ส่งมา = ใช้ `weather.default` ใน config.json ([lat, lon]) ถ้าไม่ตั้ง = Office
  - ค่ารายจุดคิดจากเรดาร์ที่มีอยู่แล้วล้วนๆ (ผู้ใช้เลือก 25 ก.ย. 26 ไม่เพิ่มแหล่งใหม่
    และไม่เพิ่มรอบโหลด loop GIF): ตำแหน่งบนภาพ, ระยะ/ทิศจากสถานี และ ETA ฝนหนัก
    จากรอบเช็ค nowcast ล่าสุด (16:00-16:45 เท่านั้น -- ดู `nowcast.age` ก่อนเชื่อ)
  - นอกวงเรดาร์ (> RADAR_RANGE_KM จากหนองจอก) = ไม่มีค่าเรดาร์ของจุดนั้น

schema_version: เพิ่ม field ได้โดยไม่ต้องขยับ / เปลี่ยนความหมายหรือลบ field = ขยับเลข
"""
import base64
import json
import math
import os
import threading
import time

import frames
import point_nowcast as pn
import verify
import rain_nowcast as rn
import weather_fetcher
from common.hub import JSON, TEXT, Api, FileCache, Store, WebWidget, config, json_body

SCHEMA_VERSION = 1
PORT = 8788
GRID = 0.05                    # องศา -- ช่องละ ~5.5 กม. กันเก็บพิกัดตรงๆ
IMG_W, IMG_H = 965, 800        # ภาพเรดาร์ BMA (ภาพนิ่งกับ loop เรขาคณิตเดียวกัน)
RADAR_RANGE_KM = 120.0         # วงนอกสุดของภาพ
DEFAULT_LATLON = rn.LOCATIONS["Office"]


def _radar(txt):
    m = json.loads(txt)
    m["img"] = base64.b64decode(m.pop("img_base64", "") or b"")
    return m


def _nowcast(txt):
    n = json.loads(txt)
    n["heavy"] = {tuple(p) for p in n.get("heavy") or ()}
    return n


radar = FileCache(weather_fetcher.JSON_PATH, _radar)

# หน้าเว็บ /dashboard = widget ไฟล์เดียวกับการ์ดบน desktop (ดู common/hub/webwidget.py)
_HUB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
dash = WebWidget(os.path.join(_HUB, "widgets", "radar-weather.jsx"),
                 os.path.join(_HUB, "web", "dist", "radar-weather.js"),
                 os.path.join(_HUB, "web", "dashboard.html"))
nowcast = FileCache(rn.NOWCAST_PATH, _nowcast)

# ETA ต่อช่องกริด: คิดใหม่เฉพาะตอน snapshot ของ nowcast เปลี่ยน
_eta_cache = {}
_eta_lock = threading.Lock()


def snap(v):
    return round(round(v / GRID) * GRID, 4)


def parse_point(query, default):
    """คืน (lat, lon, is_default) หรือ raise ValueError ถ้าส่งมาไม่ครบ/ผิดรูป"""
    lat, lon = (query.get("lat") or [""])[0], (query.get("lon") or [""])[0]
    if not lat and not lon:
        return snap(default[0]), snap(default[1]), True
    try:
        la, lo = float(lat), float(lon)
    except ValueError:
        raise ValueError("lat/lon ต้องเป็นตัวเลขทั้งคู่")
    if not (-90 <= la <= 90 and -180 <= lo <= 180) or math.isnan(la) or math.isnan(lo):
        raise ValueError("lat/lon อยู่นอกช่วง")
    return snap(la), snap(lo), False


def geometry(lat, lon):
    """ตำแหน่งของจุดเทียบสถานีเรดาร์ + ตำแหน่งบนภาพเป็น % (ใช้วาง marker ได้ตรงๆ)"""
    r_lat, r_lon = rn.RADAR_LATLON
    dn = (lat - r_lat) * 110.9
    de = (lon - r_lon) * 111.32 * math.cos(math.radians(r_lat))
    dist = math.hypot(dn, de)
    x = rn.CENTER_PX[0] + de / rn.KM_PER_PX
    y = rn.CENTER_PX[1] - dn / rn.KM_PER_PX
    covered = dist <= RADAR_RANGE_KM and 0 <= x < IMG_W and 0 <= y < IMG_H
    return {
        "in_coverage": covered,
        "distance_km": round(dist, 1),
        "bearing_deg": round((math.degrees(math.atan2(de, dn)) + 360) % 360),
        "img_pct": {"left": round(x / IMG_W * 100, 2), "top": round(y / IMG_H * 100, 2)} if covered else None,
    }


def point_nowcast(lat, lon, covered):
    n, mtime = nowcast.get()
    if n is None or not covered:           # นอกวงเรดาร์ = ภาพนี้บอกอะไรเกี่ยวกับจุดนั้นไม่ได้
        return None
    out = {"ts": n.get("ts"), "age": _age(n), "radius_km": rn.RADIUS_KM,
           "lookahead_min": rn.LOOKAHEAD_MIN, "from_dir": n.get("from_dir"),
           "speed_kmh": n.get("speed_kmh"), "eta_min": None}
    key = (lat, lon)
    with _eta_lock:
        hit = _eta_cache.get(key)
        if hit is None or hit[0] != mtime:
            if len(_eta_cache) > 512:
                _eta_cache.clear()
            v = tuple(n["motion"]) if n.get("motion") else None
            hit = (mtime, rn.eta_at(n["heavy"], v, lat, lon))
            _eta_cache[key] = hit
    out["eta_min"] = hit[1]        # 0 = ตกในรัศมีแล้ว / None = ไม่ถึงใน lookahead
    return out


def _age(v):
    ts = (v or {}).get("ts")
    return round(time.time() - ts) if isinstance(ts, (int, float)) else None


point_snap = FileCache(pn.SNAP_PATH, pn.load_snapshot)
# /api/forecast ไม่ปัดพิกัด (เดิมปัด 0.01° ~1.1 กม. ทำให้จุด custom บนภาพคลาดได้ ~550 ม. -- ผู้ใช้เห็น 25 ก.ย.)
# จุดที่ส่งมาเป็นสถานที่ประจำ/จุดที่พิมพ์เอง ไม่ใช่ตำแหน่งติดตามตัว และ API ไม่เก็บ/ไม่ log พิกัดอยู่แล้ว
# ตัดทศนิยมที่ 6 หลัก (~0.1 ม.) พอ -- mask ฝนละเอียดแค่ ~0.6 กม./ช่อง
FORECAST_DECIMALS = 6
FORECAST_MAX_POINTS = 8


def r_forecast(query):
    """`?pts=lat,lon;lat,lon` -> ฝนจะเริ่ม/หยุดกี่โมงของแต่ละจุด (ลำดับเดียวกับที่ส่งมา)

    คิดจาก snapshot ที่งาน radar เขียนไว้ ไม่เปิดภาพ/ไม่ยิงต้นทาง / ไม่เก็บและไม่ log พิกัด"""
    raw = ";".join(query.get("pts", [])).split(";")
    pts = []
    for item in raw:
        if not item.strip():
            continue
        try:
            la, lo = (float(v) for v in item.split(","))
        except ValueError:
            return 400, JSON, json_body({"error": "pts = lat,lon;lat,lon"})
        if not (-90 <= la <= 90 and -180 <= lo <= 180):
            return 400, JSON, json_body({"error": "lat/lon อยู่นอกช่วง"})
        pts.append((round(la, FORECAST_DECIMALS), round(lo, FORECAST_DECIMALS)))
    if len(pts) > FORECAST_MAX_POINTS:
        return 400, JSON, json_body({"error": "สูงสุด {} จุด".format(FORECAST_MAX_POINTS)})
    snap, _ = point_snap.get()
    basis = None
    if snap is not None:
        basis = {"ts": snap["ts"], "ref_ts": snap.get("ref_ts"), "age": _age(snap),
                 "observed_at": snap["ts"],
                 "motion": ({"from_dir": snap.get("from_dir"), "speed_kmh": snap.get("speed_kmh")}
                            if snap.get("motion") else None),
                 "step_min": pn.STEP_MIN, "lookahead_min": pn.LOOKAHEAD_MIN,
                 "radius_km": pn.POINT_RADIUS_KM}
    out = []
    for la, lo in pts:
        geo = geometry(la, lo)
        fc = pn.forecast(snap, la, lo) if snap is not None and geo["in_coverage"] else None
        out.append({"lat": la, "lon": lo, "in_coverage": geo["in_coverage"], "img_pct": geo["img_pct"],
                    "forecast": fc})
    return 200, JSON, json_body({"schema_version": SCHEMA_VERSION, "basis": basis, "points": out})


STORE = Store("weatherhub")
FRAME_DIR = STORE.path("frames")


def r_verify(query):
    """ความแม่นของ nowcast รายจุดย้อนหลัง N วัน (verify.py) -- อ่านจาก history อย่างเดียว"""
    try:
        days = max(1, min(30, int((query.get("days") or ["7"])[0])))
    except ValueError:
        return 400, JSON, json_body({"error": "days ต้องเป็นตัวเลข"})
    return 200, JSON, json_body(dict(verify.stats(STORE, days), schema_version=SCHEMA_VERSION))
FRAMES_DEFAULT = 12            # 1 ชั่วโมง เท่า loop GIF ของ กทม.


def r_frames(query):
    """รายการเฟรมย้อนหลัง (เก่า -> ใหม่) ให้หน้าเว็บเล่นเป็นภาพเคลื่อนไหว"""
    try:
        n = max(1, min(frames.MAX_FRAMES, int((query.get("n") or [FRAMES_DEFAULT])[0])))
    except ValueError:
        return 400, JSON, json_body({"error": "n ต้องเป็นตัวเลข"})
    items = frames.listing(FRAME_DIR)[-n:]
    return 200, JSON, json_body({
        "schema_version": SCHEMA_VERSION,
        "frame_minutes": rn.FRAME_MINUTES,
        "frames": [{"ts": ts, "image": "/api/frame?ts={}".format(ts)} for ts, _ in items],
    })


def r_frame(query):
    ts = (query.get("ts") or [""])[0]
    if not ts.isdigit():
        return 400, TEXT, "ts ต้องเป็นตัวเลข\n"
    for t, name in frames.listing(FRAME_DIR):
        if str(t) == ts:
            with open(os.path.join(FRAME_DIR, name), "rb") as f:
                return 200, frames.MIME[name.rsplit(".", 1)[1]], f.read()
    return 404, TEXT, "ไม่มีเฟรมนี้ (เก่าเกิน {} ชม. หรือถูกลบแล้ว)\n".format(frames.KEEP_SEC // 3600)


def build(health):
    cfg = config.load()
    default = tuple((cfg.get("weather") or {}).get("default") or DEFAULT_LATLON)

    def r_state(query):
        try:
            lat, lon, is_default = parse_point(query, default)
        except ValueError as e:
            return 400, JSON, json_body({"error": str(e)})
        m, _ = radar.get()
        geo = geometry(lat, lon)
        radar_obj = None
        if m is not None:
            radar_obj = {k: m.get(k) for k in ("ts", "last_update", "source", "via", "mime")}
            radar_obj["image"] = "/api/radar"
            # เวลาในภาพ (OCR) ของเฟรมล่าสุด -- ภาพที่ /api/radar คือเฟรมนี้ถ้าเก็บทันแล้ว
            fr = frames.listing(FRAME_DIR)
            radar_obj["observed_at"] = fr[-1][0] if fr else None
        return 200, JSON, json_body({
            "schema_version": SCHEMA_VERSION,
            "service": "weatherhub",
            "ts": round(time.time(), 3),
            "age": {"radar": _age(m)},
            "point": dict({"lat": lat, "lon": lon, "default": is_default, "grid_deg": GRID}, **geo),
            "radar": radar_obj,
            "nowcast": point_nowcast(lat, lon, geo["in_coverage"]),
        })

    def r_radar(query):
        m, _ = radar.get()
        if m is None or not m.get("img"):
            return 503, TEXT, "ยังไม่มีภาพเรดาร์ (รอรอบ 5 นาทีแรก)\n"
        return 200, m.get("mime") or "image/png", m["img"]

    api = Api("weatherhub", PORT, token=cfg.get("token"),
              extra_binds=cfg.get("bind"), extra_hosts=cfg.get("hosts"))
    api.route("/api/state", r_state)
    api.route("/api/radar", r_radar)
    api.route("/api/frames", r_frames)
    api.route("/api/forecast", r_forecast)
    api.route("/api/verify", r_verify)
    api.route("/api/frame", r_frame)
    api.route("/api/health", lambda q: (200, JSON, json_body(health.snapshot())))
    dash.mount(api)
    api.route("/", lambda q: (200, JSON, json_body({"service": "weatherhub",
                                                     "schema_version": SCHEMA_VERSION,
                                                     "routes": sorted(api.routes)})))
    return api
