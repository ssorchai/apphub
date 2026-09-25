#!/usr/bin/env python3
"""Extract the embedded V2V chart JSON from a captured QuikStrikeView.aspx file."""
import json, re, sys
from pathlib import Path

marker = "UserControlsV2.QuikOptionsV2V.Chart, "

if len(sys.argv) > 1:
    src = Path(sys.argv[1])
    html = src.read_text(encoding="utf-8", errors="replace")
else:
    # Auto-pick: newest captured file that actually contains the chart payload.
    cands = sorted(Path("captures").glob("*QuikStrikeView*.txt"),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    src, html = None, None
    for p in cands:
        t = p.read_text(encoding="utf-8", errors="replace")
        if marker in t:
            src, html = p, t
            break
    if src is None:
        sys.exit("No captured QuikStrikeView file with chart payload found")
    print(f"Using: {src.name}\n")

# Find the $create(...Chart, { ... }) call and grab the object literal via brace matching.
i = html.find(marker)
if i < 0:
    sys.exit("Chart create() not found")
start = html.index("{", i)
depth, in_str, esc, j = 0, False, False, start
while j < len(html):
    c = html[j]
    if in_str:
        if esc: esc = False
        elif c == "\\": esc = True
        elif c == '"': in_str = False
    else:
        if c == '"': in_str = True
        elif c == "{": depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                break
    j += 1
obj_literal = html[start:j+1]
outer = json.loads(obj_literal)              # has "JSONSettings": "<escaped json string>"
settings = json.loads(outer["JSONSettings"])  # the real payload

print("Top-level keys:", list(settings.keys()))
for k, v in settings.items():
    if isinstance(v, dict) and "data" in v:
        print(f"\nSeries '{k}': name={v.get('name')!r}, points={len(v['data'])}")
        if v["data"]:
            print("  sample point:", json.dumps(v["data"][0]))
    elif isinstance(v, list):
        print(f"\n{k}: list len={len(v)}; sample={json.dumps(v[:1])}")
    else:
        print(f"{k!r}: {json.dumps(v)[:200]}")

# Dump full parsed payload for inspection
Path("v2v_payload.json").write_text(json.dumps(settings, indent=2), encoding="utf-8")
print("\nFull payload written to v2v_payload.json")
