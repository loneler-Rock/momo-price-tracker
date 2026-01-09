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
    print("🤖 啟動 GitHub Actions 專用瀏覽器 (Momo + PChome)...")
    chrome_options = Options()
    chrome_options.add_argument('--headless') 
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--window-size=1920,1080') 
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver

def extract_price(text):
    if not text: return 0
    # 移除千分位逗號和非數字字符 (保留小數點)
    clean = re.sub(r'[^\d.]', '', text)
    try: return float(clean)
    except: return 0

def parse_momo(driver):
    """ 解析 Momo 頁面 """
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

def parse_pchome(driver):
    """ 解析 PChome 頁面 (新增功能) """
    try:
        title = driver.title
        try:
            # PChome 的標題通常在 h1 或 meta tag
            elem_title = driver.find_element("css selector", "h1.o-prodName, .prod_name, #ProName")
            if elem_title: title = elem_title.text
        except: pass

        price = 0
        try:
            # PChome 24h 的價格選擇器
            # 1. 新版介面 (.o-prodPrice__price)
            # 2. 舊版介面 (#PriceTotal)
            # 3. 通用備份 (.price)
            selectors = [
                ".o-prodPrice__price", 
                "#PriceTotal", 
                ".web_price .price",
                ".price_box .price"
            ]
            for sel in selectors:
                elems = driver.find_elements("css selector", sel)
                for el in elems:
                    # PChome 有時候會顯示 "折後價"，要優先抓這個
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
    print("🚀 開始執行全自動比價任務 (Momo + PChome)...")
    
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

        if not all_products:
            print("📭 資料庫無監控商品")
        else:
            print(f"📋 準備檢查 {len(all_products)} 筆商品...\n")
            
            for p in all_products:
                url = p['original_url']
                platform_name = "未知"
                
                # 簡單的網址判斷邏輯
                if "momo" in url: platform_name = "Momo"
                elif "pchome" in url: platform_name = "PChome"
                else: 
                    print(f"⚠️ 跳過不支援的連結: {url[:20]}...")
                    continue

                print(f"🔎 [{platform_name}] {p.get('product_name', '未知')[:10]}...", end=" ")
                
                try:
                    driver.get(url)
                    time.sleep(3) # PChome 載入稍微久一點，給它 3 秒
                    
                    name = "未知"
                    new_price = 0
                    
                    if platform_name == "Momo":
                        name, new_price = parse_momo(driver)
                    elif platform_name == "PChome":
                        name, new_price = parse_pchome(driver)
                    
                    if new_price > 0:
                        print(f"[${new_price}] ✅")
                        
                        # 更新資料庫
                        db.table("products").update({
                            "current_price": new_price,
                            "product_name": name,
                            "original_url": driver.current_url 
                        }).eq("id", p['id']).execute()
                        
                        old_price = p.get('current_price') or 0
                        target_price = p.get('target_price') or 0
                        
                        # 通知邏輯 (降價 或 達標)
                        if (old_price > 0 and new_price < old_price):
                            msg = f"📉【{platform_name}降價】\n{name}\n\n${old_price} ➡️ ${new_price}\n(省 ${old_price - new_price})"
                            send_notification(p['user_id'], msg)
                        elif (old_price != new_price and target_price > 0 and new_price <= target_price):
                            msg = f"🎯【{platform_name}達標】\n{name}\n\n目前：${new_price}"
                            send_notification(p['user_id'], msg)
                    else:
                        print(f"[抓取失敗] ❌")
                except Exception as e:
                    print(f"[Err] ❌")
    finally:
        driver.quit()
        print("\n🏁 任務結束")

if __name__ == "__main__":
    run_updater()
