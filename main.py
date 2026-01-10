import os
import time
import requests
from supabase import create_client, Client
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from datetime import datetime, timezone

# --- 環境變數 ---
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
MAKE_WEBHOOK_URL = os.environ.get("MAKE_WEBHOOK_URL")

# --- 初始化 Supabase ---
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def setup_driver():
    """設定 Chrome Headless"""
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36")
    return webdriver.Chrome(options=chrome_options)

def parse_momo_price(driver, url):
    """Momo 爬蟲核心"""
    try:
        driver.get(url)
        time.sleep(3)
        
        # 嘗試抓取價格 (支援多種版型)
        selectors = [".prdPrice .special", "#pKwdPrice", "ul.price li.special span"]
        price_text = None
        
        for selector in selectors:
            try:
                el = driver.find_element(By.CSS_SELECTOR, selector)
                if el and el.text.strip():
                    price_text = el.text.strip()
                    break
            except:
                continue
        
        if not price_text: return None
        return int("".join(filter(str.isdigit, price_text)))
    except:
        return None

def notify_make(item_name, price, target_price, url, msg_type):
    """發送通知到 Make"""
    if not MAKE_WEBHOOK_URL: return
    payload = {
        "type": msg_type,
        "product_name": item_name,
        "current_price": price,
        "target_price": target_price,
        "url": url,
        "timestamp": datetime.now().isoformat()
    }
    try:
        requests.post(MAKE_WEBHOOK_URL, json=payload)
        print(f"✅ Webhook sent: {msg_type}")
    except Exception as e:
        print(f"❌ Webhook failed: {e}")

def main():
    print("🚀 Second Brain V9.0 Started...")
    
    # 1. 讀取新資料表 tracked_items
    try:
        data = supabase.table("tracked_items").select("*").eq("is_active", True).execute()
        items = data.data
    except Exception as e:
        print(f"❌ DB Error: {e}")
        return

    if not items:
        print("📭 No active items found.")
        return

    driver = setup_driver()

    for item in items:
        print(f"🔍 Checking: {item['product_name']}")
        current_price = parse_momo_price(driver, item['product_url'])
        
        if current_price:
            print(f"   💰 Price: {current_price}")
            
            # 更新目前價格
            supabase.table("tracked_items").update({
                "current_price": current_price,
                "last_checked_at": datetime.now(timezone.utc).isoformat()
            }).eq("id", item['id']).execute()

            # 寫入歷史紀錄
            supabase.table("price_history").insert({
                "item_id": item['id'],
                "price": current_price
            }).execute()

            # 判斷通知
            last_price = item.get('current_price')
            target = item.get('target_price', 0) or 0
            
            if last_price and current_price < last_price:
                notify_make(item['product_name'], current_price, target, item['product_url'], "降價通知")
            elif target > 0 and current_price <= target:
                notify_make(item['product_name'], current_price, target, item['product_url'], "達標通知")
        else:
            print("   ⚠️ Failed to parse price")

    driver.quit()
    print("✅ Done")

if __name__ == "__main__":
    main()
