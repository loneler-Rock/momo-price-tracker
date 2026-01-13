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
    將短網址還原為長網址
    """
    try:
        # 模擬瀏覽器 User Agent，避免被 Google 擋
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        response = requests.get(short_url, headers=headers, allow_redirects=True, timeout=10)
        return response.url
    except Exception as e:
        print(f"❌ 網址還原失敗: {e}")
        return short_url

def extract_name_from_url(url):
    """
    [V2.0 新功能] 從 Google Maps 網址中挖掘店名
    網址格式通常為: /maps/place/店名/@...
    """
    try:
        # 尋找 /place/ 後面的文字，直到遇到 / 為止
        match = re.search(r'/place/([^/]+)/', url)
        if match:
            # 網址通常是編碼過的 (例如 %E5%8F%B0...)，需要 unquote 解碼成中文
            raw_name = match.group(1)
            decoded_name = unquote(raw_name)
            # 把 + 號換成空白 (Google 用 + 代表空白)
            clean_name = decoded_name.replace('+', ' ')
            return clean_name
    except Exception as e:
        print(f"⚠️ 解析店名失敗: {e}")
    
    return "未命名地點" # 如果真的找不到，才用這個

def extract_coordinates(url):
    """
    從網址解析經緯度
    """
    # Pattern 1: @lat,long
    match = re.search(r'@(-?\d+\.\d+),(-?\d+\.\d+)', url)
    if match:
        return float(match.group(1)), float(match.group(2))
        
    # Pattern 2: ?q=lat,long
    match = re.search(r'q=(-?\d+\.\d+),(-?\d+\.\d+)', url)
    if match:
        return float(match.group(1)), float(match.group(2))
        
    # Pattern 3: !3d...!4d...
    match = re.search(r'!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)', url)
    if match:
        return float(match.group(1)), float(match.group(2))

    return None, None

def save_location(supabase, user_id, url):
    print(f"🔍 正在解析: {url} ...")
    
    # 1. 還原網址
    final_url = expand_url(url)
    print(f"➡️ 最終網址: {final_url[:100]}...") 
    
    # 2. [新功能] 解析店名
    shop_name = extract_name_from_url(final_url)
    print(f"🏷️ 偵測到店名: {shop_name}")
    
    # 3. 解析座標
    lat, lng = extract_coordinates(final_url)
    
    if lat and lng:
        print(f"✅ 抓到座標: 緯度 {lat}, 經度 {lng}")
        
        # 4. 寫入資料庫
        data = {
            "user_id": user_id,
            "original_url": url,
            "name": shop_name,  # 這裡現在會填入真正的店名了！
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
    print("🚀 IG 美食地圖解析器 V2.0 (含店名解析) 啟動...")
    
    # 接收外部參數
    if len(sys.argv) > 2:
        target_url = sys.argv[1]
        user_id = sys.argv[2]
        
        print(f"收到指令！\n使用者: {user_id}\n網址: {target_url}")
        
        try:
            supabase = init_supabase()
            save_location(supabase, user_id, target_url)
        except Exception as e:
            print(f"❌ 執行發生錯誤: {e}")
            sys.exit(1) 
            
    else:
        print("⚠️ 無法執行：缺少參數。請透過 GitHub Actions 執行。")

if __name__ == "__main__":
    main()
