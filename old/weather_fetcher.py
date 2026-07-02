import asyncio
import json
import os
import requests
import base64
from datetime import datetime
from playwright.async_api import async_playwright

# ใช้ Path ไหนก็ได้ที่คุณถนัด (แนะนำที่เดิมที่คุณใช้)
DATA_DIR = os.path.expanduser("/tmp/")
IMAGE_PATH = os.path.join(DATA_DIR, "radar.png")
JSON_PATH = os.path.join(DATA_DIR, "weather_meta.json")

async def apply_stealth_manually(page):
    await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

async def main():
    if not os.path.exists(DATA_DIR): os.makedirs(DATA_DIR)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        await apply_stealth_manually(page)

        try:
            print("Fetching Radar...")
            await page.goto("https://weather.tmd.go.th/bma_nck.php", wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(5000)
            img_url = await page.evaluate("""() => {
                // ค้นหาภาพในหน้าเว็บทั้งหมดที่ขยายความกว้างเต็มจอ หรือมีคีย์เวิร์ดตรวจจับฝน
                const images = Array.from(document.querySelectorAll('img'));
                
                // ค้นหาภาพที่มี src ตรงเป้าหมาย หรือหากหาไม่เจอให้เอาภาพแรกที่เป็นตัวแผนที่มา
                const radarImg = images.find(img => img.src.includes('radar') || img.src.includes('NCK') || img.src.includes('bma'));
                
                if (radarImg) return radarImg.src;
                
                // Fallback: ถ้าหาไม่เจอจริงๆ ให้ดึงภาพหลักชิ้นแรกที่มีขนาดใหญ่ของหน้านั้นมา
                return images.length > 0 ? images[0].src : null;
            }""")
            
            # 1. ดาวน์โหลดภาพ
            img_data = requests.get(img_url).content
            
            # 2. แปลงภาพเป็น Base64 String
            encoded_img = base64.b64encode(img_data).decode('utf-8')
            
            # 3. บันทึกลง JSON (รวมทั้งข้อมูลและตัวภาพ)
            metadata = {
                "last_update": datetime.now().strftime("%H:%M"),
                "source": "BMA Radar (Nong Chok)",
                "img_base64": encoded_img
            }
            with open(JSON_PATH, "w") as f:
                json.dump(metadata, f)
                
            print("✅ Data & Image embedded in JSON successfully.")

        except Exception as e:
            print(f"❌ Error: {e}")
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())