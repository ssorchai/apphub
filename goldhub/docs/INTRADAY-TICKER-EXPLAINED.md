# Intraday Ticker — สรุปกลไก (สำหรับสอน session อื่น)

โค้ดจริง: `fetchers/cme_ticker.py` (fetcher) + `widgets/cme-ticker.jsx` (display)
เอกสารนี้อธิบายเฉพาะส่วน **Ticker** = log ของ "flow ที่เข้ามาราย strike" ของ gold 0DTE option

---

## 1. Ticker คืออะไร

แต่ละแถว = "ที่ strike X มี volume เพิ่มขึ้น +N สัญญาในรอบ 5 นาทีที่ผ่านมา"
เฉพาะ event ที่ **N ≥ 10 สัญญา** (`TICKER_MIN_CONTRACTS`) ถึงจะขึ้น ticker

format ที่แสดง: `time / strike / P / C / Δ / oi+intra`
- **time** = เวลาที่ flow เข้า
- **strike** = ราคาใช้สิทธิ์ (สีตามราคา future ปัจจุบัน — ดูข้อ 6)
- **P / C** = สัญญาที่เพิ่มรอบนี้ แยก put (ส้ม) / call (ฟ้า) ฝั่งที่ไม่มีของเข้าเว้นว่าง
  (22 ก.ย. 26 แยกจาก `+n` รวม — ย้ายหน้าที่มาจาก Δ CHANGES ฝั่ง Intraday ของการ์ด P/C
  ที่ถอดออกเพราะซ้ำกัน) **เกณฑ์ ≥10 ยังนับจากยอดรวม P+C**
- **Δ** = delta ของ strike ณ ตอนที่ flow เข้า (แช่ไว้ ไม่อัปเดต)
- **oi+intra** = OI ถือข้ามคืน + intraday volume ที่มีอยู่ก่อน flow ก้อนนี้

---

## 2. flow event คำนวณยังไง (หัวใจ)

**Intraday volume ของ QuikStrike เป็นยอดสะสมทั้งวัน** (เพิ่มอย่างเดียว ไม่ลด)
→ "flow ที่เพิ่ง เข้า" = ยอดสะสมรอบนี้ − ยอดสะสมรอบก่อน (เก็บใน `state["prev"]`)

```python
for k, (p, c) in rows.items():          # p,c = put/call volume สะสม ของ strike k รอบนี้
    base = prev.get(str(k))             # ยอดของ strike k รอบก่อน
    if base is None: continue           # กับดัก 1 (ดูล่าง)
    dp, dc = p - base[0], c - base[1]
    if dp < 0 or dc < 0: continue        # กับดัก 2 (ดูล่าง)
    tot = dp + dc                        # = +n ที่จะโชว์
    if tot <= 0: continue
    # ... สร้าง contrib
```

### กับดัก 2 อย่างที่ **ต้อง skip ไม่ใช่นับเป็น 0** (ไม่งั้นได้ event ปลอมก้อนใหญ่)

QuikStrike ส่ง strike มาเป็น "หน้าต่าง" รอบราคา ไม่ใช่ทุก strike — หน้าต่างนี้เลื่อน/หด
ตามราคาที่วิ่ง (วัดจริง: หน้าต่างหด 22 → 15 strikes ในเย็นเดียว) ทำให้เกิด 2 เคสหลอก:

1. **strike เพิ่งโผล่เข้าหน้าต่าง** (`base is None`) — ไม่มียอดรอบก่อนให้เทียบ
   ถ้าเผลอตั้ง base = 0 จะได้ dp = ยอดสะสมทั้งวัน = event ปลอมมหาศาล
   → รอบแรกที่เห็น strike ใด = **ตั้ง baseline เฉยๆ ไม่สร้าง event**
2. **ยอดลดลง** (`dp < 0`) — เป็นไปไม่ได้ในโลกจริง (สะสมไม่มีลด) = ข้อมูลรีเซ็ต/
   หน้าต่างเลื่อน → **skip เงียบๆ (re-baseline)** ไม่ใช่ event

> threshold 10 พอดีกับขนาด false positive พวกนี้ ถ้าไม่กัน 2 เคสนี้ ticker จะเด้งขยะรัวๆ

---

## 3. Ticker = FIFO ตามจำนวน ไม่ใช่ตามอายุ (บทเรียนที่แก้ทีหลัง)

**ผิดตอนแรก:** ดึง ticker จาก `contribs` ที่ตัดทิ้งของเก่ากว่า 60 นาที (window ของ Most Active)
→ แถวหายด้วย "อายุ" แม้ ticker ยังไม่เต็ม 12 แถว (ผู้ใช้เห็นแถวค่อยๆ หายเอง)

**แก้:** แยก `ticker_log` ออกมา เป็น FIFO ตามจำนวนล้วน
```python
ticker_log += [x for x in new_contribs if x["n"] >= TICKER_MIN_CONTRACTS]
ticker_log = ticker_log[-TICKER_KEEP:]         # เก็บ 50 ล่าสุด (แสดง 12)
ticker = sorted(ticker_log, key=lambda x: -x["ts"])[:TICKER_ROWS]
```
→ แถวเก่าอยู่จนกว่ามีอันใหม่มาดันออก **ไม่หายตามเวลา**
(Most Active ยังใช้ window 60 นาทีแยกต่างหาก — คนละ concept)

---

## 4. enrichment ต่อ event

แต่ละ contrib เก็บค่าเสริมไว้ **ณ เวลาที่ flow เข้า** (ticker = log ของอดีต จึงแช่ค่าไว้):
- `d` (delta), `pt` (p_touch) — จาก Black-76 (ดูข้อ 5)
- `dist` = strike − F (ห่างจากราคากี่จุด)
- `oi` = open interest ถือข้ามคืน
- `intra` = `p + c − tot` = intraday volume ที่ strike นี้ **ก่อน** flow ก้อนนี้
  (ไม่รวม +n เพราะ +n โชว์แยกคอลัมน์แล้ว กันนับซ้ำ)

---

## 5. Delta / p_touch (Black-76)

แหล่งไม่ให้ delta มา → คำนวณเอง จาก smile (IV รายสไตรค์) + F สด + DTE
```python
T = dte_days / 365.0
d1 = (ln(F/K) + 0.5*σ²*T) / (σ*√T)
delta_otm = N(d1) ถ้า K>F  else 1 − N(d1)   # ฝั่งที่ยัง OTM → ATM ~0.5, ไกล → 0
p_touch  ≈ min(2 × delta_otm, 1)            # "ราคาจะวิ่งไปแตะไหม" (ต่างจาก delta = "จบ ITM ไหม")
```
r ตัดทิ้งได้เพราะ T สั้นมาก (0DTE) → e^(−rT) ≈ 1

---

## 6. สี strike (ในฝั่ง widget)

ระบายตาม **ราคา future ปัจจุบัน** (อ่านสดจาก gold_data.json ทุก refresh 15 วิ) ไม่ใช่ F ตอน log
→ ราคาวิ่งข้าม strike เมื่อไหร่ **แถวที่ค้างอยู่สลับสีเอง**
- เหนือราคา = เขียว pastel `#83e0a3`
- ที่ราคา (±2.6) = ขาว
- ต่ำกว่า = แดง pastel `#ff6b78`

(ใช้ pastel + ไม่ใช้ ฟ้า/เหลือง เพราะสองสีนั้นชนกับ convention PUT/CALL ของผู้ใช้)

---

## 7. แหล่งข้อมูล + จังหวะ

- **fetch**: GET หน้า QuikStrike + postback เลือก series ใกล้หมดสุด = **2 requests** ต่อรอบ
  (หน้าเดียวได้ครบ: ATMVol, put/call รายสไตรค์, smile, F, DTE)
- **cron ทุก 5 นาที** — ATMVol ของ QuikStrike อัปเดตจริงทุก ~5 นาทีเป๊ะ (วัดแล้ว) ดึงถี่กว่าไร้ประโยชน์
  ข้อจำกัดที่ยอมรับ: เห็นแค่ผลรวม 5 นาที **แยกไม่ออกว่า block เดียว 200 ไม้ หรือซอย 20 ไม้**
- **F มาจาก gold_data.json** (gold_fetcher เขียนทุก ~5 วิ) ไม่ใช้ FuturePrice ของ QuikStrike
  ที่เก่า/ค้าง (วัดแล้วเพี้ยน −13 ถึง +8 จุด) — F ผิด delta เพี้ยนแรงตอนใกล้ expire
- **OI ดึงชั่วโมงละครั้ง** (cache) — CME publish OI วันละครั้ง (วัด: OI 0/15 strikes ขยับใน 10 นาที)
  OI เป็น "บริบท" ไม่ใช่ตัวสร้าง event

---

## 8. State & lifecycle

- state เก็บใน `/tmp/cme_ticker_state.json` = `{series, prev, contribs, iv_hist, ticker_log}`
  (อยู่ /tmp → หายตอน reboot = ยอมรับได้ สะสมใหม่)
- **series roll = ล้างประวัติทั้งหมด** (`state["series"] != series`) ห้ามเอา flow คนละ series มาต่อกัน
  series 0DTE หมดอายุ **12:30 CT** = ~00:30 เวลาไทย (ใช้ zoneinfo ให้เลื่อนตาม DST เอง)
  — ระวังบั๊กเดิม: เทียบวันที่แบบไร้ timezone จะ roll ตั้งแต่เที่ยงคืน ทิ้งช่วง gamma แรงสุด 30 นาที
- ปุ่ม Reset ใน widget (กดค้าง 5 วิ) = `rm state.json` แล้วรัน fetcher ใหม่ → ตั้ง baseline ใหม่

---

## 9. บทเรียนรวบยอด (ให้ session อื่นจำ)

1. **ยอดสะสม → ต้อง diff กับ snapshot รอบก่อน** ถึงได้ "flow ที่เพิ่งเข้า"
2. **หน้าต่างข้อมูลไม่คงที่** → strike ใหม่/ยอดลด ต้อง skip ไม่ใช่นับเป็น event
3. **ticker = FIFO ตามจำนวน** ไม่ใช่ตามเวลา (คนละอันกับ sliding-window ของ Most Active)
4. **ค่าที่ต้องสด(F) แยกจากค่าที่แช่ได้(delta ตอน log)** — F ใช้ทาสีย้อนหลังได้ delta ไม่ต้อง
5. **แหล่งอัปเดตเป็นรอบ ไม่ใช่ realtime** → ดึงตามคาบจริงของมัน อย่าดึงถี่เกิน
