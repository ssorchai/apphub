# research — backtest ของกรอบ SD (ก.ค. 2026)

ที่มาของกฎเทรดที่ใช้อยู่จริง (fade ที่ 2σ/3σ, SL 25$) ย้ายมาจาก `claude_code/cme_scraping`
ตอนรวม repo 25 ก.ย. 26 — **ไม่ใช่โค้ดที่รันในระบบ** แต่เป็นตัวที่ทำให้ตัดสินใจแบบนี้

| ไฟล์ | คืออะไร |
|---|---|
| `backtest_sd.py` | ตัว backtest เอง สเปกอยู่ใน docstring หัวไฟล์ |
| `backtest_touches.csv` | ผลรุ่น SL 12.5$ (รุ่นแรก) |
| `backtest_touches_sl25.csv` | ผลรุ่น SL 25$ (รุ่นที่สรุปว่าดีกว่า) |

## ข้อมูลที่ใช้

ประวัติ 5.5 เดือน (113 วัน) จาก repo ของคนอื่นที่ mirror ข้อมูล CME ไว้:
`github.com/pageth/Vol2VolData` — ต้อง clone มาก่อนแล้วชี้ path ให้สคริปต์

```bash
git clone --filter=blob:limit=20k https://github.com/pageth/Vol2VolData v2v_full
python3 backtest_sd.py /path/to/v2v_full --csv backtest_touches.csv
```

ต้องใช้ `/usr/bin/git` (git ของ MacPorts 2.15 partial clone ไม่รอด) clone ราว 2 นาที
โฟลเดอร์ที่ clone ไม่ได้เก็บไว้ที่นี่ — re-clone เมื่อจะรันใหม่

## ข้อสรุปที่ได้ (สำคัญกว่าตัวโค้ด)

- **SL 12.5$ แคบเกินไป** — median overshoot หลังแตะเส้นอยู่ที่ 20–44$ คือโดนลากเลย SL
  เป็นปกติแล้วราคาถึงจะกลับ
- **SL 25$ พลิกผล** — กลุ่มที่แตะเส้นช่วง frozen hours (05:00–17:00 น. ที่ CME แช่ vol ไว้)
  กลายเป็นกลุ่มที่ดีที่สุด ชนะ 57% ที่ 1:1
- **ฝั่ง put (fade ขาลง = long) ดีกว่าฝั่ง call** (fade ขาขึ้น = short)
- **DTE 0.6 แย่กว่า 0.8125 ทุกกรณี** — กรอบแคบเกิน
- 3σ ฝั่งล่างดีที่สุด แต่ n=8 เท่านั้น ยังสรุปไม่ได้จริง
