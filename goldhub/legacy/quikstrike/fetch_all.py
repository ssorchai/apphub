#!/usr/bin/env python3
"""
One-command CME QuikStrike Vol2Vol Expected Range scraper for Gold (OG/GC), 0DTE.

Gets ALL of: Intraday Volume, Open Interest, IV smile (Vol), and SD / Expected Range
in a single run. Vol and the SD ranges are embedded in every tab payload, so we only
need to visit two tabs (Intraday + OI) to produce all four datasets.

USAGE
-----
  # Just run it. No login needed: the QuikStrike backend auto-creates a session when
  # the request carries a cmegroup.com Referer, and pid=40 defaults to Gold with the
  # nearest expiry (= today's 0DTE).
  python3 fetch_all.py

  # Force a visible window (debugging):
  python3 fetch_all.py --headed

  # Legacy manual flow (only if the bootstrap URL ever stops working):
  python3 fetch_all.py --login

OUTPUT (in ./out/)
  gold_0dte_intraday.csv   Strike, Call, Put, VolSettle      (intraday volume per strike)
  gold_0dte_oi.csv         Strike, Call, Put, VolSettle      (open interest per strike)
  gold_0dte_vol.csv        Strike, Vol, VolSettle            (IV smile)
  gold_0dte_sdrange.csv    Sigma, Low, High, Width           (expected-range bands)
  gold_0dte_delta.csv      Label, Price                      (5/15/25/35/45 dP/dC lines + Future)
  gold_0dte_all.json       everything + metadata (future price, ATM vol, DTE, totals)
  IntradayData.txt         pageth/Vol2VolData-compatible intraday file
  OIData.txt               pageth/Vol2VolData-compatible open-interest file
"""

import argparse
import csv
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
PROFILE = HERE / ".pw-profile"
SESSION = HERE / "session.json"
OUT = HERE / "out"
OUT.mkdir(exist_ok=True)

CME_PAGE = "https://www.cmegroup.com/tools-information/quikstrike/vol2vol-expected-range.html"
# pid=40/pf=6 = Gold (OG|GC); without insid the server picks the nearest expiry (0DTE).
# The backend auto-logs-in any request whose Referer is a cmegroup.com page.
BOOTSTRAP_URL = ("https://cmegroup-tools.quikstrike.net/User/QuikStrikeView.aspx"
                 "?pid=40&pf=6&viewitemid=IntegratedV2VExpectedRange")
BOOTSTRAP_REFERER = "https://www.cmegroup.com/"
MARKER = "UserControlsV2.QuikOptionsV2V.Chart, "
CTRL_PREFIX = "ctl00$MainContent$ucViewControl_IntegratedV2VExpectedRange$"
TABS = {  # ValueName we expect -> __doPostBack target
    "Intraday Volume": CTRL_PREFIX + "lbIntradayVolume",
    "Open Interest":   CTRL_PREFIX + "lbOI",
}


# --------------------------------------------------------------------------- #
# Payload extraction
# --------------------------------------------------------------------------- #
def extract_payloads(text):
    """Find every $create(...Chart, {<obj>}) in `text` and return parsed settings dicts."""
    out = []
    start = 0
    while True:
        i = text.find(MARKER, start)
        if i < 0:
            break
        try:
            obj = _grab_object(text, text.index("{", i))
            outer = json.loads(obj)
            settings = json.loads(outer["JSONSettings"])
            out.append(settings)
            start = i + len(MARKER)
        except Exception:
            start = i + len(MARKER)
    return out


def _grab_object(s, start):
    depth, in_str, esc, j = 0, False, False, start
    while j < len(s):
        c = s[j]
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
                    return s[start:j + 1]
        j += 1
    raise ValueError("unbalanced braces")


def series_points(settings, key):
    return {round(p["x"], 6): p["y"] for p in settings.get(key, {}).get("data", [])}


# --------------------------------------------------------------------------- #
# Browser flow
# --------------------------------------------------------------------------- #
def run(mode):
    headless = (mode == "normal")
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE),
            headless=headless,
            viewport={"width": 1500, "height": 950},
            locale="en-US",
            timezone_id="Asia/Bangkok",
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        # Collect text from every quikstrike response (safety net besides page.content()).
        blobs = []
        def on_response(resp):
            if "quikstrike" in resp.url and "QuikStrikeView" in resp.url:
                try:
                    blobs.append(resp.text())
                except Exception:
                    pass
        page.on("response", on_response)

        if mode == "login":
            tool_url = _login_flow(page)
            SESSION.write_text(json.dumps({"tool_url": tool_url,
                                           "saved": datetime.now(timezone.utc).isoformat()}))
            print(f"\nSaved session/tool URL to {SESSION.name}")
        else:
            print(f"Bootstrapping session (headless={headless}):\n  {BOOTSTRAP_URL}")
            page.goto(BOOTSTRAP_URL, referer=BOOTSTRAP_REFERER,
                      wait_until="domcontentloaded", timeout=90000)
            _check_alive(page, ctx)
            SESSION.write_text(json.dumps({"tool_url": page.url,
                                           "saved": datetime.now(timezone.utc).isoformat()}))

        # Visit the tabs we need; collect page HTML after each postback.
        blobs.append(page.content())
        for value_name, target in TABS.items():
            try:
                page.evaluate(f"__doPostBack({target!r}, '')")
                try:
                    page.wait_for_load_state("networkidle", timeout=15000)
                except Exception:
                    pass
                page.wait_for_timeout(2500)
                blobs.append(page.content())
            except Exception as e:
                print(f"  ! could not switch to {value_name}: {e}")

        ctx.close()

    payloads = _dedupe([s for b in blobs for s in extract_payloads(b)])
    if not payloads:
        sys.exit("No chart payloads found. Session may have expired -> run --login again.")
    write_outputs(payloads)


def _login_flow(page):
    print(f"\nOpening CME page (window). Navigating...\n  {CME_PAGE}")
    page.goto(CME_PAGE, wait_until="domcontentloaded", timeout=90000)
    print("=" * 78)
    print("In the window:  Product -> Metals -> Gold,  then pick TODAY's expiry (0DTE).")
    print("Wait until the chart shows, then come back here and press ENTER.")
    print("=" * 78)
    try:
        input()
    except (EOFError, KeyboardInterrupt):
        pass
    # The tool runs in an iframe; grab the frame URL that points at QuikStrikeView.
    for fr in page.frames:
        if "QuikStrikeView" in (fr.url or ""):
            return fr.url
    # Fallback: scan page for the iframe src.
    m = re.search(r'https://[^"\']*QuikStrikeView\.aspx[^"\']*', page.content())
    if m:
        return m.group(0)
    sys.exit("Could not find the QuikStrikeView frame URL. Is the tool loaded?")


def _check_alive(page, ctx):
    html = page.content()
    if ("Account/Login.aspx" in html or "Just a moment" in html or "cf-challenge" in html
            or "ErrorPage.aspx" in page.url or "has been denied" in html):
        ctx.close()
        sys.exit("Session bootstrap failed (login/Cloudflare/denied). Try:  python3 fetch_all.py --login")


def _dedupe(payloads):
    """Keep one payload per ValueName (the one with the most strikes)."""
    best = {}
    for s in payloads:
        vn = s.get("ValueName")
        if not vn:
            continue
        n = len(s.get("Call", {}).get("data", []))
        if vn not in best or n > best[vn][0]:
            best[vn] = (n, s)
    return {vn: s for vn, (_, s) in best.items()}


# --------------------------------------------------------------------------- #
# Output
# --------------------------------------------------------------------------- #
def _meta(s):
    sub = re.sub("<[^>]+>", "", s.get("Subtitle", ""))
    sub = sub.replace("&nbsp;", " ").replace("\xa0", " ")
    sub = re.sub(r"\s{2,}", "  ", sub).strip()
    return {
        "title": s.get("Title"),
        "future_price": s.get("FuturePrice"),
        "atm_vol": s.get("ATMVol"),
        "dte": s.get("DTE"),
        "summary": sub,
        "fetched_utc": datetime.now(timezone.utc).isoformat(),
    }


def _write_csv(path, header, rows):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def _num(v):
    """Render 3.0 as 3 but keep real decimals (matches Vol2VolData files)."""
    if v == "" or v is None:
        return "0"
    f = float(v)
    return str(int(f)) if f == int(f) else repr(f)


def _write_v2v_txt(path, s, meta):
    """pageth/Vol2VolData-compatible file, e.g.
    Gold (OG|GC) G1RN6 (0.40 DTE) vs 4087.1 (+4.7) - Intraday Volume
    Put: 1,250  Call: 771  Vol: 45.86  Vol Chg: 0.18  Future Chg: 4.7
    Strike,Call,Put,Vol Settle
    3905,0,3,0.5656203696926241
    """
    product = (s.get("Product") or {}).get("Name", "")
    value_name = s.get("ValueName", "")
    series = s.get("Title", "").replace(value_name, "").strip()
    m = re.search(r"Future Chg:\s*(-?[\d.]+)", meta["summary"])
    chg = f"{float(m.group(1)):+g}" if m else "?"
    header = (f"{product} {series} ({meta['dte']:.2f} DTE) "
              f"vs {meta['future_price']:g} ({chg}) - {value_name}")
    call, put, vs = series_points(s, "Call"), series_points(s, "Put"), series_points(s, "VolSettle")
    lines = [header, meta["summary"], "Strike,Call,Put,Vol Settle"]
    for k in sorted(set(call) | set(put) | set(vs)):
        lines.append(f"{_num(k)},{_num(call.get(k, 0))},{_num(put.get(k, 0))},{vs.get(k, '')}")
    Path(path).write_text("\n".join(lines) + "\n")


def _top_active(rows, n=2):
    """[(strike, total, put, call)] sorted by total desc, from Strike/Call/Put rows."""
    scored = []
    for strike, call, put, _ in rows:
        c = float(call or 0)
        p = float(put or 0)
        if c + p > 0:
            scored.append((strike, c + p, p, c))
    return sorted(scored, key=lambda t: -t[1])[:n]


def write_outputs(payloads):
    by_name = payloads
    combined = {"meta": None, "intraday": [], "oi": [], "vol": [], "sd_range": []}

    # any payload carries Vol + Ranges; prefer OI's, else whatever exists
    ref = by_name.get("Open Interest") or by_name.get("Intraday Volume") or next(iter(by_name.values()))
    combined["meta"] = _meta(ref)

    def strike_rows(s):
        call, put, vs = series_points(s, "Call"), series_points(s, "Put"), series_points(s, "VolSettle")
        rows = []
        for k in sorted(set(call) | set(put) | set(vs)):
            rows.append([k, call.get(k, ""), put.get(k, ""), vs.get(k, "")])
        return rows

    if "Intraday Volume" in by_name:
        s = by_name["Intraday Volume"]
        r = strike_rows(s)
        _write_csv(OUT / "gold_0dte_intraday.csv", ["Strike", "Call", "Put", "VolSettle"], r)
        _write_v2v_txt(OUT / "IntradayData.txt", s, _meta(s))
        combined["intraday"] = r

    if "Open Interest" in by_name:
        s = by_name["Open Interest"]
        r = strike_rows(s)
        _write_csv(OUT / "gold_0dte_oi.csv", ["Strike", "Call", "Put", "VolSettle"], r)
        _write_v2v_txt(OUT / "OIData.txt", s, _meta(s))
        combined["oi"] = r

    # IV smile (Vol + VolSettle) from reference payload
    vol, vset = series_points(ref, "Vol"), series_points(ref, "VolSettle")
    vrows = [[k, vol.get(k, ""), vset.get(k, "")] for k in sorted(set(vol) | set(vset))]
    _write_csv(OUT / "gold_0dte_vol.csv", ["Strike", "Vol", "VolSettle"], vrows)
    combined["vol"] = vrows

    # SD / expected-range bands
    sd = []
    for rg in ref.get("Ranges", {}).get("data", []):
        sd.append([rg.get("Tag", {}).get("Range"), round(rg["x"], 4),
                   round(rg.get("x2", rg["x"]), 4), (rg.get("dataLabels") or {}).get("format")])
    _write_csv(OUT / "gold_0dte_sdrange.csv", ["Sigma", "Low", "High", "Width"], sd)
    combined["sd_range"] = sd

    # Delta level lines: price where option delta = 5/15/25/35/45, per side, + future
    dl = []
    for pl in ref.get("PlotLines", []) or []:
        lbl = (pl.get("label") or {}).get("text", "")
        if not lbl:
            continue
        if lbl.startswith("Future"):
            lbl = "Future"
        dl.append([lbl, round(pl["value"], 4)])
    dl.sort(key=lambda r: r[1])
    _write_csv(OUT / "gold_0dte_delta.csv", ["Label", "Price"], dl)
    combined["delta_lines"] = dl

    (OUT / "gold_0dte_all.json").write_text(json.dumps(combined, indent=2))

    # ---- console summary ----
    m = combined["meta"]
    print("\n" + "=" * 60)
    print(f"{m['title']}")
    print(f"Future {m['future_price']}   ATM Vol {m['atm_vol']*100:.2f}%   DTE {m['dte']:.3f}")
    print(f"{m['summary']}")
    print("=" * 60)
    print(f"tabs captured : {', '.join(by_name)}")
    print(f"intraday rows : {len(combined['intraday'])}")
    print(f"oi rows       : {len(combined['oi'])}")
    print(f"vol rows      : {len(combined['vol'])}")
    print(f"sd bands      : {len(combined['sd_range'])}")
    print(f"delta lines   : {len(combined['delta_lines'])}")
    for label, rows in [("intraday", combined["intraday"]), ("oi", combined["oi"])]:
        for strike, total, put, call in _top_active(rows):
            print(f"top {label:8s}: {_num(strike)} | {int(total)}  (P:{int(put)} / C:{int(call)})")
    print(f"\nWrote CSVs + gold_0dte_all.json to {OUT}/")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--login", action="store_true", help="open a window to pick Gold/0DTE and save session")
    g.add_argument("--headed", action="store_true", help="run a normal fetch but with a visible window")
    a = ap.parse_args()
    run("login" if a.login else "headed" if a.headed else "normal")
