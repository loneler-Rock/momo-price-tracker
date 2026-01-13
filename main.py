# 檔案位置: ig_map/main.py
import os
import sys
import re
import requests
import time
from urllib.parse import unquote

# 設定路徑以引用 utils
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from utils.supabase_client import init_supabase

def expand_url(short_url):
    """
    將短網址 (如 https://maps.app.goo.gl/...) 還原為長網址
    """
    try:
        # allow_redirects=True 會自動幫我們跳轉到最終網址
        response = requests.get(short_url, allow_redirects=True, timeout=10)
        return response.url
    except Exception as e:
        print(f"❌ 網址還原失敗: {e}")
        return short_url

def extract_coordinates(url):
    """
    核心邏輯：使用 Regex 從 Google Maps 網址中暴力解析經緯度
    不使用 Google API (省錢策略)
    """
    # 網址通常包含 @緯度,經度,縮放
    # 例如: https://www.google.com/maps/place/.../@25.0339639,121.5644722,17z/...
    
    # Pattern 1: 尋找 @lat,long
    match = re.search(r'@(-?\d+\.\d+),(-?\d+\.\d+)', url)
    if match:
        return float(match.group(1)), float(match.group(2))
        
    # Pattern 2: 尋找 query param ?q=lat,long
    match = re.search(r'q=(-?\d+\.\d+),(-?\d+\.\d+)', url)
    if match:
        return float(match.group(1)), float(match.group(2))
        
    # Pattern 3: 尋找 !3dlat!4dlong (Google Maps 內嵌代碼格式)
    match = re.search(r'!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)', url)
    if match:
        return float(match.group(1)), float(match.group(2))

    return None, None

def save_location(supabase, user_id, url, name="未命名地點"):
    """
    將解析結果存入 Supabase
    """
    print(f"🔍 正在解析: {url} ...")
    
    # 1. 如果是短網址，先還原
    final_url = expand_url(url)
    print(f"➡️ 最終網址: {final_url[:60]}...") # 只印前60字避免太長
    
    # 2. 解析座標
    lat, lng = extract_coordinates(final_url)
    
    if lat and lng:
        print(f"✅ 抓到座標: 緯度 {lat}, 經度 {lng}")
        
        # 3. 寫入資料庫
        # 注意: 我們不需要手動寫 geom，SQL Trigger 會自動幫我們算
        data = {
            "user_id": user_id,
            "original_url": url,
            "name": name,
            "latitude": lat,
            "longitude": lng
        }
        
        try:
            supabase.table("ig_food_map").insert(data).execute()
            print("🎉 成功儲存至 Supabase!")
            return True
        except Exception as e:
            print(f"❌ 資料庫寫入失敗: {e}")
    else:
        print("⚠️ 無法解析出座標，可能是網址格式不支援。")
    
    return False

def main():
    print("🚀 IG 美食地圖解析器啟動...")
    supabase = init_supabase()
    
    # ==========================================
    # 模擬測試區 (因為我們還沒接 Webhook)
    # ==========================================
    # 這裡我們放幾個假的測試資料，模擬使用者從 LINE 傳來的連結
    
    test_inputs = [
        # 測試 1: Google Maps 短網址 (假設這是 User 傳的)
        {
            "user_id": "TEST_USER_001",
            "url": "https://maps.app.goo.gl/KkX9Jz8b9Jz8b9Jz8" # 這是範例，如果失效是正常的
        },
        # 測試 2: 已知的長網址 (台北 101)
        {
            "user_id": "TEST_USER_001", 
            "url": "https://www.google.com/maps/place/Taipei+101/@25.0339639,121.5644722,17z/data=!3m1!4b1!4m6!3m5!1s0x3442abb6da9c9e1f:0x1206a061c55743f4!8m2!3d25.0339639!4d121.5644722!16s%2Fm%2F02_6w?entry=ttu"
        }
    ]

    # 如果有從 command line 傳入參數 (未來給 GitHub Actions 用)
    # 這裡可以擴充接收 sys.argv
    
    for item in test_inputs:
        print(f"\n--- 處理任務 ---")
        # 注意: 上面的短網址範例是假的，可能會解析失敗，我們主要測下面那個長網址
        save_location(supabase, item["user_id"], item["url"])

if __name__ == "__main__":
    main()