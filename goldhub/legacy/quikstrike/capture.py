#!/usr/bin/env python3
"""
Phase 1: discover the QuikStrike data endpoint for the Vol2Vol Expected Range tool.

Opens a REAL (headful) Chromium window using your own browser profile-style context,
navigates to the CME page, and records every JSON/XHR response coming from the
quikstrike backend while YOU click through the UI manually:

    Product -> Metals -> Gold -> Expire series = today (0DTE)

Each captured response body is saved to ./captures/ and an index is printed so we
can see which call returns the actual data table.

Run:
    python3 capture.py
"""

import json
import re
import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

URL = "https://www.cmegroup.com/tools-information/quikstrike/vol2vol-expected-range.html"
OUT = Path("captures")
OUT.mkdir(exist_ok=True)

# Domains that QuikStrike data flows through. We log anything matching.
INTERESTING = re.compile(r"quikstrike|cmegroup\.com/.*\.(json|ashx|aspx)|/Services/", re.I)

index = []          # summary rows
counter = {"n": 0}


def safe_name(url: str, n: int) -> str:
    tail = re.sub(r"[^A-Za-z0-9._-]", "_", url.split("?")[0])[-60:]
    return f"{n:03d}_{tail}.txt"


def on_response(resp):
    url = resp.url
    if not INTERESTING.search(url):
        return
    ctype = (resp.headers or {}).get("content-type", "")
    # We care about data-ish responses: json, or anything that isn't an image/font/css/js asset
    if any(x in ctype for x in ("image/", "font/", "text/css", "javascript")):
        return
    counter["n"] += 1
    n = counter["n"]
    try:
        body = resp.text()
    except Exception as e:
        body = f"<could not read body: {e}>"

    fname = safe_name(url, n)
    (OUT / fname).write_text(body, encoding="utf-8", errors="replace")

    looks_json = ctype.startswith("application/json") or body[:1] in "{["
    index.append({
        "n": n,
        "status": resp.status,
        "method": resp.request.method,
        "ctype": ctype,
        "bytes": len(body),
        "json": looks_json,
        "file": fname,
        "url": url,
    })
    print(f"[{n:03d}] {resp.request.method} {resp.status} {len(body):>7}B "
          f"json={looks_json!s:5} {url[:100]}")


def main():
    with sync_playwright() as p:
        # Persistent context keeps cookies/storage between runs and looks more like a real user.
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(Path("./.pw-profile").resolve()),
            headless=False,
            viewport={"width": 1500, "height": 950},
            locale="en-US",
            timezone_id="Asia/Bangkok",
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.on("response", on_response)

        print(f"\nNavigating to:\n  {URL}\n")
        page.goto(URL, wait_until="domcontentloaded", timeout=90000)

        print("=" * 80)
        print("Browser is open. Now in the page, MANUALLY do:")
        print("   Product  -> Metals -> Gold")
        print("   Expire series -> today's date (0DTE)")
        print("Take your time. Every data response is being captured below.")
        print("IMPORTANT: after the chart visibly updates (e.g. you switch to the OI tab),")
        print("wait ~2 seconds so the data response finishes, THEN press ENTER here.")
        print("=" * 80)
        try:
            input()
        except (EOFError, KeyboardInterrupt):
            pass

        # Drain: keep the handler alive a bit so late XHR/postback bodies are read
        # BEFORE the context closes (otherwise resp.text() throws "browser closed").
        print("Draining pending responses (8s)...")
        try:
            page.wait_for_timeout(8000)
        except Exception:
            pass

        # Write the index
        idx_path = OUT / "_index.json"
        idx_path.write_text(json.dumps(index, indent=2), encoding="utf-8")
        print(f"\nSaved {len(index)} responses to {OUT}/")
        print(f"Index: {idx_path}")
        print("\nMost likely data candidates (json, biggest first):")
        for row in sorted([r for r in index if r["json"]],
                          key=lambda r: r["bytes"], reverse=True)[:8]:
            print(f"   [{row['n']:03d}] {row['bytes']:>7}B  {row['file']}")
            print(f"          {row['url'][:110]}")

        print("\nClosing browser...")
        ctx.close()


if __name__ == "__main__":
    main()
