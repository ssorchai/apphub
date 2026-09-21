"""สถานะงานแต่ละตัว — เอาไว้ตอบ /api/health และให้ widget ขึ้นไฟเตือนได้

เก็บไว้ทั้งในหน่วยความจำและเขียนลง store ทุกครั้งที่เปลี่ยน (ไฟล์เล็กมาก)
จะได้ดูย้อนหลังได้แม้ service เพิ่ง restart
"""
import threading
import time

# งานคาบสั้น (gold ทุก 5 วิ) ไม่ต้องเขียนไฟล์ทุก tick -- ของในหน่วยความจำยังสดเสมอ
# ที่เขียนลงดิสก์ช้าได้สุด 15 วินาที ยกเว้นตอนพัง/ตั้งรอบใหม่ ซึ่งเขียนทันที
WRITE_MIN_INTERVAL = 15


class Health:
    def __init__(self, store=None, name="health"):
        self._lock = threading.Lock()
        self._jobs = {}
        self._store = store
        self._name = name
        self.started_at = time.time()
        self._last_write = 0.0

    def _job(self, job):
        return self._jobs.setdefault(job, {
            "runs": 0, "fails": 0, "skips": 0,
            "last_start": None, "last_ok": None, "last_fail": None,
            "last_error": None, "last_duration": None, "next_run": None,
        })

    def _set(self, job, _force=True, **kw):
        with self._lock:
            self._job(job).update(kw)
            if not self._store:
                return
            now = time.time()
            if not _force and now - self._last_write < WRITE_MIN_INTERVAL:
                return
            self._last_write = now
            snap = self.snapshot()
        try:
            self._store.write_json(self._name, snap)
        except Exception:
            pass

    def started(self, job):
        with self._lock:
            j = self._job(job)
            j["runs"] += 1
            j["last_start"] = time.time()

    def ok(self, job, duration):
        self._set(job, _force=False,
                  last_ok=time.time(), last_duration=round(duration, 2), last_error=None)

    def fail(self, job, error):
        with self._lock:
            self._job(job)["fails"] += 1
        self._set(job, last_fail=time.time(), last_error=error)

    def skipped(self, job):
        with self._lock:
            self._job(job)["skips"] += 1

    def next_run(self, job, ts):
        # งาน gold ตั้งรอบใหม่ทุก 5 วินาที ถ้าบังคับเขียนทุกครั้งการหน่วงข้างบนก็ไม่มีผล
        self._set(job, _force=False, next_run=ts)

    def snapshot(self):
        return {
            "started_at": self.started_at,
            "uptime_sec": round(time.time() - self.started_at),
            "now": time.time(),
            "jobs": {k: dict(v) for k, v in self._jobs.items()},
        }
