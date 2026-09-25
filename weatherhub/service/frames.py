"""เฟรมเรดาร์ย้อนหลัง -- ภาพนิ่งที่งาน radar ดึงอยู่แล้วทุก 5 นาที เก็บไว้เล่นเป็นภาพเคลื่อนไหวบนเว็บ

ทำไมไม่ใช้ loop GIF ของ กทม.: ต้องยิงต้นทางเพิ่ม (ผู้ใช้เลือกไว้ 25 ก.ย. ว่าโหลด loop เฉพาะรอบเช็ค
16:xx) ส่วนภาพนิ่งเราได้มาฟรีทุกรอบอยู่แล้ว เป็นภาพชุดเดียวกัน 965x800 ห่าง 5 นาทีเท่า GIF
ข้อจำกัด: ช่วงที่เครื่องหลับจะไม่มีเฟรม / เพิ่ง start ต้องรอสะสม

ไฟล์: <store>/frames/<ts>.<ext> -- ts = **เวลาในภาพ** (epoch) อ่านด้วย OCR จากมุมขวาล่าง
("2026-09-25 15:35:00") ไม่ใช่เวลาที่ดึง: ภาพของ กทม. ออกช้ากว่าเวลาในภาพ 5-10 นาทีและแกว่ง
OCR ไม่ได้ = ประมาณด้วยเวลาดึง - FALLBACK_LAG_MIN / อยู่นอก /tmp จะได้รอด reboot
ภาพที่เวลาในภาพซ้ำกับที่มีแล้ว (ต้นทางยังไม่อัปเดต) ไม่เก็บซ้ำ
"""
import base64
import hashlib
import os
import re
import subprocess
import threading
import time
from datetime import datetime

KEEP_SEC = 2 * 3600          # เก็บย้อนหลัง 2 ชั่วโมง (~24 เฟรม x ~110 KB)
MAX_FRAMES = 40
EXT = {"image/jpeg": "jpg", "image/png": "png", "image/gif": "gif"}
MIME = {v: k for k, v in EXT.items()}
FALLBACK_LAG_MIN = 6         # ใช้เมื่อ OCR ไม่ได้ (วัดได้ 5-10 นาที 25 ก.ย.)
TS_BOX = (820, 760, 145, 40)  # x y w h ของกล่องเวลาในภาพ 965x800
_TS_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})\s+(\d{1,2}):(\d{2})(?::(\d{2}))?")

# ---- OCR (Vision ของ macOS ผ่านโปรแกรม Swift เล็กๆ) ----
_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ocr_time.swift")
_ocr_lock = threading.Lock()
_ocr_state = {"bin": None, "failed": False}


def ensure_ocr(bin_dir):
    """compile ocr_time.swift ครั้งแรก (~40 วิ) -- เรียกจาก thread แยกตอน start
    ไม่มี swiftc (cloud/linux) = ใช้ FALLBACK ตลอด ไม่พัง"""
    path = os.path.join(bin_dir, "ocr_time")
    with _ocr_lock:
        try:
            if os.path.exists(path) and os.stat(path).st_mtime >= os.stat(_SRC).st_mtime:
                _ocr_state["bin"] = path
                return path
            os.makedirs(bin_dir, exist_ok=True)
            subprocess.run(["swiftc", "-O", _SRC, "-o", path + ".tmp"], capture_output=True,
                           text=True, timeout=300, check=True)
            os.replace(path + ".tmp", path)
            _ocr_state["bin"] = path
            return path
        except Exception:
            _ocr_state["failed"] = True
            return None


def read_image_time(img_path, fetched_ts):
    """เวลาในภาพ (epoch) หรือ None -- ต้องไม่ใหม่กว่าเวลาดึง และไม่เก่ากว่านั้นเกิน 1 ชม."""
    b = _ocr_state["bin"]
    if not b:
        return None
    try:
        out = subprocess.run([b, img_path] + [str(v) for v in TS_BOX], capture_output=True,
                             text=True, timeout=20).stdout
    except Exception:
        return None
    m = _TS_RE.search(out)
    if not m:
        return None
    y, mo, d, hh, mm, ss = (int(v) if v else 0 for v in m.groups())
    try:
        ts = int(datetime(y, mo, d, hh, mm, ss).timestamp())   # เวลาในภาพเป็นเวลาไทย = local ของเครื่อง
    except ValueError:
        return None
    return ts if fetched_ts - 3600 <= ts <= fetched_ts + 120 else None


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
    """เก็บภาพจาก weather_meta.json หนึ่งเฟรม -- คืน (เก็บใหม่ไหม, เวลาในภาพ, ได้จาก 'ocr'|'fetch')"""
    raw = base64.b64decode(meta.get("img_base64") or b"")
    if not raw:
        return False, None, None
    os.makedirs(folder, exist_ok=True)
    frames = listing(folder)
    if frames:
        try:
            with open(os.path.join(folder, frames[-1][1]), "rb") as f:
                if hashlib.sha1(f.read()).digest() == hashlib.sha1(raw).digest():
                    return False, frames[-1][0], None
        except OSError:
            pass
    fetched = int(meta.get("ts") or time.time())
    ext = EXT.get(meta.get("mime"), "jpg")
    tmp = os.path.join(folder, ".incoming." + ext)
    with open(tmp, "wb") as f:
        f.write(raw)
    ts = read_image_time(tmp, fetched)
    src = "ocr"
    if ts is None:
        ts, src = fetched - FALLBACK_LAG_MIN * 60, "fetch"
    if any(t == ts for t, _ in frames):                # เวลาในภาพซ้ำ = ภาพเดิม (อาจ encode ต่าง)
        os.remove(tmp)
        return False, ts, src
    os.replace(tmp, os.path.join(folder, "{}.{}".format(ts, ext)))
    prune(folder)
    return True, ts, src


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
