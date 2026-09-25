#!/usr/bin/env python3
"""Build the V2V Expected Range data table (per strike) + ranges + summary from v2v_payload.json."""
import json, csv, re
from pathlib import Path

s = json.loads(Path("v2v_payload.json").read_text())

def pts(key):
    return {round(p["x"], 6): p["y"] for p in s.get(key, {}).get("data", [])}

call, put, vol, volset = pts("Call"), pts("Put"), pts("Vol"), pts("VolSettle")
strikes = sorted(set(call) | set(put) | set(vol) | set(volset))

rows = []
for k in strikes:
    rows.append({
        "Strike": k,
        "Call_" + s["ValueName"].replace(" ", ""): call.get(k, ""),
        "Put_" + s["ValueName"].replace(" ", ""): put.get(k, ""),
        "Vol": vol.get(k, ""),
        "VolSettle": volset.get(k, ""),
    })

cols = list(rows[0].keys())
with open("v2v_table.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=cols)
    w.writeheader(); w.writerows(rows)

# Expected-range bands
ranges = []
for r in s.get("Ranges", {}).get("data", []):
    ranges.append({
        "Range": r.get("Tag", {}).get("Range"),
        "Low": round(r["x"], 4),
        "High": round(r.get("x2", r["x"]), 4),
        "Width%": (r.get("dataLabels") or {}).get("format"),
    })
with open("v2v_ranges.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["Range", "Low", "High", "Width%"])
    w.writeheader(); w.writerows(ranges)

# ---- pretty print ----
clean = re.sub("<[^>]+>", "", s.get("Subtitle", "")).replace("\xa0", " ")
print(f"# {s.get('Title')}")
print(f"Future Price : {s.get('FuturePrice')}")
print(f"ATM Vol      : {s.get('ATMVol',0)*100:.2f}%")
print(f"DTE          : {s.get('DTE'):.4f} (fraction of a day -> 0DTE)")
print(f"Summary      : {clean}")
print(f"\nValueName (current tab): {s['ValueName']}\n")

w_s = max(len(str(r['Strike'])) for r in rows)
hdr = f"{'Strike':>{w_s}} | {'Call':>8} | {'Put':>8} | {'Vol%':>8} | {'VolSettle%':>10}"
print(hdr); print("-" * len(hdr))
for r in rows:
    c = list(r.values())
    vpct = f"{c[3]*100:.2f}" if c[3] != "" else ""
    vspct = f"{c[4]*100:.2f}" if c[4] != "" else ""
    print(f"{c[0]:>{w_s}} | {c[1]:>8} | {c[2]:>8} | {vpct:>8} | {vspct:>10}")

print(f"\nExpected Range bands:")
print(f"{'Range':>5} | {'Low':>10} | {'High':>10} | {'Width%':>8}")
for r in ranges:
    print(f"{str(r['Range']):>5} | {r['Low']:>10} | {r['High']:>10} | {str(r['Width%']):>8}")

print(f"\nSaved: v2v_table.csv ({len(rows)} strikes), v2v_ranges.csv ({len(ranges)} bands)")
