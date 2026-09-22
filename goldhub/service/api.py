"""API ของ goldhub (พอร์ต 8787) — อ่านจากไฟล์ผลลัพธ์ที่ fetcher เขียนไว้แล้วเท่านั้น

ทำไมอ่านจากไฟล์ ไม่ใช่เก็บในหน่วยความจำหลังงานรัน: ปุ่ม refresh ของ widget ยังรัน
cme_fetcher เป็น process แยก ถ้า API จำแค่ผลของ daemon เอง กด refresh แล้วหน้าจอ
จะยังโชว์ของเก่าจนรอบชั่วโมงถัดไป -- อ่านไฟล์โดยจำตาม mtime ได้ของสดเสมอ และถูกมาก
(stat หนึ่งครั้งต่อ request ไฟล์เปลี่ยนถึงค่อย parse ใหม่)

schema_version: เพิ่ม field ได้โดยไม่ต้องขยับ / เปลี่ยนความหมายหรือลบ field = ขยับเลข
"""
import os
import threading
import time

import cme_fetcher
import gold_fetcher as gf
from common.hub import HTML, JS, JSON, TEXT, Api, json_body

SCHEMA_VERSION = 1
PORT = 8787

# ไม่เอาเข้า /api/flat: เป็นตาราง/อาร์เรย์ ใช้ใน key=value ไม่ได้
FLAT_SKIP = {"chart", "delta", "qs", "changes"}


class FileCache:
    """อ่านไฟล์ซ้ำเฉพาะตอน mtime เปลี่ยน -- ไฟล์ไม่มี/พังคืน None (ไม่ raise)"""

    def __init__(self, path, parse):
        self.path, self.parse = path, parse
        self._lock = threading.Lock()
        self._mtime = None
        self._value = None

    def get(self):
        try:
            m = os.stat(self.path).st_mtime
        except OSError:
            return None, None
        with self._lock:
            if m != self._mtime:
                try:
                    with open(self.path, encoding="utf-8") as f:
                        self._value = self.parse(f.read())
                    self._mtime = m
                except Exception:          # อ่านตอนกำลังเขียน/ไฟล์พัง -> ใช้ของเดิมไปก่อน
                    pass
            return self._value, self._mtime


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
    api = Api("goldhub", PORT)
    api.route("/api/state", r_state)
    api.route("/api/flat", r_flat)
    api.route("/api/health", lambda q: (200, JSON, json_body(health.snapshot())))
    api.route("/api/clip", _file_route(clip, TEXT, "clip"))
    # แยกจาก /api/state ตามที่ตัดสินใจไว้: client ที่สนใจแค่ ticker poll ได้โดยไม่ลากก้อนใหญ่
    api.route("/api/ticker", r_ticker)
    api.route("/api/chart", _file_route(chart, HTML, "chart"))
    # หน้ากราฟโหลด "gold_live.js" แบบ relative -- เปิดผ่าน /api/chart จะขอ /api/gold_live.js
    api.route("/api/gold_live.js", _file_route(live_js, JS, "gold_live.js"))
    api.route("/", lambda q: (200, JSON, json_body({"service": "goldhub",
                                                     "schema_version": SCHEMA_VERSION,
                                                     "routes": sorted(api.routes)})))
    return api
