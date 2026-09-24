"""HTTP API ขั้นต่ำของทุกบริการ — stdlib ล้วน (http.server + threading)

กติกา (ดู "กฎที่ห้ามละเมิด" ใน PLAN.md):
  - **อ่านอย่างเดียว** รับแค่ GET/HEAD/OPTIONS และ handler ต้องคืนของจาก cache/ไฟล์ที่มีอยู่
    ห้ามไปกระตุ้นให้ดึง upstream ไม่งั้นใครยิงถี่ๆ = เราไปถล่มแหล่งข้อมูลแทน
  - bind 127.0.0.1 เสมอ + address ที่ระบุใน config (`bind`; คำว่า "lan" = IP ปัจจุบันของเครื่อง)
    **ไม่ใช้ 0.0.0.0** -- เปิดคนละ
    listener ต่อ address ไม่ใช่เปิดทั้งเครื่องแล้วมากรองทีหลัง
  - เช็ค Host header กัน DNS rebinding: เว็บที่เปิดในเบราว์เซอร์ชี้โดเมนตัวเองมาที่ 127.0.0.1
    แล้วอ่าน API ได้ ถ้าไม่ตรวจ Host
  - ETag / If-None-Match -> 304 ให้ client ที่ poll บ่อยไม่ต้องลากก้อนเต็มทุกครั้ง
  - CORS * : widget ของ Übersicht มาจาก origin อื่น (127.0.0.1:41416) ต้องมี header นี้
    ข้อมูลเป็นราคาตลาดสาธารณะ ส่วนที่ต้องกันจริงคือการ "สั่งงาน" ซึ่ง API นี้ไม่มีให้
  - **token บังคับเฉพาะคนที่มาจากนอกเครื่อง** (เฟส 4): 127.0.0.1 ยังเรียกได้เปล่าๆ เพื่อให้
    widget/หน้าเว็บบนเครื่องเดียวกันไม่ต้องถือ token ส่วนเครื่องอื่นต้องมี
    รับได้ทั้ง header X-Apphub-Token, ?token= (Rainmeter ใส่ header ไม่สะดวก) และ cookie
    -- เปิดหน้าเว็บจากเครื่องอื่นต้องใช้ cookie เพราะ <script src> แนบ header เองไม่ได้:
    เข้า /dashboard?token=… ครั้งเดียว เซิร์ฟเวอร์ set cookie ให้ แล้วไฟล์ย่อย/fetch ตามมาได้เอง
    (อ่านอย่างเดียวทั้งหมด + CORS เป็น * ซึ่งเบราว์เซอร์ไม่ส่ง cookie ข้าม origin ให้อยู่แล้ว)
    ไม่ log ค่า token

route หนึ่งตัว = ฟังก์ชัน (query: dict) -> (status, content_type, body: bytes|str)
"""
import hashlib
import hmac
import json
import socket
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


LOOPBACK = ("127.0.0.1", "::1")


def lan_ip():
    """IP ของ interface ที่ใช้ออกเน็ตตอนนี้ -- UDP connect ไม่ได้ส่งอะไรจริง แค่ให้ kernel
    เลือก route ให้ / ใช้กับคำว่า "lan" ใน config จะได้ไม่ต้องแก้ไฟล์ทุกครั้งที่ย้ายเน็ต"""
    sk = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sk.connect(("8.8.8.8", 53))
        return sk.getsockname()[0]
    except OSError:
        return None
    finally:
        sk.close()
COOKIE = "apphub_token"


class Api:
    def __init__(self, name, port, host="127.0.0.1", token=None, extra_binds=(), extra_hosts=()):
        self.name = name
        self.port = port
        self.host = host
        self.token = token
        extra = [lan_ip() if a == "lan" else a for a in (extra_binds or [])]
        self.binds = [host] + [a for a in extra if a and a != host and a != "0.0.0.0"]
        self.routes = {}
        self._httpds = []
        # Host ที่ยอมรับ: localhost, ทุก address ที่ bind และชื่อที่ระบุเพิ่มใน config
        self.allowed_hosts = {"localhost"} | set(self.binds) | set(extra_hosts)

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

            def _cookie_token(self):
                raw = self.headers.get("Cookie") or ""
                for part in raw.split(";"):
                    k, _, v = part.strip().partition("=")
                    if k == COOKIE:
                        return v
                return ""

            def _token_ok(self, query):
                # เครื่องเดียวกันผ่านได้เลย / เครื่องอื่นต้องมี token (ถ้าตั้งไว้)
                if self.client_address[0] in LOOPBACK or not api.token:
                    return True
                got = (self.headers.get("X-Apphub-Token")
                       or (query.get("token") or [""])[0] or self._cookie_token())
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
                # มากับ ?token= ที่ถูก -> ฝาก cookie ไว้ ไฟล์ย่อยของหน้าเว็บจะตามมาได้เอง
                extra = {}
                if (api.token and self.client_address[0] not in LOOPBACK
                        and (query.get("token") or [""])[0] == api.token):
                    extra["Set-Cookie"] = ("{}={}; Path=/; Max-Age=604800; SameSite=Lax"
                                           .format(COOKIE, api.token))
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
                extra["ETag"] = etag
                if status == 200 and self.headers.get("If-None-Match") == etag:
                    return self._send(304, None, extra=extra, head=head)
                self._send(status, ctype, body, extra=extra, head=head)

        return H

    def start(self):
        """เปิด listener หนึ่งตัวต่อ address ใน thread แยก -- address ไหนเปิดไม่ได้ก็ข้ามตัวนั้น
        (เช่น IP ของ Tailscale ยังไม่ขึ้น) ขอให้ loopback ขึ้นก็พอ งานดึงข้อมูลต้องไม่พังเพราะ API"""
        handler = self._handler()
        ok = []
        for addr in self.binds:
            try:
                httpd = ThreadingHTTPServer((addr, self.port), handler)
            except OSError as e:
                err("api {} เปิด {}:{} ไม่ได้ ({}) — ข้าม address นี้",
                    self.name, addr, self.port, e.strerror or e)
                continue
            httpd.daemon_threads = True
            self._httpds.append(httpd)
            threading.Thread(target=httpd.serve_forever, name="api-" + addr, daemon=True).start()
            ok.append(addr)
        if not ok:
            err("api {} เปิดไม่ได้เลย — ทำงานต่อโดยไม่มี API", self.name)
            return False
        log("api {} ฟังที่ {} พอร์ต {}{} ({})", self.name, ", ".join(ok), self.port,
            " · token เปิดใช้กับเครื่องอื่น" if self.token else "", ", ".join(sorted(self.routes)))
        return True
