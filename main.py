import os
import time
import re
import requests 
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from supabase import create_client, Client

# ================= ⚙️ 設定區 (已自動填入) =================
SUPABASE_URL = "https://eovkimfqgoggxbkvkjxg.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImVvdmtpbWZxZ29nZ3hia3ZranhnIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Njc3NjI1NzksImV4cCI6MjA4MzMzODU3OX0.akX_HaZQwRh53KJ-ULuc5Syf2ypjhaYOg7DfWhYs8EY"
MAKE_WEBHOOK_URL = "https://hook.eu1.make.com/iqfx87wola6yp35c3ly7mqvugycxwlfx"
# ============================================================

def setup_driver():
    print("🤖 啟動 GitHub Actions 專用瀏覽器...")
    chrome_options = Options()
    chrome_options.add_argument('--headless') 
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--window-size=1920,1080') # 模擬大螢幕避免跑版
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    # 自動安裝對應版本的驅動
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver

def extract_price(text):
    if not text: return 0
    clean = re.sub(r'[^\d.]', '', text)
    try: return float(clean)
    except: return 0

def parse_momo(driver):
    try:
        title = driver.title
        try:
            meta_title = driver.find_element("css selector", "meta[property='og:title']")
            if meta_title: title = meta_title.get_attribute("content")
        except: pass

        price = 0
        try:
            selectors = [
                ".prdPrice .special", ".prdPrice .price", "#pKwdPrice", 
                "ul.price li.special span", ".amount", "li.special span"
            ]
            for sel in selectors:
                elems = driver.find_elements("css selector", sel)
                for el in elems:
                    p = extract_price(el.text)
                    if p > 10: 
                        price = p
                        break
                if price > 0: break
        except: pass
        return title, int(price)
    except:
        return None, 0

def send_notification(user_id, message):
    if "hook" not in MAKE_WEBHOOK_URL: return
    try:
        requests.post(MAKE_WEBHOOK_URL, json={"message": message, "to": user_id})
        print(f"   🔔 通知已發送")
    except: pass

def run_updater():
    print("🚀 開始執行全自動比價任務...")
    
    try:
        db = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        print(f"❌ DB Error: {e}")
        return

    try:
        driver = setup_driver()
    except Exception as e:
        print(f"❌ Driver Error: {e}")
        return
    
    try:
        try:
            # 撈取所有 Active 的商品
            all_products = db.table("products").select("*").eq("is_active", True).execute().data
        except:
            all_products = []

        momo_products = [p for p in all_products if "momo" in p['original_url']]

        if not momo_products:
            print("📭 無 Momo 商品")
        else:
            print(f"📋 檢查 {len(momo_products)} 筆商品...\n")
            
            for p in momo_products:
                print(f"🔎 {p.get('product_name', '未知')[:10]}...", end=" ")
                try:
                    driver.get(p['original_url'])
                    time.sleep(2)
                    name, new_price = parse_momo(driver)
                    
                    if new_price > 0:
                        print(f"[${new_price}] ✅")
                        
                        db.table("products").update({
                            "current_price": new_price,
                            "product_name": name,
                            "original_url": driver.current_url 
                        }).eq("id", p['id']).execute()
                        
                        old_price = p.get('current_price') or 0
                        target_price = p.get('target_price') or 0
                        
                        if (old_price > 0 and new_price < old_price):
                            msg = f"📉【Momo降價】\n{name}\n\n${old_price} ➡️ ${new_price}\n(省 ${old_price - new_price})"
                            send_notification(p['user_id'], msg)
                        elif (old_price != new_price and target_price > 0 and new_price <= target_price):
                            msg = f"🎯【Momo達標】\n{name}\n\n目前：${new_price}"
                            send_notification(p['user_id'], msg)
                    else:
                        print(f"[失敗] ❌")
                except Exception as e:
                    print(f"[Err] ❌")
    finally:
        driver.quit()
        print("\n🏁 任務結束")

if __name__ == "__main__":
    run_updater()
