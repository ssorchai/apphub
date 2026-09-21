"""log บรรทัดเดียวจบ: launchd เก็บ stdout/stderr ลงไฟล์ให้อยู่แล้ว ไม่ต้องมี handler เอง
(ฟอร์แมตเดียวกับของเดิมใน cme_fetcher เพื่อให้ไล่ log เก่า-ใหม่ต่อกันได้)"""
import sys
import threading
from datetime import datetime

# หลายงานหลาย thread เขียน log เดียวกัน -- print() แยก write ตัวข้อความกับ "\n" เป็นคนละครั้ง
# บรรทัดเลยซ้อนกันได้ (เจอจริงตอนเพิ่มงาน gold 21 ก.ย.) จึงต่อ \n เองแล้วเขียนครั้งเดียวใต้ล็อก
_lock = threading.Lock()


def log(msg, *args, **kw):
    line = "[{:%Y-%m-%d %H:%M:%S}] {}\n".format(
        datetime.now(), msg.format(*args) if args else msg)
    stream = sys.stderr if kw.get("err") else sys.stdout
    with _lock:
        stream.write(line)
        stream.flush()


def err(msg, *args):
    log(msg, *args, err=True)
