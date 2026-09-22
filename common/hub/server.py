"""HTTP API ขั้นต่ำของทุกบริการ — stdlib ล้วน (http.server + threading)

กติกา (ดู "กฎที่ห้ามละเมิด" ใน PLAN.md):
  - **อ่านอย่างเดียว** รับแค่ GET/HEAD/OPTIONS และ handler ต้องคืนของจาก cache/ไฟล์ที่มีอยู่
    ห้ามไปกระตุ้นให้ดึง upstream ไม่งั้นใครยิงถี่ๆ = เราไปถล่มแหล่งข้อมูลแทน
  - bind 127.0.0.1 เป็นค่าเริ่ม (เฟส 4 ค่อยเพิ่ม IP ของ Tailscale) ไม่ใช่ 0.0.0.0
  - เช็ค Host header กัน DNS rebinding: เว็บที่เปิดในเบราว์เซอร์ชี้โดเมนตัวเองมาที่ 127.0.0.1
    แล้วอ่าน API ได้ ถ้าไม่ตรวจ Host
  - ETag / If-None-Match -> 304 ให้ client ที่ poll บ่อยไม่ต้องลากก้อนเต็มทุกครั้ง
  - CORS * : widget ของ Übersicht มาจาก origin อื่น (127.0.0.1:41416) ต้องมี header นี้
    ข้อมูลเป็นราคาตลาดสาธารณะ ส่วนที่ต้องกันจริงคือการ "สั่งงาน" ซึ่ง API นี้ไม่มีให้
  - token ปิดไว้ในเฟส 2 (ผูก loopback อยู่แล้ว) ตั้ง `token=` เมื่อไหร่ก็บังคับทันที
    รับได้ทั้ง header X-Apphub-Token และ ?token= (Rainmeter ใส่ header ไม่สะดวก) ไม่ log ค่า

route หนึ่งตัว = ฟังก์ชัน (query: dict) -> (status, content_type, body: bytes|str)
"""
import hashlib
import hmac
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from .log import err, log

JSON = "application/json; charset=utf-8"
TEXT = "text/plain; charset=utf-8"
HTML = "text/html; charset=utf-8"
JS = "application/javascript; charset=utf-8"


def json_body(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


class Api:
    def __init__(self, name, port, host="127.0.0.1", token=None):
        self.name = name
        self.port = port
        self.host = host
        self.token = token
        self.routes = {}
        self._httpd = None
        # Host ที่ยอมรับ: เรียกด้วย localhost หรือ IP ที่ bind (เฟส 4 จะเพิ่มชื่อของ Tailscale)
        self.allowed_hosts = {"localhost", "127.0.0.1", host}

    def route(self, path, fn):
        self.routes[path] = fn
        return self

    # ---------- ตัวจัดการ request ----------
    def _handler(self):
        api = self

        class H(BaseHTTPRequestHandler):
            server_version = "apphub"
            sys_version = ""

            def log_message(self, *a):        # widget poll ทุก 5 วิ -- ไม่ log ทุก request
                pass

            def _send(self, status, ctype, body=b"", extra=None, head=False):
                self.send_response(status)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Headers", "X-Apphub-Token, If-None-Match")
                self.send_header("Access-Control-Expose-Headers", "ETag")
                self.send_header("Cache-Control", "no-cache")
                if ctype:
                    self.send_header("Content-Type", ctype)
                for k, v in (extra or {}).items():
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                if body and not head:
                    self.wfile.write(body)

            def _host_ok(self):
                host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]")
                return host in api.allowed_hosts

            def _token_ok(self, query):
                if not api.token:
                    return True
                got = self.headers.get("X-Apphub-Token") or (query.get("token") or [""])[0]
                return hmac.compare_digest(got.encode(), api.token.encode())

            def do_OPTIONS(self):
                self._send(204, None)

            def do_HEAD(self):
                self.do_GET(head=True)

            def do_GET(self, head=False):
                u = urlsplit(self.path)
                query = parse_qs(u.query)
                if not self._host_ok():
                    return self._send(403, TEXT, b"bad host\n", head=head)
                if not self._token_ok(query):
                    return self._send(401, TEXT, b"token required\n", head=head)
                fn = api.routes.get(u.path.rstrip("/") or "/")
                if fn is None:
                    body = json_body({"error": "not found", "routes": sorted(api.routes)}).encode()
                    return self._send(404, JSON, body, head=head)
                try:
                    status, ctype, body = fn(query)
                except Exception as e:           # handler พังไม่ควรลากทั้ง service ล่ม
                    err("api {} พัง {}: {}", u.path, type(e).__name__, str(e)[:160])
                    return self._send(500, JSON, json_body({"error": type(e).__name__}).encode(),
                                      head=head)
                if isinstance(body, str):
                    body = body.encode("utf-8")
                etag = '"{}"'.format(hashlib.sha1(body).hexdigest()[:16])
                if status == 200 and self.headers.get("If-None-Match") == etag:
                    return self._send(304, None, extra={"ETag": etag}, head=head)
                self._send(status, ctype, body, extra={"ETag": etag}, head=head)

        return H

    def start(self):
        """เปิดใน thread แยก -- พอร์ตชนก็แค่ log แล้วเดินต่อ งานดึงข้อมูลต้องไม่พังเพราะ API"""
        try:
            self._httpd = ThreadingHTTPServer((self.host, self.port), self._handler())
        except OSError as e:
            err("api {} เปิดพอร์ต {}:{} ไม่ได้ ({}) — ทำงานต่อโดยไม่มี API",
                self.name, self.host, self.port, e.strerror or e)
            return False
        self._httpd.daemon_threads = True
        threading.Thread(target=self._httpd.serve_forever, name="api", daemon=True).start()
        log("api {} ฟังที่ http://{}:{} ({})", self.name, self.host, self.port,
            ", ".join(sorted(self.routes)))
        return True
