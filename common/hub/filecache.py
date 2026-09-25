"""อ่านไฟล์ผลลัพธ์ของ fetcher แบบจำตาม mtime -- ใช้ใน API ทุกบริการ

stat หนึ่งครั้งต่อ request ไฟล์เปลี่ยนถึงค่อย parse ใหม่ / ไฟล์ไม่มีหรือพังคืน None (ไม่ raise)
"""
import os
import threading


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
