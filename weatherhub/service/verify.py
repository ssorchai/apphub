"""บันทึกผลทาย nowcast รายจุด แล้ววัดความแม่นเทียบกับภาพจริงอัตโนมัติ

ทุกครั้งที่ได้เฟรมใหม่ (เวลาในภาพ T) งาน radar เรียก record():
  - history/observed : ฝนจริงที่ PLACES ตอน T (level 0/1/2 ในรัศมีจุด 2 กม. -- นิยามเดียวกับตัวทาย)
  - history/forecast : ผลทาย 1 ชม. ของ 3 โมเดล เริ่มที่ t0 = เวลาในภาพถัดไปที่ >= ตอนนี้
      trend   = ตัวที่ใช้จริง (advection + แนวโน้มสลายตัว)
      advect  = advection ล้วน (ตัวก่อน 25 ก.ย.) -- ไว้ดูว่าแนวโน้มช่วยจริงไหม
      persist = "เหมือนตอนนี้ไปตลอด" -- เส้นฐาน ถ้าโมเดลไม่ชนะอันนี้แปลว่าไม่มีประโยชน์
    t0 วางบนกริดเวลาภาพ (ทุก 5 นาที) ช่องที่ k จึงตรงกับเฟรมจริงในอนาคตพอดี

stats() จับคู่ช่องทำนายกับ observed ที่เวลาเดียวกัน แยกตามระยะทายล่วงหน้า
ตัดสินแค่ "ฝน / ไม่ฝน" (level > 0) -- ฝนหนักยังไม่วัด
"""
import glob
import json
import math
import os
import threading
import time

import point_nowcast as pn
import rain_nowcast as rn

# ต้องตรงกับ MARKERS ใน widgets/radar-weather.jsx (id เดียวกัน)
PLACES = {
    "office": (13.7733, 100.5426),
    "office2": (13.8062486, 100.5352885),
    "home": (13.8873269, 100.6026284),
    "home2": (13.873365, 100.6494155),
}
FRAME_SEC = 300
MATCH_TOL = 120                 # วินาที -- เฟรม OCR ตรงกริดพอดี เฟรม fallback (เวลาดึง - 6 นาที) คลาดได้
LEAD_BUCKETS = [(0, 10), (15, 30), (35, 60)]   # นาทีนับจาก t0


def _level_at(snap, lat, lon):
    px, py = rn.latlon_to_ds_px(lat, lon)
    cx, cy = int(round(px)), int(round(py))
    cells = [(cx + dx, cy + dy) for dx, dy in pn._offsets()]
    if any(c in snap["heavy"] for c in cells):
        return 2
    return 1 if any(c in snap["rain"] for c in cells) else 0


def record(store, snap, now=None, via=None):
    """บันทึก observed + forecast ของรอบนี้ -- snap = แบบที่ load_snapshot คืน (mask เป็น set)
    via = ต้นทางภาพ (เกณฑ์ภาพเก่าเดียวกับที่หน้าเว็บใช้)"""
    now = now or time.time()
    stale_min = pn.stale_limit(via)
    obs = snap["ts"]
    t0 = obs + FRAME_SEC * max(0, math.ceil((now - obs) / FRAME_SEC))
    n = 0
    for place, (la, lo) in PLACES.items():
        lv = _level_at(snap, la, lo)
        store.append_history("observed", {"ts": obs, "place": place, "level": lv})
        if (now - obs) / 60 > stale_min:
            continue                          # ภาพเก่า ตัวทายจริงก็ไม่ทาย -- ไม่นับ
        steps = pn.LOOKAHEAD_MIN // pn.STEP_MIN + 1
        store.append_history("forecast", {"made": int(now), "obs": obs, "t0": t0, "place": place,
                                          "model": "persist", "timeline": [lv] * steps})
        for model, use_trend in (("trend", True), ("advect", False)):
            fc = pn.forecast(snap, la, lo, now=t0, use_trend=use_trend, stale_min=stale_min)
            if fc.get("predictable"):
                store.append_history("forecast", {"made": int(now), "obs": obs, "t0": t0, "place": place,
                                                  "model": model, "timeline": fc["timeline"]})
                n += 1
    return n


def _read(store, stream, since):
    out = []
    for path in sorted(glob.glob(os.path.join(store.path("history", stream), "*.jsonl"))):
        try:
            if os.stat(path).st_mtime < since:
                continue
            with open(path) as f:
                for line in f:
                    try:
                        out.append(json.loads(line))
                    except ValueError:
                        pass
        except OSError:
            pass
    return out


_cache = {"key": None, "value": None}
_lock = threading.Lock()


def stats(store, days=7):
    """ความแม่นของแต่ละโมเดลแยกตามระยะทาย -- cache ตาม mtime ของไฟล์ history"""
    since = time.time() - days * 86400
    files = glob.glob(store.path("history", "forecast", "*.jsonl")) + \
        glob.glob(store.path("history", "observed", "*.jsonl"))
    key = (days, max((os.stat(p).st_mtime for p in files), default=0))
    with _lock:
        if _cache["key"] == key:
            return _cache["value"]
    obs = {}
    for o in _read(store, "observed", since):
        obs[(o["place"], int(round(o["ts"] / FRAME_SEC)))] = (o["ts"], o["level"])
    res = {}
    first = last = None
    for fc in _read(store, "forecast", since):
        if fc["made"] < since:
            continue
        m = res.setdefault(fc["model"], {"buckets": {"{}-{}".format(a, b): [0, 0, 0, 0] for a, b in LEAD_BUCKETS}})
        for k, lv in enumerate(fc["timeline"]):
            target = fc["t0"] + k * FRAME_SEC
            hit = obs.get((fc["place"], int(round(target / FRAME_SEC))))
            if not hit or abs(hit[0] - target) > MATCH_TOL:
                continue
            lead = k * pn.STEP_MIN
            b = next(("{}-{}".format(a, z) for a, z in LEAD_BUCKETS if a <= lead <= z), None)
            if b is None:
                continue
            p, a = lv > 0, hit[1] > 0
            # [ทายฝน-ฝนจริง, ทายฝน-ไม่ฝน, ทายไม่ฝน-ฝนจริง, ทายไม่ฝน-ไม่ฝน]
            m["buckets"][b][0 if p and a else 1 if p else 2 if a else 3] += 1
            first = fc["made"] if first is None else min(first, fc["made"])
            last = fc["made"] if last is None else max(last, fc["made"])
    for m in res.values():
        for b, (tp, fp, fn, tn) in list(m["buckets"].items()):
            n = tp + fp + fn + tn
            m["buckets"][b] = {
                "n": n,
                "accuracy": round((tp + tn) / n, 3) if n else None,
                "pod": round(tp / (tp + fn), 3) if tp + fn else None,     # ฝนจริงที่ทายถูก
                "far": round(fp / (tp + fp), 3) if tp + fp else None,     # ทายว่าฝนแต่ไม่ตก
                "counts": {"hit": tp, "false_alarm": fp, "miss": fn, "correct_dry": tn},
            }
    value = {"days": days, "from": first, "to": last, "models": res}
    with _lock:
        _cache.update(key=key, value=value)
    return value
