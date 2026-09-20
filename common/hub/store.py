"""ที่เก็บข้อมูลของบริการ — อยู่นอก /tmp เพราะ macOS ล้าง /tmp ตอน reboot

โครง:
    <root>/<service>/state/<name>.json      สถานะล่าสุด (เขียนทับ atomic)
    <root>/<service>/history/<stream>/<YYYY-MM-DD>.jsonl   ประวัติรายวัน (ลบเมื่อเกิน retention)

root: $APPHUB_DATA ถ้ามี (ใช้ตอนขึ้น cloud/docker) ไม่งั้น
      ~/Library/Application Support/apphub (macOS)
"""
import json
import os
import time

DEFAULT_ROOT = os.path.expanduser("~/Library/Application Support/apphub")


class Store:
    def __init__(self, service, root=None):
        self.root = os.path.join(root or os.environ.get("APPHUB_DATA") or DEFAULT_ROOT, service)
        os.makedirs(os.path.join(self.root, "state"), exist_ok=True)
        os.makedirs(os.path.join(self.root, "history"), exist_ok=True)

    # ---------- ไฟล์สถานะ ----------
    def path(self, *parts):
        return os.path.join(self.root, *parts)

    def write_json(self, name, obj):
        self._atomic(self.path("state", name + ".json"), json.dumps(obj))

    def read_json(self, name, default=None):
        try:
            with open(self.path("state", name + ".json")) as f:
                return json.load(f)
        except Exception:
            return default

    @staticmethod
    def _atomic(path, text):
        """เขียนไฟล์ชั่วคราวแล้ว rename — กัน widget อ่านไฟล์ครึ่งๆ กลางๆ ตอนกำลังเขียน"""
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            f.write(text)
        os.replace(tmp, path)

    # ---------- ประวัติรายวัน ----------
    def append_history(self, stream, obj):
        d = self.path("history", stream)
        os.makedirs(d, exist_ok=True)
        day = time.strftime("%Y-%m-%d")
        with open(os.path.join(d, day + ".jsonl"), "a") as f:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")

    # ---------- ล้างของเก่า ----------
    def retention(self, days=7, cap_mb=200):
        """ลบประวัติเก่ากว่า `days` วัน แล้วถ้ายังเกิน cap ให้ลบจากเก่าสุดต่อจนต่ำกว่า cap
        (cap เป็นกันเหนียว เผื่อวันไหนมี event เยอะผิดปกติจนไฟล์บวม)"""
        cutoff = time.time() - days * 86400
        files = []
        for dirpath, _, names in os.walk(self.path("history")):
            for n in names:
                p = os.path.join(dirpath, n)
                try:
                    st = os.stat(p)
                except OSError:
                    continue
                files.append((st.st_mtime, st.st_size, p))
        removed = []
        keep = []
        for mtime, size, p in files:
            if mtime < cutoff:
                try:
                    os.remove(p)
                    removed.append(p)
                except OSError:
                    pass
            else:
                keep.append((mtime, size, p))
        total = sum(s for _, s, _ in keep)
        for mtime, size, p in sorted(keep):
            if total <= cap_mb * 1024 * 1024:
                break
            try:
                os.remove(p)
                removed.append(p)
                total -= size
            except OSError:
                pass
        return {"removed": len(removed), "bytes_left": total}
