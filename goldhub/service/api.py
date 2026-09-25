"""API ของ goldhub (พอร์ต 8787) — อ่านจากไฟล์ผลลัพธ์ที่ fetcher เขียนไว้แล้วเท่านั้น

ทำไมอ่านจากไฟล์ ไม่ใช่เก็บในหน่วยความจำหลังงานรัน: ปุ่ม refresh ของ widget ยังรัน
cme_fetcher เป็น process แยก ถ้า API จำแค่ผลของ daemon เอง กด refresh แล้วหน้าจอ
จะยังโชว์ของเก่าจนรอบชั่วโมงถัดไป -- อ่านไฟล์โดยจำตาม mtime ได้ของสดเสมอ และถูกมาก
(stat หนึ่งครั้งต่อ request ไฟล์เปลี่ยนถึงค่อย parse ใหม่)

schema_version: เพิ่ม field ได้โดยไม่ต้องขยับ / เปลี่ยนความหมายหรือลบ field = ขยับเลข
"""
import os
import platform
import subprocess
import threading
import time

import cme_fetcher
import gold_fetcher as gf
from common.hub import HTML, JS, JSON, TEXT, Api, FileCache, config, err, json_body, log

SCHEMA_VERSION = 1
PORT = 8787

# ไม่เอาเข้า /api/flat: เป็นตาราง/อาร์เรย์ ใช้ใน key=value ไม่ได้
FLAT_SKIP = {"chart", "delta", "qs", "changes"}


def _json(txt):
    import json
    return json.loads(txt)


def _text(txt):
    return txt


cme = FileCache(cme_fetcher.JSON_OUT, _json)
live = FileCache(gf.JSON_PATH, _json)
clip = FileCache(cme_fetcher.CLIP_OUT, _text)
chart = FileCache(cme_fetcher.CHART_OUT, _text)
live_js = FileCache(gf.LIVE_JS_PATH, _text)
tick = FileCache("/tmp/cme_ticker.json", _json)       # ticker.OUT (ไม่ import กันวงวน)

# หน้าเว็บ dashboard = หน้า host + widget ไฟล์เดียวกับที่ Übersicht ใช้ ที่ build เป็น .js แล้ว
# ไม่พึ่ง CDN / ไม่มี Babel ในเบราว์เซอร์ (22 ก.ย. 26) ทุกไฟล์อ่านจาก repo ตาม mtime
_GOLDHUB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_WEB = os.path.join(_GOLDHUB, "web")
DASH_JSX = os.path.join(_GOLDHUB, "widgets", "gold-dashboard.jsx")
DASH_JS = os.path.join(_WEB, "dist", "gold-dashboard.js")
dash_html = FileCache(os.path.join(_WEB, "dashboard.html"), _text)
dash_js = FileCache(DASH_JS, _text)
vendor = {n: FileCache(os.path.join(_WEB, "vendor", n), _text)
          for n in ("react.production.min.js", "react-dom.production.min.js")}

# ตัว build = node + Babel ที่มากับ Übersicht.app (ไม่ต้องติดตั้งอะไร) -- ไม่มี (cloud) ก็เสิร์ฟ dist
# ที่ commit ไว้แทน / build เฉพาะตอน .jsx ใหม่กว่า dist แก้ .jsx แล้ว reload หน้าเว็บได้เลย
_UB = "/Applications/Übersicht.app/Contents/Resources"
_NODE = os.path.join(_UB, "node-arm64" if platform.machine() == "arm64" else "node-x64")
_build_lock = threading.Lock()
_build_err = {"msg": None}


def ensure_built():
    with _build_lock:
        try:
            if os.stat(DASH_JSX).st_mtime <= os.stat(DASH_JS).st_mtime:
                return
        except OSError:
            pass                                   # dist ยังไม่มี -> build
        if not os.path.exists(_NODE):
            return                                 # ไม่มี Übersicht: ใช้ dist เดิม
        try:
            subprocess.run([_NODE, os.path.join(_WEB, "build.js"), DASH_JSX, DASH_JS],
                           env={"UB_NODE_MODULES": os.path.join(_UB, "node_modules")},
                           capture_output=True, text=True, timeout=30, check=True)
            log("dashboard: build widget ใหม่จาก {}", os.path.basename(DASH_JSX))
            _build_err["msg"] = None
        except Exception as e:                     # .jsx พัง -> ใช้ dist ตัวล่าสุดที่ดีต่อ
            m = (getattr(e, "stderr", None) or str(e)).strip()
            if m != _build_err["msg"]:
                # stderr ของ Babel ปิดท้ายด้วย code frame -- หยิบบรรทัดที่บอกชนิด error + ตำแหน่งมาแทน
                lines = m.splitlines()
                why = next((ln for ln in lines if "Error" in ln), lines[0] if lines else type(e).__name__)
                err("dashboard: build ไม่ผ่าน ใช้ตัวเดิม ({})", why.strip()[:200])
                _build_err["msg"] = m


def _age(v):
    ts = (v or {}).get("ts")
    return round(time.time() - ts) if isinstance(ts, (int, float)) else None


def state_obj():
    c, _ = cme.get()
    g, _ = live.get()
    return {
        "schema_version": SCHEMA_VERSION,
        "service": "goldhub",
        "ts": round(time.time(), 3),
        "age": {"cme": _age(c), "live": _age(g)},   # วินาที ให้ client ตัดสินเองว่าเก่าไป
        "cme": c,
        "live": g,
    }


def _fields(query):
    raw = ",".join(query.get("fields", []))
    return {f.strip() for f in raw.split(",") if f.strip()}


def r_state(query):
    s = state_obj()
    want = _fields(query)
    if want:
        s = {k: v for k, v in s.items() if k in want or k == "schema_version"}
    return 200, JSON, json_body(s)


def _flatten(prefix, v, out):
    if isinstance(v, dict):
        for k, x in v.items():
            if k in FLAT_SKIP:
                continue
            _flatten("{}.{}".format(prefix, k) if prefix else k, x, out)
    elif isinstance(v, list):
        return
    else:
        out.append("{}={}".format(prefix, "" if v is None else v))


def r_flat(query):
    s = state_obj()
    lines = []
    _flatten("", s, lines)
    return 200, TEXT, "\n".join(lines) + "\n"


def r_widget(query):
    ensure_built()
    v, _ = dash_js.get()
    return (200, JS, v) if v is not None else (503, TEXT, "widget ยังไม่ได้ build\n")


def r_ticker(query):
    v, _ = tick.get()
    if v is None:
        return 503, TEXT, "ticker ยังไม่มี (รอรอบ 5 นาทีแรก)\n"
    return 200, JSON, json_body(dict(v, schema_version=SCHEMA_VERSION))


def _file_route(cache, ctype, what):
    def r(query):
        v, _ = cache.get()
        if v is None:
            return 503, TEXT, "{} ยังไม่มี (fetcher ยังไม่ได้เขียนไฟล์)\n".format(what)
        return 200, ctype, v
    return r


def build(health):
    cfg = config.load()
    api = Api("goldhub", PORT, token=cfg.get("token"),
              extra_binds=cfg.get("bind"), extra_hosts=cfg.get("hosts"))
    api.route("/api/state", r_state)
    api.route("/api/flat", r_flat)
    api.route("/api/health", lambda q: (200, JSON, json_body(health.snapshot())))
    api.route("/api/clip", _file_route(clip, TEXT, "clip"))
    # แยกจาก /api/state ตามที่ตัดสินใจไว้: client ที่สนใจแค่ ticker poll ได้โดยไม่ลากก้อนใหญ่
    api.route("/api/ticker", r_ticker)
    api.route("/api/chart", _file_route(chart, HTML, "chart"))
    # หน้ากราฟโหลด "gold_live.js" แบบ relative -- เปิดผ่าน /api/chart จะขอ /api/gold_live.js
    api.route("/api/gold_live.js", _file_route(live_js, JS, "gold_live.js"))
    api.route("/dashboard", _file_route(dash_html, HTML, "dashboard.html"))
    api.route("/dashboard/widget.js", r_widget)
    for n, fc in vendor.items():
        api.route("/dashboard/vendor/" + n, _file_route(fc, JS, n))
    ensure_built()
    api.route("/", lambda q: (200, JSON, json_body({"service": "goldhub",
                                                     "schema_version": SCHEMA_VERSION,
                                                     "routes": sorted(api.routes)})))
    return api
