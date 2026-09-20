"""log บรรทัดเดียวจบ: launchd เก็บ stdout/stderr ลงไฟล์ให้อยู่แล้ว ไม่ต้องมี handler เอง
(ฟอร์แมตเดียวกับของเดิมใน cme_fetcher เพื่อให้ไล่ log เก่า-ใหม่ต่อกันได้)"""
import sys
from datetime import datetime


def log(msg, *args, **kw):
    line = "[{:%Y-%m-%d %H:%M:%S}] {}".format(datetime.now(), msg.format(*args) if args else msg)
    print(line, file=sys.stderr if kw.get("err") else sys.stdout, flush=True)


def err(msg, *args):
    log(msg, *args, err=True)
