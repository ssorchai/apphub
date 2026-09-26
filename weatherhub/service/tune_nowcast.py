"""ตรวจ parameter ของ nowcast รายจุดกับข้อมูลที่ verify.py เก็บไว้ -- แค่รายงาน ไม่แก้ค่าในโค้ดเอง

    cd weatherhub/service && python3 tune_nowcast.py [--days 30] [--places-only] [--base-only] [--top 10]

ใช้ features ที่แนบกับผลทาย (level ดิบจาก advection + สัดส่วนฝนรอบๆ + ความชัน ทุกช่อง 5 นาที)
คิดผลทายใหม่ได้ทุกค่าโดยไม่ต้องเปิดภาพ:
    ฝนที่ช่อง k ถูกตัดทิ้ง  <=>  f_k + alpha * s_k * lead_k < F_DRY
  - F_DRY  : เกณฑ์สัดส่วนฝนรอบๆ ที่ถือว่าสลายแล้ว (ตอนนี้ pn.F_DRY)
  - alpha  : น้ำหนักของความชัน (1 = แบบที่ใช้อยู่, < 1 = เชื่อแนวโน้มน้อยลง)
  - trend  : ชุดรัศมี/ช่วงย้อนหลังที่ใช้หาแนวโน้ม (r10w30 = 10 กม. 30 นาที = ชุดที่ใช้อยู่)
ที่ปรับจากข้อมูลนี้ไม่ได้: รัศมีจุด 2 กม. และ motion (ต้องมีภาพ -- เฟรมเก็บแค่ 2 ชม.)

คะแนน = ความแม่น (ฝน/ไม่ฝน) เฉลี่ย 3 ช่วงทาย (≤10, 15–30, 35–60 นาที) ให้น้ำหนักเท่ากัน
กันตัวเลขสวยเกินจริง (เลือกค่าจากข้อมูลชุดเดียวกับที่วัด): ถ้ามีวันฝนตก >= 2 วัน ทำ
leave-one-day-out -- เลือกค่าจากวันอื่น แล้ววัดกับวันที่เว้นไว้ เทียบกับค่าปัจจุบันบนวันเดียวกัน
"""
import argparse
import bisect
import glob
import json
import os
import sys
import time
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

import point_nowcast as pn  # noqa: E402
import verify  # noqa: E402
from common.hub import Store  # noqa: E402

F_GRID = [round(i * 0.02, 2) for i in range(0, 26)]      # 0.00 .. 0.50
ALPHAS = [0.5, 0.75, 1.0, 1.5]
BUCKETS = ["{}-{}".format(a, b) for a, b in verify.LEAD_BUCKETS]
VARIANT_NAMES = [pn.trend_name(r, w) for r, w in pn.TREND_VARIANTS]
MIN_RAIN_DAYS = 5              # ต่ำกว่านี้ = ผลยังเชื่อไม่ได้ (เตือน)


def _read(store, stream, since):
    for path in sorted(glob.glob(os.path.join(store.path("history", stream), "*.jsonl"))):
        if os.stat(path).st_mtime < since:
            continue
        with open(path) as f:
            for line in f:
                try:
                    yield json.loads(line)
                except ValueError:
                    pass


def _bucket(lead):
    return next((b for b, (a, z) in zip(BUCKETS, verify.LEAD_BUCKETS) if a <= lead <= z), None)


def _day(ts):
    return time.strftime("%Y-%m-%d", time.localtime(ts))


class Acc:
    """นับ confusion ต่อช่วงทาย: ช่องที่ผลไม่ขึ้นกับ F นับตรงๆ ช่องที่ขึ้นกับ F เก็บค่า g ไว้ bisect"""

    def __init__(self):
        self.fixed = {b: [0, 0, 0, 0] for b in BUCKETS}          # tp fp fn tn
        self.g = {b: ([], []) for b in BUCKETS}                  # (g ของช่องที่ฝนตกจริง, ช่องที่ไม่ตก)
        self.ready = False

    def add_fixed(self, b, pred, act):
        self.fixed[b][0 if pred and act else 1 if pred else 2 if act else 3] += 1

    def add_g(self, b, g, act):
        self.g[b][0 if act else 1].append(g)
        self.ready = False

    def merge(self, other):
        for b in BUCKETS:
            for i in range(4):
                self.fixed[b][i] += other.fixed[b][i]
            self.g[b][0].extend(other.g[b][0])
            self.g[b][1].extend(other.g[b][1])
        self.ready = False
        return self

    def counts(self, F):
        if not self.ready:
            for b in BUCKETS:
                self.g[b][0].sort()
                self.g[b][1].sort()
            self.ready = True
        out = {}
        for b in BUCKETS:
            tp, fp, fn, tn = self.fixed[b]
            gr, gd = self.g[b]
            kr, kd = bisect.bisect_left(gr, F), bisect.bisect_left(gd, F)   # g < F = ตัดทิ้ง (ทายแห้ง)
            out[b] = (tp + len(gr) - kr, fp + len(gd) - kd, fn + kr, tn + kd)
        return out


def score(counts):
    accs = [(tp + tn) / n for tp, fp, fn, tn in counts.values() for n in [tp + fp + fn + tn] if n]
    return sum(accs) / len(accs) if len(accs) == len(BUCKETS) else None


def load(store, days, places_only, base_only=False):
    since = time.time() - days * 86400
    obs = {}
    for o in _read(store, "observed", since):
        obs[(o["place"], int(round(o["ts"] / verify.FRAME_SEC)))] = (o["ts"], o["level"])

    def actual(place, t):
        hit = obs.get((place, int(round(t / verify.FRAME_SEC))))
        return None if not hit or abs(hit[0] - t) > verify.MATCH_TOL else hit[1]

    # acc[day][config] ; config = ("trend", name, alpha) | ("advect",) | ("persist",)
    acc = defaultdict(lambda: defaultdict(Acc))
    info = {"records": 0, "skipped_old": 0, "places": set(), "rain_days": set(), "frames": set()}
    for fc in _read(store, "forecast", since):
        feat = fc.get("features")
        if not feat or fc["made"] < since or (places_only and fc["place"] not in verify.PLACES):
            continue
        if fc["model"] not in ("raw", "trend"):
            continue
        if "f" in feat and "var" not in feat and not base_only:
            info["skipped_old"] += 1          # ก่อนมีชุดทางเลือก (26 ก.ย.) เทียบกันไม่ได้ครบทุกชุด
            continue
        now_lv = actual(fc["place"], fc["obs"])
        day = _day(fc["t0"])
        info["records"] += 1
        info["places"].add(fc["place"])
        info["frames"].add(fc["obs"])
        base = fc.get("trend") or pn.trend_name(pn.TREND_RADIUS_KM, pn.TREND_WINDOW_MIN)
        sets = {base: (feat.get("f"), feat.get("s"))}
        if not base_only:
            # แห้งทั้งชั่วโมง (ไม่มี f) = ทุกชุดทายเหมือนกัน ต้องนับให้ทุกชุด ไม่งั้นจำนวนช่องไม่เท่ากัน
            for name in VARIANT_NAMES:
                sets.setdefault(name, (None, None))
            for name, v in (feat.get("var") or {}).items():
                sets[name] = (v["f"], v["s"])
        d = acc[day]
        for k, lv in enumerate(feat["raw"]):
            t = fc["t0"] + k * verify.FRAME_SEC
            act = actual(fc["place"], t)
            b = _bucket(k * pn.STEP_MIN)
            if act is None or b is None:
                continue
            act = act > 0
            if act:
                info["rain_days"].add(day)
            d[("advect",)].add_fixed(b, lv > 0, act)
            if now_lv is not None:
                d[("persist",)].add_fixed(b, now_lv > 0, act)
            lead = feat["lead0"] + k * pn.STEP_MIN
            for name, (fs, ss) in sets.items():
                f = fs[k] if fs else None
                s = ss[k] if ss else None
                for a in ALPHAS:
                    cfg = ("trend", name, a)
                    if lv == 0 or f is None or s is None:
                        d[cfg].add_fixed(b, lv > 0, act)
                    else:
                        d[cfg].add_g(b, f + a * s * lead, act)
    return acc, info


def configs(acc_day):
    """ทุกชุดค่าที่เทียบ: (ชื่อที่แสดง, key ของ Acc, F หรือ None)"""
    out = []
    for key in acc_day:
        if key[0] == "trend":
            out += [(key, F) for F in F_GRID]
        else:
            out.append((key, None))
    return out


def label(key, F):
    if key[0] != "trend":
        return {"advect": "advect (ไม่ตัดด้วยแนวโน้ม)", "persist": "persist (เหมือนตอนนี้)"}[key[0]]
    return "trend {} alpha {:g} F_DRY {:.2f}".format(key[1], key[2], F)


def merged(acc, days):
    out = defaultdict(Acc)
    for day in days:
        for key, a in acc[day].items():
            out[key].merge(a)
    return out


def fmt(counts):
    cells = []
    for b in BUCKETS:
        tp, fp, fn, tn = counts[b]
        n = tp + fp + fn + tn
        csi = tp / (tp + fp + fn) if tp + fp + fn else None
        cells.append("{:>5} {:>5} {:>6}".format("{:.0%}".format((tp + tn) / n) if n else "-",
                                                 "{:.2f}".format(csi) if csi is not None else "-", n))
    return " | ".join(cells)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--places-only", action="store_true", help="ใช้แค่ 4 สถานที่ (ไม่รวมกริด)")
    ap.add_argument("--base-only", action="store_true",
                    help="จูนแค่ F_DRY/alpha ของชุดที่ใช้อยู่ -- รวมผลทายรุ่นเก่าที่ไม่มีชุดทางเลือกด้วย")
    ap.add_argument("--top", type=int, default=10)
    args = ap.parse_args()

    store = Store("weatherhub")
    acc, info = load(store, args.days, args.places_only, args.base_only)
    days = sorted(acc)
    if not days:
        print("ยังไม่มีข้อมูลที่มี features -- รอให้งาน radar เก็บก่อน")
        return
    current = (("trend", pn.trend_name(pn.TREND_RADIUS_KM, pn.TREND_WINDOW_MIN), 1.0), pn.F_DRY)
    print("ข้อมูล: {} วัน ({} ถึง {}) · วันที่มีฝน {} · {} ภาพ · {} จุด · {} ผลทาย".format(
        len(days), days[0], days[-1], len(info["rain_days"]), len(info["frames"]),
        len(info["places"]), info["records"]))
    if info["skipped_old"]:
        print("  ข้ามผลทายรุ่นเก่าที่ไม่มีชุดทางเลือก {} รายการ (--base-only เพื่อรวม)".format(info["skipped_old"]))
    if len(info["rain_days"]) < MIN_RAIN_DAYS:
        print("⚠️  วันที่มีฝนยังไม่ถึง {} วัน -- ผลข้างล่างยังเชื่อไม่ได้ อย่าเพิ่งเปลี่ยนค่า".format(MIN_RAIN_DAYS))

    # ---- ทั้งชุด (in-sample) ----
    allacc = merged(acc, days)
    rows = []
    for key, F in configs(allacc):
        c = allacc[key].counts(F if F is not None else 0)
        sc = score(c)
        if sc is not None:
            rows.append((sc, key, F, c))
    rows.sort(key=lambda r: -r[0])
    head = " | ".join("{:^18}".format("≤{} นาที".format(b.split("-")[1]) if b.startswith("0") else b + " นาที")
                      for b in BUCKETS)
    print("\nคะแนน = ความแม่นเฉลี่ย 3 ช่วง · แต่ละช่วง: ความแม่น / CSI / จำนวนช่อง (ข้อมูลทั้งหมด -- in-sample)")
    print("{:>6}  {:<36} {}".format("คะแนน", "ชุดค่า", head))
    show = rows[:args.top]
    for extra in [current, (("advect",), None), (("persist",), None)]:
        if not any(r[1] == extra[0] and r[2] == extra[1] for r in show):
            show += [r for r in rows if r[1] == extra[0] and r[2] == extra[1]]
    for sc, key, F, c in show:
        mark = " ← ใช้อยู่" if (key, F) == current else ""
        print("{:>6.1%}  {:<36} {}{}".format(sc, label(key, F), fmt(c), mark))

    # ---- leave-one-day-out ----
    rain_days = sorted(info["rain_days"])
    if len(rain_days) < 2:
        print("\nleave-one-day-out: ต้องมีวันที่ฝนตกอย่างน้อย 2 วัน (ตอนนี้ {}) -- ข้าม".format(len(rain_days)))
        return
    print("\nleave-one-day-out (เลือกค่าจากวันอื่น วัดกับวันที่เว้นไว้ -- ตัวเลขนี้คือที่ควรเชื่อ)")
    gain, picks = [], defaultdict(int)
    for held in rain_days:
        train = merged(acc, [d for d in days if d != held])
        best = max(((score(train[k].counts(F if F is not None else 0)), k, F) for k, F in configs(train)
                    if k[0] == "trend"), key=lambda r: r[0] if r[0] is not None else -1)
        test = acc[held]
        s_best = score(test[best[1]].counts(best[2]))
        s_cur = score(test[current[0]].counts(current[1])) if current[0] in test else None
        picks[(best[1], best[2])] += 1
        if s_best is not None and s_cur is not None:
            gain.append(s_best - s_cur)
        print("  {}  เลือก {:<34} ได้ {}  ค่าปัจจุบันได้ {}".format(
            held, label(best[1], best[2]),
            "{:.1%}".format(s_best) if s_best is not None else "-",
            "{:.1%}".format(s_cur) if s_cur is not None else "-"))
    if gain:
        avg = sum(gain) / len(gain)
        (k, F), n = max(picks.items(), key=lambda kv: kv[1])
        print("\nเฉลี่ยดีกว่าค่าปัจจุบัน {:+.1f} จุด% ({} จาก {} วันดีขึ้น)".format(
            avg * 100, sum(g > 0 for g in gain), len(gain)))
        print("ค่าที่ถูกเลือกบ่อยสุด: {} ({}/{} วัน)".format(label(k, F), n, len(rain_days)))
        if len(rain_days) < MIN_RAIN_DAYS:
            print("→ ข้อมูลยังน้อย (วันฝนตก {}/{}) -- ดูไว้ก่อน อย่าเพิ่งเปลี่ยน".format(len(rain_days), MIN_RAIN_DAYS))
        elif avg <= 0.005:
            print("→ ยังไม่คุ้มเปลี่ยน")
        else:
            print("→ ข้อเสนอ: ลองเปลี่ยนเป็นค่าข้างบน (แก้ใน point_nowcast.py เอง -- สคริปต์นี้ไม่แก้ให้)")


if __name__ == "__main__":
    main()
