import asyncio
import json
import time
import os
from datetime import datetime
from playwright.async_api import async_playwright

# กำหนด Path สำหรับ JSON
JSON_PATH = os.path.expanduser("/tmp/gold_data.json")

async def apply_stealth_manually(page):
    await page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
    """)

def get_market_zone():
    hour = datetime.now().hour
    if 7 <= hour < 14: return "ASIA Session"
    if 14 <= hour < 19: return "LONDON Session"
    if 19 <= hour < 23: return "GOLDEN TIME (LDN+NY)"
    if 23 <= hour or hour < 5: return "NEW YORK Session"
    return "Quiet Session"

async def scrape_data_fast(page):
    """ดึงข้อมูลทุกอย่างรวมถึงชื่อ Series เต็มๆ จาก h1"""
    return await page.evaluate("""() => {
        const get = (sel) => document.querySelector(sel)?.innerText || '0';
        return {
            // ดึงชื่อเต็ม เช่น "Gold Futures (GCM6)"
            name: document.querySelector('h1')?.innerText?.trim() || 'Unknown',
            price: get('[data-test="instrument-price-last"]'),
            open: get('[data-test="open"]'),
            change: get('[data-test="instrument-price-change"]'),
            percent: get('[data-test="instrument-price-change-percent"]'),
            time: get('[data-test="trading-time-label"]')
        };
    }""")

async def main():
    async with async_playwright() as p:
        print(f"🚀 Engine Started (Series tracking enabled)")
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) ...")

        p_future = await context.new_page()
        p_cfd = await context.new_page()
        await apply_stealth_manually(p_future)
        await apply_stealth_manually(p_cfd)

        print("🌐 Connecting to Futures & CFD...")
        await asyncio.gather(
            p_future.goto("https://www.investing.com/commodities/gold", wait_until="commit"),
            p_cfd.goto("https://www.investing.com/currencies/xau-usd", wait_until="commit")
        )

        # รอให้ Selector พร้อม
        await asyncio.gather(
            p_future.wait_for_selector('[data-test="instrument-price-last"]'),
            p_cfd.wait_for_selector('[data-test="instrument-price-last"]')
        )

        print("✅ Live Monitoring Active...")
        start_time = time.time()
        
        while time.time() - start_time < 298: # ทำงาน 5 นาที
            # Feature 4: Concurrent request ดึงพร้อมกันทั้ง 2 หน้า
            f_res, c_res = await asyncio.gather(scrape_data_fast(p_future), scrape_data_fast(p_cfd))

            try:
                f_price = float(f_res['price'].replace(',', ''))
                c_price = float(c_res['price'].replace(',', ''))
                diff = round(f_price - c_price, 2)

                output = {
                    "future": {**f_res, "price": f_price, "open": float(f_res['open'].replace(',', ''))},
                    "cfd": {**c_res, "price": c_price, "open": float(c_res['open'].replace(',', ''))},
                    "diff": diff,
                    "zone": get_market_zone(),
                    "system_time": datetime.now().strftime("%H:%M:%S")
                }

                # Atomic write ลงไฟล์ JSON
                temp_path = JSON_PATH + ".tmp"
                with open(temp_path, "w") as f:
                    json.dump(output, f)
                os.replace(temp_path, JSON_PATH)

                # แสดงสถานะบน Terminal (Optional)
                print(f"[{output['system_time']}] {f_res['name']}: {f_price:.2f} {c_res['name']}: {c_price:.2f} | Diff: {diff}", end='\r')
                
            except Exception:
                pass 
            
            await asyncio.sleep(3) # หน่วง 3 วินาทีแล้วค่อยไปอ่านใหม่

        await browser.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Stopped.")