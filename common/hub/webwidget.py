"""หน้าเว็บ dashboard ของแต่ละบริการ = หน้า host + widget ไฟล์เดียวกับที่ Übersicht ใช้

ไม่พึ่ง CDN / ไม่มี Babel ในเบราว์เซอร์ (22 ก.ย. 26) -- .jsx ถูก build เป็น .js ด้วย
common/web/build.js ส่วน React อยู่ที่ common/web/vendor ใช้ร่วมทุกบริการ (ย้ายจาก goldhub 25 ก.ย.)
ทุกไฟล์อ่านจาก repo ตาม mtime

ตัว build = node + Babel ที่มากับ Übersicht.app (ไม่ต้องติดตั้งอะไร) -- ไม่มี (cloud) ก็เสิร์ฟ dist
ที่ commit ไว้แทน / build เฉพาะตอน .jsx ใหม่กว่า dist แก้ .jsx แล้ว reload หน้าเว็บได้เลย
"""
import os
import platform
import subprocess
import threading

from .filecache import FileCache
from .log import err, log
from .server import HTML, JS, TEXT

_COMMON_WEB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")
BUILD_JS = os.path.join(_COMMON_WEB, "build.js")
VENDOR = ("react.production.min.js", "react-dom.production.min.js")
_UB = "/Applications/Übersicht.app/Contents/Resources"
_NODE = os.path.join(_UB, "node-arm64" if platform.machine() == "arm64" else "node-x64")


def _text(txt):
    return txt


def _file_route(cache, ctype, what):
    def r(query):
        v, _ = cache.get()
        if v is None:
            return 503, TEXT, "{} ยังไม่มี\n".format(what)
        return 200, ctype, v
    return r


class WebWidget:
    def __init__(self, jsx, dist, html):
        self.jsx, self.dist = jsx, dist
        self.html = FileCache(html, _text)
        self.js = FileCache(dist, _text)
        self.vendor = {n: FileCache(os.path.join(_COMMON_WEB, "vendor", n), _text) for n in VENDOR}
        self._lock = threading.Lock()
        self._last_err = None

    def ensure_built(self):
        with self._lock:
            try:
                if os.stat(self.jsx).st_mtime <= os.stat(self.dist).st_mtime:
                    return
            except OSError:
                pass                                   # dist ยังไม่มี -> build
            if not os.path.exists(_NODE):
                return                                 # ไม่มี Übersicht: ใช้ dist เดิม
            try:
                os.makedirs(os.path.dirname(self.dist), exist_ok=True)
                subprocess.run([_NODE, BUILD_JS, self.jsx, self.dist],
                               env={"UB_NODE_MODULES": os.path.join(_UB, "node_modules")},
                               capture_output=True, text=True, timeout=30, check=True)
                log("dashboard: build widget ใหม่จาก {}", os.path.basename(self.jsx))
                self._last_err = None
            except Exception as e:                     # .jsx พัง -> ใช้ dist ตัวล่าสุดที่ดีต่อ
                m = (getattr(e, "stderr", None) or str(e)).strip()
                if m != self._last_err:
                    # stderr ของ Babel ปิดท้ายด้วย code frame -- หยิบบรรทัดที่บอกชนิด error + ตำแหน่งมาแทน
                    lines = m.splitlines()
                    why = next((ln for ln in lines if "Error" in ln), lines[0] if lines else type(e).__name__)
                    err("dashboard: build ไม่ผ่าน ใช้ตัวเดิม ({})", why.strip()[:200])
                    self._last_err = m

    def _r_widget(self, query):
        self.ensure_built()
        v, _ = self.js.get()
        return (200, JS, v) if v is not None else (503, TEXT, "widget ยังไม่ได้ build\n")

    def mount(self, api):
        """/dashboard (หน้า host), /dashboard/widget.js, /dashboard/vendor/<react>"""
        api.route("/dashboard", _file_route(self.html, HTML, "dashboard.html"))
        api.route("/dashboard/widget.js", self._r_widget)
        for n, fc in self.vendor.items():
            api.route("/dashboard/vendor/" + n, _file_route(fc, JS, n))
        self.ensure_built()
        return api
