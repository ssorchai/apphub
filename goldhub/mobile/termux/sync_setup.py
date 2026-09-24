#!/usr/bin/env python3
"""ฝัง cme_gold_termux.py ลง setup_cme_termux.sh (ตัวที่เอาไปติดตั้งบนมือถือจริง)

ไฟล์ .sh มีโค้ด python ทั้งไฟล์อยู่ข้างในเป็น heredoc -- แก้ .py อย่างเดียวไม่ถึงมือถือ
(24 ก.ย. 26 เคยพลาดมาแล้ว) รันตัวนี้ทุกครั้งหลังแก้ .py:

    python3 sync_setup.py           # ฝังลง .sh
    python3 sync_setup.py --check   # เช็คว่าตรงกันไหม (คืน exit 1 ถ้าไม่ตรง)
"""
import sys
import os

HERE = os.path.dirname(os.path.abspath(__file__))
PY_FILE = os.path.join(HERE, "cme_gold_termux.py")
SH_FILE = os.path.join(HERE, "setup_cme_termux.sh")
START = "cat > ~/cme-gold/cme_gold_termux.py << 'PYEOF'\n"
END = "PYEOF\n"


def split_sh(sh):
    i = sh.index(START) + len(START)
    j = sh.index("\n" + END, i) + 1
    return sh[:i], sh[i:j], sh[j:]


def main():
    py = open(PY_FILE).read()
    sh = open(SH_FILE).read()
    head, embedded, tail = split_sh(sh)
    if "\nPYEOF\n" in py:
        sys.exit("cme_gold_termux.py มีบรรทัด PYEOF -- จะทำให้ heredoc ขาดกลางคัน")
    if "--check" in sys.argv:
        same = embedded == py
        print("ตรงกัน" if same else "ไม่ตรง: .sh มีโค้ดเก่าอยู่ -- รัน sync_setup.py")
        sys.exit(0 if same else 1)
    if embedded == py:
        print("ตรงกันอยู่แล้ว ไม่ต้องแก้")
        return
    tmp = SH_FILE + ".tmp"
    with open(tmp, "w") as f:
        f.write(head + py + tail)
    os.replace(tmp, SH_FILE)
    print("ฝัง %d บรรทัดลง %s แล้ว" % (py.count("\n"), os.path.basename(SH_FILE)))


if __name__ == "__main__":
    main()
