
import os
import time
import requests
import urllib.parse
import re
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from supabase import create_client

# ==========================================
# 系統設定區 (請確認 Key 與 URL 是否正確)
# ==========================================
SUPABASE_URL = "https://eovkimfqgoggxbkvkjxg.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImVvdmtpbWZxZ29nZ3hia3ZranhnIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Njc3NjI1NzksImV4cCI6MjA4MzMzODU3OX0.akX_HaZQwRh53KJ-ULuc5Syf2ypjhaYOg7DfWhYs8EY"
MAKE_WEBHOOK_URL = "https://hook.eu1.make.com/iqfx87wola6yp35c3ly7mqvugycxwlfx"

# 通路王 (iChannels) 會員 ID (Momo 與 PChome 通用)
ICHANNELS_ID = "af000148084"

# ==========================================
# 核心功能函式
# ==========================================

def get_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

def setup_driver():
    chrome_options = Options()
    chrome_options.add_argument('--headless') 
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36")
    
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=chrome_options)

def generate_affiliate_link(original_url):
    """
    將原始商品網址轉換為通路王 (iChannels) 分潤連結
    支援平台：Momo, PChome
    """
    # 判斷是否為支援的電商平台
    if "momoshop.com.tw" in original_url or "pchome.com.tw" in original_url:
        # 進行 URL 編碼
        encoded_url = urllib.parse.quote(original_url)
        # 組合通路王通用導購連結 (Momo/PChome 通用同一套邏輯)
        return f"http://www.ichannels.com.tw/bbs.php?member={ICHANNELS_ID}&url={encoded_url}"
    
    # 若非上述平台，回傳原網址
    return original_url

def update_price_history(supabase, product_id, price):
    """
    1. 寫入價格歷史表
    2. 判斷是否為歷史新低
    """
    # A. 寫入歷史紀錄
    try:
        supabase.table("price_history").insert({
            "product_id": product_id,
            "price": price
        }).execute()
    except Exception as e:
        print(f"寫入歷史價格失敗: {e}")

    # B. 檢查是否為歷史低價
    try:
        data = supabase.table("products").select("lowest_price").eq("id", product_id).execute()
        current_lowest = data.data[0].get("lowest_price")
        
        # 如果沒有舊紀錄，或者 現在價格 < 舊紀錄
        if current_lowest is None or price < float(current_lowest):
            # 更新 Products 表的最低價欄位
            supabase.table("products").update({"lowest_price": price}).eq("id", product_id).execute()
            return True # 是歷史新低
    except Exception as e:
        print(f"檢查歷史低價失敗: {e}")
        
    return False # 不是歷史新低

def parse_momo(driver, url):
    driver.get(url)
    time.sleep(3)
    try:
        title = driver.title.split("-")[0].strip()
        price_text = ""
        try:
            price_text = driver.find_element("css selector", ".prdPrice").text
        except:
            try:
                price_text = driver.find_element("css selector", "#pKwdPrice").text
            except:
                price_text = "0"
        
        price = int(re.sub(r"[^\d]", "", price_text))
        return title, price
    except Exception as e:
        print(f"Momo 解析失敗: {e}")
        return "Unknown Product", 99999999

def parse_pchome(driver, url):
    driver.get(url)
    time.sleep(3)
    try:
        title = driver.title.split("-")[0].strip()
        price_text = ""
        try:
            # 新版頁面 Class
            price_text = driver.find_element("css selector", ".o-prodPrice__price").text
        except:
            try:
                # 舊版頁面 ID
                price_text = driver.find_element("css selector", "#PriceTotal").text
            except:
                price_text = "0"
                
        price = int(re.sub(r"[^\d]", "", price_text))
        return title, price
    except Exception as e:
        print(f"PChome 解析失敗: {e}")
        return "Unknown Product", 99999999

def send_notification(product_name, price, url, user_id, is_lowest_price):
    """
    組合訊息並發送給 Make
    """
    # 產生分潤連結 (這裡會自動把 PChome 網址也轉成賺錢連結)
    affiliate_url = generate_affiliate_link(url)
    
    # 訊息標題
    status_tag = "🔥 歷史新低價！" if is_lowest_price else "📉 降價通知"
    
    message = (
        f"{status_tag}\n"
        f"商品：{product_name}\n"
        f"金額：${price:,}\n"
        f"------------------\n"
        f"點此購買 (已追蹤)：\n{affiliate_url}"
    )
    
    payload = {
        "message": message,
        "to": user_id
    }
    
    try:
        requests.post(MAKE_WEBHOOK_URL, json=payload)
        print(f"通知已發送: {product_name}")
    except Exception as e:
        print(f"Webhook 發送失敗: {e}")

def run_updater():
    print("啟動比價爬蟲 V10.1 (雙平台獲利版)...")
    supabase = get_supabase()
    driver = setup_driver()
    
    # 1. 取得所有啟用中的商品
    response = supabase.table("products").select("*").eq("is_active", True).execute()
    products = response.data
    
    print(f"共發現 {len(products)} 個監控商品")

    for p in products:
        try:
            original_url = p['original_url']
            target_price = p.get('target_price', 0)
            last_price = p.get('current_price', 99999999)
            
            print(f"正在檢查: {p['product_name']}...")
            
            # 2. 判斷平台並爬取
            current_price = 99999999
            title = p['product_name']
            
            if "momoshop" in original_url:
                title, current_price = parse_momo(driver, original_url)
            elif "pchome" in original_url:
                title, current_price = parse_pchome(driver, original_url)
            
            if current_price == 99999999:
                print("略過: 價格解析失敗")
                continue

            # 3. 處理價格歷史
            is_lowest = update_price_history(supabase, p['id'], current_price)
            
            # 4. 更新資料庫
            supabase.table("products").update({
                "current_price": current_price, 
                "product_name": title 
            }).eq("id", p['id']).execute()

            # 5. 觸發通知邏輯
            should_notify = False
            
            if target_price and current_price <= target_price:
                should_notify = True
            elif current_price < last_price:
                should_notify = True
            elif is_lowest:
                should_notify = True
                
            if should_notify:
                print(f"==> 觸發通知！現價 ${current_price}")
                send_notification(title, current_price, original_url, p['user_id'], is_lowest)
            else:
                print(f"未達通知標準 (現價 ${current_price})")
                
            time.sleep(2)
            
        except Exception as e:
            print(f"處理商品 ID {p.get('id')} 時發生錯誤: {e}")
            continue
            
    driver.quit()
    print("所有排程執行完畢。")

if __name__ == "__main__":
    run_updater()
