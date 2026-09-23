"""คอนฟิกของ apphub — ไฟล์เดียวใช้ร่วมทุกบริการ

`~/Library/Application Support/apphub/config.json` (หรือ $APPHUB_DATA/config.json) สิทธิ์ 0600

    {"token": "…", "bind": ["192.168.1.10"], "hosts": ["mac.tail1234.ts.net"]}

- **token คงที่** ไม่สุ่มใหม่ทุก start (ตัดสินใจไว้ 20 ก.ย.) ไม่งั้นปุ่มบนมือถือ/Rainmeter
  จะพังเงียบๆ ทุกครั้งที่ launchd restart -- ไฟล์นี้อยู่นอก git และห้าม log ค่า
- `bind` = address ที่จะเปิดเพิ่มจาก 127.0.0.1 (เช่น IP ของ LAN หรือ Tailscale)
  **ห้ามใส่ 0.0.0.0** (กฎข้อ 1 ของโปรเจกต์ -- ดู PLAN.md)
- `hosts` = ชื่อโฮสต์ที่ยอมให้เรียกเพิ่ม (Host check กัน DNS rebinding)
"""
import json
import os
import secrets
import stat

from .log import err, log
from .store import DEFAULT_ROOT

NAME = "config.json"


def path():
    return os.path.join(os.environ.get("APPHUB_DATA") or DEFAULT_ROOT, NAME)


def load():
    """อ่านคอนฟิก -- ไม่มีไฟล์ก็สร้างพร้อม token สุ่มใหม่ (สิทธิ์ 0600)"""
    p = path()
    try:
        with open(p) as f:
            cfg = json.load(f)
    except FileNotFoundError:
        cfg = {"token": secrets.token_hex(16), "bind": [], "hosts": []}
        os.makedirs(os.path.dirname(p), exist_ok=True)
        tmp = p + ".tmp"
        with open(tmp, "w") as f:
            json.dump(cfg, f, indent=2)
        os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)        # 0600 ก่อน rename
        os.replace(tmp, p)
        log("สร้าง {} พร้อม token ใหม่ (สิทธิ์ 0600) -- ดูค่าด้วย: cat '{}'", NAME, p)
    except Exception as e:
        err("อ่าน {} ไม่ได้ ({}) -- ใช้ค่าปริยาย (loopback อย่างเดียว ไม่มี token)", NAME, type(e).__name__)
        return {"token": None, "bind": [], "hosts": []}

    mode = stat.S_IMODE(os.stat(p).st_mode)
    if mode & 0o077:                                       # คนอื่นอ่าน token ได้
        err("{} สิทธิ์เป็น {:o} -- ควรเป็น 600 (chmod 600 '{}')", NAME, mode, p)
    cfg.setdefault("token", None)
    cfg["bind"] = [a for a in (cfg.get("bind") or []) if a and a != "0.0.0.0"]
    cfg.setdefault("hosts", [])
    return cfg
