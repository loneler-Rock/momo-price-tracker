print("👋 哈囉！我是程式，我真的有被執行到！")
import os
import sys
import re
import requests
import time
from urllib.parse import unquote

# 設定路徑以引用 utils (確保能找到上一層的 supabase_client)
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from utils.supabase_client import init_supabase

def expand_url(short_url):
    """
    將短網址 (如 http://googleusercontent.com/...) 還原為長網址
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
        print("⚠️ 未偵測到外部參數，進入「本地測試模式」...")
        print("請使用 GitHub Actions 輸入參數來測試真實情境。")

if __name__ == "__main__":
    main()

