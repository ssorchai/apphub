"""ตารางงานในตัวแอป — แทน cron

ทำไมไม่ใช้ cron ต่อ:
  - cron ยิงรอบใหม่ทับตัวที่ยังรันไม่จบ (gold_fetcher รันยาว 290 วิ ต่อรอบ 300 วิ = เฉียดตลอด)
  - งานหลายตัวต้องใช้ผลของกันและกันในรอบเดียว (snapshot -> clip -> ticker)
  - อยากรู้สถานะว่างานไหนพังล่าสุดเมื่อไหร่ (health) ซึ่ง cron ไม่มีให้

กติกา:
  - งานหนึ่ง = thread หนึ่ง พังแยกกัน งานหนึ่งค้างไม่ลากตัวอื่นตาย
  - `timeout` เป็นแค่ตัวเตือนใน log/health **ไม่ได้ kill งาน** (Python kill thread ไม่ได้)
    งานทุกตัวต้องมีเส้นตายของตัวเอง เช่น cme_fetcher มี MAX_RUNTIME + socket timeout
  - `at_minute` ให้ยึดนาทีเดิมของ cron ได้ (เช่น :07) ไม่ใช่นับจากตอน start
  - `gate` คืน False = ข้ามรอบนั้นเงียบๆ (เช่น ตลาดปิด) ไม่นับเป็น error
"""
import threading
import time
from datetime import datetime

from .log import err, log

TICK = 30        # วินาที ต่อการตื่นมาเช็กเวลาหนึ่งครั้ง
LATE_WARN = 120  # ช้าเกินเท่านี้ (วินาที) ถือว่าผิดปกติ ให้ขึ้น log


class Job:
    def __init__(self, name, fn, interval, timeout=None, at_minute=None,
                 gate=None, run_at_start=True):
        self.name = name
        self.fn = fn
        self.interval = interval          # วินาที
        self.timeout = timeout or interval
        self.at_minute = at_minute        # None = นับจากเวลาเริ่ม / 7 = ทุกชั่วโมงนาทีที่ 7
        self.gate = gate
        self.run_at_start = run_at_start


class Scheduler:
    def __init__(self, health):
        self.health = health
        self.jobs = []
        self._stop = threading.Event()
        self._last_err = {}      # job -> ข้อความ error ล่าสุดที่ log ไปแล้ว
        self._fail_streak = {}   # job -> พลาดติดกันกี่รอบ

    def add(self, *jobs):
        self.jobs.extend(jobs)
        return self

    def _next_due(self, job, now):
        if job.at_minute is None:
            return now + job.interval
        # ยึดนาทีที่กำหนดของชั่วโมงถัดไป (ให้ log เทียบกับยุค cron ได้ตรงๆ)
        t = datetime.fromtimestamp(now).replace(minute=job.at_minute, second=0, microsecond=0)
        nxt = t.timestamp()
        while nxt <= now:
            nxt += max(job.interval, 60)
        return nxt

    def _run_once(self, job):
        if job.gate and not job.gate():
            self.health.skipped(job.name)
            return
        t0 = time.time()
        self.health.started(job.name)
        try:
            job.fn()
            dt = time.time() - t0
            self.health.ok(job.name, dt)
            n = self._fail_streak.pop(job.name, 0)
            if n:
                log("{} กลับมาปกติ (พลาดไป {} รอบ)", job.name, n)
            self._last_err.pop(job.name, None)
            if dt > job.timeout:
                err("{} ใช้เวลา {:.0f}s เกิน timeout ที่ตั้งไว้ {:.0f}s", job.name, dt, job.timeout)
        except Exception as e:
            msg = "{}: {}".format(type(e).__name__, str(e)[:200])
            self.health.fail(job.name, msg)
            # งานคาบสั้น (gold ทุก 5 วิ) ถ้าแหล่งล่มจะพังทุกรอบ -> log ซ้ำเฉพาะตอนข้อความเปลี่ยน
            # ส่วนจำนวนครั้งดูได้จาก health (fails) และบรรทัด "กลับมาปกติ" ตอนหาย
            self._fail_streak[job.name] = self._fail_streak.get(job.name, 0) + 1
            if msg != self._last_err.get(job.name):
                self._last_err[job.name] = msg
                err("{} พัง {}", job.name, msg)

    def _loop(self, job):
        if job.run_at_start:
            self._run_once(job)
        while not self._stop.is_set():
            due = self._next_due(job, time.time())
            self.health.next_run(job.name, due)
            # รอทีละ TICK แล้วเทียบ "เวลาจริง" ใหม่ทุกครั้ง ห้ามรอยาวรวดเดียว:
            # 20 ก.ย. 26 เครื่องหลับข้ามคืน แล้วรอบ :07 หายไปหลายรอบ เพราะ timer
            # ของ Event.wait() ไม่ตรงกับนาฬิกาจริงหลังเครื่องตื่น (ดู PLAN.md)
            while not self._stop.is_set() and time.time() < due:
                if self._stop.wait(min(due - time.time(), TICK)):
                    return
            if self._stop.is_set():
                return
            late = time.time() - due
            if late > LATE_WARN:
                err("{} ยิงช้า {:.0f} นาที (เครื่องหลับ/หยุดชั่วคราว?)", job.name, late / 60)
            self._run_once(job)

    def run_forever(self):
        for job in self.jobs:
            threading.Thread(target=self._loop, args=(job,), name=job.name, daemon=True).start()
            log("job {} ทุก {:.0f}s{}", job.name, job.interval,
                " (นาทีที่ :{:02d})".format(job.at_minute) if job.at_minute is not None else "")
        try:
            while not self._stop.wait(3600):
                pass
        except KeyboardInterrupt:
            log("ได้ Ctrl-C — ออก")
        self._stop.set()

    def stop(self):
        self._stop.set()
