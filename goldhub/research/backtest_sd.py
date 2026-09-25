#!/usr/bin/env python3
"""
Backtest mean-reversion fades at SD bands for Gold 0DTE, from pageth/Vol2VolData history.

Spec (agreed 3 Jul 2026):
- Bands per day, anchored at open F0 (first snapshot >= 05:00 Thai):
    flat DTE 0.8125:  +/-1.5, 2, 3 sigma      (sigma = F0 * vol_settle * sqrt(DTE/365))
    flat DTE 0.6:     +/-1.5, 2, 3 sigma
    smile-corrected:  strikes where market-implied tail prob = 2.28% / 0.135% per side
- vol_settle + smile come from the first snapshot AFTER that day's settle refresh;
  bands are active from that snapshot on (no look-ahead).
  New format (Apr 2026+): refresh = Vol Chg reset (<1.5), vol_settle = Vol - Vol Chg.
  Old format (Jan-Mar 2026, no subtitle): refresh = smile curve replacement vs the
  pre-open curve, vol_settle = smile at the ATM strike nearest F0.
- Touch = first snapshot at/beyond a line (first touch per line per day only).
- Headline exit: TP = 25 pts toward mean, SL = 12.5 pts further out, else expiry close.
- Anatomy per touch: MFE/MAE, end-of-day pnl; tags: frozen (05:00-17:00 touch) vs US
  hours, calm vs reprice day (|Vol Chg| > 2.0 after 17:00; new format only).

Usage: python3 backtest_sd.py /path/to/v2v_full [--csv out.csv]
"""

import csv
import datetime
import math
import re
import subprocess
import sys
from collections import defaultdict

GIT = "/usr/bin/git"  # system git is MacPorts 2.15, too old for partial-clone repos

TP, SL = 25.0, 25.0
DTE_FULL, DTE_EXA = 0.8125, 0.6
REPRICE_THRESH = 2.0
Z = {"1.5s": 1.5, "2s": 2.0, "3s": 3.0}
TAIL = {"2s_true": 0.02275, "3s_true": 0.00135}


def N(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def parse_snapshot(blob):
    lines = blob.strip().split("\n")
    if len(lines) < 5:
        return None
    m1 = re.search(r"(\S+) \(([\d.]+) DTE\) vs ([\d.]+) \((-?\+?[\d.-]+)\)", lines[0])
    if not m1:
        return None
    m2 = re.search(r"Vol:\s*([\d.]+)\s+Vol Chg:\s*(-?[\d.]+)", lines[1])
    smile = {}
    for ln in lines[1:]:
        p = ln.split(",")
        if len(p) == 4:
            try:
                v = float(p[3])
                if 0.01 < v < 3.0:
                    smile[float(p[0])] = v
            except ValueError:
                pass
    if len(smile) < 10:
        return None
    return dict(ser=m1.group(1), dte=float(m1.group(2)), F=float(m1.group(3)),
                V=float(m2.group(1)) if m2 else None,
                VC=float(m2.group(2)) if m2 else None, smile=smile)


def load_snapshots(repo):
    """[(iso_ts, snapshot_dict)] oldest-first; one bulk cat-file --batch call."""
    log = subprocess.run(
        [GIT, "-C", repo, "log", "--reverse", "--format=%H %cI", "--", "IntradayData.txt"],
        capture_output=True, text=True).stdout.strip().split("\n")
    entries = [ln.split(" ", 1) for ln in log if ln]
    reqs = "".join(f"{h}:IntradayData.txt\n" for h, _ in entries).encode()
    raw = subprocess.run([GIT, "-C", repo, "cat-file", "--batch"],
                         input=reqs, capture_output=True).stdout
    out, i = [], 0
    for h, ts in entries:
        j = raw.index(b"\n", i)
        hdr = raw[i:j].decode()
        i = j + 1
        if hdr.endswith(" missing") or " blob " not in hdr:
            continue
        size = int(hdr.split()[2])
        blob = raw[i:i + size].decode(errors="replace")
        i += size + 1
        snap = parse_snapshot(blob)
        if snap:
            out.append((ts, snap))
    return out


def vol_at(smile_sorted, k):
    ks, vs = smile_sorted
    if k <= ks[0]:
        return vs[0]
    if k >= ks[-1]:
        return vs[-1]
    for i in range(len(ks) - 1):
        if ks[i] <= k <= ks[i + 1]:
            w = (k - ks[i]) / (ks[i + 1] - ks[i])
            return vs[i] + (vs[i + 1] - vs[i]) * w
    return vs[-1]


def smile_replaced(a, b):
    """True when >half of the overlapping strikes changed value (settle refresh)."""
    common = set(a) & set(b)
    if len(common) < 10:
        return True
    diff = sum(1 for k in common if abs(a[k] - b[k]) > 1e-9)
    return diff > len(common) / 2


def tail_prob(F0, T, smile_sorted, K, side):
    s = vol_at(smile_sorted, K)
    st = s * math.sqrt(T)
    d2 = (math.log(F0 / K) - 0.5 * st * st) / st
    return N(-d2) if side == "dn" else N(d2)


def solve_tail(F0, T, smile_sorted, p_target, side, sd):
    lo, hi = (F0 - 8 * sd, F0) if side == "dn" else (F0, F0 + 8 * sd)
    for _ in range(100):
        m = (lo + hi) / 2
        t = tail_prob(F0, T, smile_sorted, m, side)
        if side == "dn":
            lo, hi = (lo, m) if t >= p_target else (m, hi)
        else:
            lo, hi = (m, hi) if t >= p_target else (lo, m)
    return (lo + hi) / 2


def trading_day(ts):
    """Session day key: snapshots 00:00-04:59 belong to the previous calendar day."""
    d, hm = ts[:10], ts[11:16]
    if hm < "05:00":
        return (datetime.date.fromisoformat(d) - datetime.timedelta(days=1)).isoformat()
    return d


def run(repo, csv_path):
    snaps = load_snapshots(repo)
    print(f"snapshots parsed: {len(snaps)}  ({snaps[0][0][:10]} -> {snaps[-1][0][:10]})")

    days = defaultdict(list)
    for ts, s in snaps:
        days[trading_day(ts)].append((ts, s))

    touches, skipped = [], defaultdict(int)
    for day in sorted(days):
        recs = days[day]
        pre = [(ts, s) for ts, s in recs if ts[:10] == day and ts[11:16] < "05:00"]
        sess = [(ts, s) for ts, s in recs if ts[:10] == day and ts[11:16] >= "05:00"]
        sess += [(ts, s) for ts, s in recs if ts[:10] != day]
        if len(sess) < 20:
            skipped["few snapshots"] += 1
            continue
        F0 = sess[0][1]["F"]
        ser0 = sess[0][1]["ser"]
        if sess[0][1]["dte"] > 1.05:
            skipped["not 0DTE (holiday/weekend)"] += 1
            continue

        has_vc = sess[0][1]["VC"] is not None
        ref_i = None
        if has_vc:
            for i, (ts, s) in enumerate(sess):
                if abs(s["VC"]) < 1.5 and s["ser"] == ser0:
                    ref_i = i
                    break
        else:
            base = pre[-1][1]["smile"] if pre else None
            if base is None:
                ref_i = 0  # no pre-open reference: assume already refreshed at open
            else:
                for i, (ts, s) in enumerate(sess):
                    if smile_replaced(base, s["smile"]):
                        ref_i = i
                        break
        if ref_i is None:
            skipped["no refresh detected"] += 1
            continue
        ref = sess[ref_i][1]
        smile_sorted = (sorted(ref["smile"]), [ref["smile"][k] for k in sorted(ref["smile"])])
        if has_vc:
            vol_settle = (ref["V"] - ref["VC"]) / 100.0
        else:
            atm_strike = min(smile_sorted[0], key=lambda k: abs(k - F0))
            vol_settle = ref["smile"][atm_strike]
        if not 0.05 < vol_settle < 2.0:
            skipped["bad vol"] += 1
            continue

        if has_vc:
            # early-US window only: after ~19:30 the into-expiry vol crush inflates
            # |Vol Chg| on perfectly normal days, poisoning the tag
            evening = [s for ts, s in sess
                       if ts[:10] == day and "17:00" <= ts[11:16] <= "19:30"]
            reprice = any(abs(s["VC"]) > REPRICE_THRESH for s in evening) if evening else None
        else:
            reprice = None

        lines = {}
        for name, dte in [("full", DTE_FULL), ("exA", DTE_EXA)]:
            sd = F0 * vol_settle * math.sqrt(dte / 365)
            for zname, z in Z.items():
                lines[f"{name}_{zname}_dn"] = F0 - z * sd
                lines[f"{name}_{zname}_up"] = F0 + z * sd
        sd_full = F0 * vol_settle * math.sqrt(DTE_FULL / 365)
        T = DTE_FULL / 365
        for tname, p in TAIL.items():
            lines[f"smile_{tname}_dn"] = solve_tail(F0, T, smile_sorted, p, "dn", sd_full)
            lines[f"smile_{tname}_up"] = solve_tail(F0, T, smile_sorted, p, "up", sd_full)

        active = sess[ref_i:]
        for lname, level in lines.items():
            side = "dn" if lname.endswith("_dn") else "up"
            hit_i = None
            for i, (ts, s) in enumerate(active):
                if (side == "dn" and s["F"] <= level) or (side == "up" and s["F"] >= level):
                    hit_i = i
                    break
            if hit_i is None:
                continue
            hit_ts, hit = active[hit_i]
            entry = hit["F"]
            sign = 1.0 if side == "dn" else -1.0  # long at dn lines, short at up
            pnl_path = [sign * (s["F"] - entry) for ts, s in active[hit_i:]]
            outcome, exit_pnl = "eod", pnl_path[-1]
            for p in pnl_path:
                if p <= -SL:
                    outcome, exit_pnl = "sl", -SL
                    break
                if p >= TP:
                    outcome, exit_pnl = "tp", TP
                    break
            frozen = hit_ts[:10] == day and "05:00" <= hit_ts[11:16] < "17:00"
            touches.append(dict(
                day=day, line=lname, side=side, level=round(level, 1),
                entry=entry, time=hit_ts[11:16], frozen=int(frozen),
                reprice=("" if reprice is None else int(reprice)),
                outcome=outcome, pnl=round(exit_pnl, 1),
                mfe=round(max(pnl_path), 1), mae=round(-min(pnl_path), 1),
                eod=round(pnl_path[-1], 1),
                overshoot=round(abs(entry - level), 1),
            ))

    used = len(days) - sum(skipped.values())
    print(f"days used: {used}   skipped: {dict(skipped)}")
    if touches and csv_path:
        with open(csv_path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(touches[0].keys()))
            w.writeheader()
            w.writerows(touches)
        print(f"touch log -> {csv_path}")

    def summarize(rows, label):
        if not rows:
            print(f"{label:36s}  -")
            return
        n = len(rows)
        wins = sum(1 for r in rows if r["outcome"] == "tp")
        sls = sum(1 for r in rows if r["outcome"] == "sl")
        exp = sum(r["pnl"] for r in rows) / n
        med_mae = sorted(r["mae"] for r in rows)[n // 2]
        print(f"{label:36s} n={n:4d}  TP {wins/n*100:4.0f}%  SL {sls/n*100:4.0f}%  "
              f"exp {exp:+6.2f}$/trade  medMAE {med_mae:5.1f}")

    print("\n=== headline: TP+25 / SL-12.5, first touch per line per day ===")
    for lname in sorted(set(t["line"] for t in touches)):
        summarize([t for t in touches if t["line"] == lname], lname)

    print("\n=== 2-sigma-class lines, split by condition ===")
    twos = [t for t in touches if "2s" in t["line"]]
    for cond, fn in [("touch in frozen hours", lambda t: t["frozen"]),
                     ("touch in US hours", lambda t: not t["frozen"]),
                     ("calm day", lambda t: t["reprice"] == 0),
                     ("reprice day", lambda t: t["reprice"] == 1),
                     ("put side (long fade)", lambda t: t["side"] == "dn"),
                     ("call side (short fade)", lambda t: t["side"] == "up")]:
        summarize([t for t in twos if fn(t)], f"2s | {cond}")


if __name__ == "__main__":
    repo = sys.argv[1]
    csv_out = sys.argv[3] if len(sys.argv) > 3 and sys.argv[2] == "--csv" else "backtest_touches.csv"
    run(repo, csv_out)
