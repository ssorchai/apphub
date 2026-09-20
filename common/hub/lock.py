"""กันรันซ้อน — หนึ่งบริการต่อหนึ่ง process

เจอของจริง 20 ก.ย. 2026: process ทดสอบที่รันจาก shell ค้างอยู่สองตัวโดยไม่รู้ตัว
(pkill ไม่โดนเพราะ argv เป็น "app.py" เฉยๆ ไม่ใช่ path เต็ม) พอ launchd โหลดตัวจริงขึ้นมา
เลยมีสามตัวยิง QuikStrike พร้อมกันที่นาที :07 — ซึ่งเป็นสิ่งที่เราพยายามเลี่ยงที่สุด

flock ปลดเองเมื่อ process ตาย ไม่ต้องเก็บกวาด pid file ค้าง
"""
import fcntl
import os


def single_instance(path):
    """คืน file object ถ้าจองได้ (ต้องเก็บ reference ไว้ทั้งอายุโปรแกรม ไม่งั้น GC ปิดไฟล์
    แล้ว lock หลุด) / คืน None ถ้ามีตัวอื่นถืออยู่"""
    f = open(path, "a+")
    try:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        return None
    f.seek(0)
    f.truncate()
    f.write(str(os.getpid()))
    f.flush()
    return f


def holder_pid(path):
    """pid ของตัวที่ถือ lock อยู่ (ไว้บอกใน log ว่าไปชนกับใคร)"""
    try:
        with open(path) as f:
            return f.read().strip()
    except Exception:
        return "?"
