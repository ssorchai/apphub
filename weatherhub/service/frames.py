"""เฟรมเรดาร์ย้อนหลัง -- ภาพนิ่งที่งาน radar ดึงอยู่แล้วทุก 5 นาที เก็บไว้เล่นเป็นภาพเคลื่อนไหวบนเว็บ

ทำไมไม่ใช้ loop GIF ของ กทม.: ต้องยิงต้นทางเพิ่ม (ผู้ใช้เลือกไว้ 25 ก.ย. ว่าโหลด loop เฉพาะรอบเช็ค
16:xx) ส่วนภาพนิ่งเราได้มาฟรีทุกรอบอยู่แล้ว เป็นภาพชุดเดียวกัน 965x800 ห่าง 5 นาทีเท่า GIF
ข้อจำกัด: ช่วงที่เครื่องหลับจะไม่มีเฟรม / เพิ่ง start ต้องรอสะสม

ไฟล์: <store>/frames/<ts>.<ext> (ts = เวลาที่ดึง epoch วินาที) -- อยู่นอก /tmp จะได้รอด reboot
ภาพซ้ำกับเฟรมล่าสุด (ต้นทางยังไม่อัปเดต) ไม่เก็บซ้ำ
"""
import base64
import hashlib
import os
import time

KEEP_SEC = 2 * 3600          # เก็บย้อนหลัง 2 ชั่วโมง (~24 เฟรม x ~110 KB)
MAX_FRAMES = 40
EXT = {"image/jpeg": "jpg", "image/png": "png", "image/gif": "gif"}
MIME = {v: k for k, v in EXT.items()}


def listing(folder):
    """[(ts, filename)] เรียงจากเก่าไปใหม่ -- ไฟล์แปลกปลอมข้าม"""
    out = []
    try:
        names = os.listdir(folder)
    except OSError:
        return out
    for n in names:
        stem, _, ext = n.partition(".")
        if stem.isdigit() and ext in MIME:
            out.append((int(stem), n))
    return sorted(out)


def save(folder, meta):
    """เก็บภาพจาก weather_meta.json หนึ่งเฟรม คืน True ถ้าเก็บใหม่"""
    raw = base64.b64decode(meta.get("img_base64") or b"")
    if not raw:
        return False
    os.makedirs(folder, exist_ok=True)
    frames = listing(folder)
    if frames:
        try:
            with open(os.path.join(folder, frames[-1][1]), "rb") as f:
                if hashlib.sha1(f.read()).digest() == hashlib.sha1(raw).digest():
                    return False
        except OSError:
            pass
    ts = int(meta.get("ts") or time.time())
    name = "{}.{}".format(ts, EXT.get(meta.get("mime"), "jpg"))
    tmp = os.path.join(folder, "." + name + ".tmp")
    with open(tmp, "wb") as f:
        f.write(raw)
    os.replace(tmp, os.path.join(folder, name))
    prune(folder)
    return True


def prune(folder, now=None):
    now = now or time.time()
    frames = listing(folder)
    drop = [n for ts, n in frames if now - ts > KEEP_SEC]
    keep = [f for f in frames if f[1] not in drop]
    drop += [n for _, n in keep[:-MAX_FRAMES]] if len(keep) > MAX_FRAMES else []
    for n in drop:
        try:
            os.remove(os.path.join(folder, n))
        except OSError:
            pass
