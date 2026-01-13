# 檔案位置: ig_map/main.py
import os
import sys
import re
import requests
from urllib.parse import unquote

# 設定路徑以引用 utils
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from utils.supabase_client import init_supabase

def expand_url(short_url):
    """
    將短網址還原為長網址
    """
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        response = requests.get(short_url, headers=headers, allow_redirects=True, timeout=10)
        return response.url
    except Exception as e:
        print(f"❌ 網址還原失敗: {e}")
        return short_url

def parse_dms(dms_str):
    """
    將度分秒格式 (25°03'56.9"N) 轉換為十進位 (25.0658)
    """
    try:
        # 使用 Regex 拆解 度、分、秒、方向
        parts = re.match(r"(\d+)°(\d+)'([\d.]+)\"([NSEW])", dms_str)
        if parts:
            degrees = float(parts.group(1))
            minutes = float(parts.group(2))
            seconds = float(parts.group(3))
            direction = parts.group(4)
            
            decimal = degrees + minutes/60 + seconds/3600
            
            if direction in ['S', 'W']:
                decimal = -decimal
            return decimal
    except Exception as e:
        print(f"⚠️ DMS 轉換錯誤: {e}")
    return None

def extract_name_from_url(url):
    """
    從網址中挖掘店名
    """
    try:
        decoded_url = unquote(url)
        match = re.search(r'/place/([^/]+)/', decoded_url)
        if match:
            return match.group(1).replace('+', ' ')
    except Exception as e:
        print(f"⚠️ 解析店名失敗: {e}")
    
    return "未命名地點"

def extract_coordinates(url):
    """
    從網址解析經緯度 (支援十進位與度分秒)
    """
    # 關鍵步驟：先將網址解碼 (把 %C2%B0 變回 °)
    decoded_url = unquote(url)
    print(f"🔓 解碼後網址: {decoded_url[:100]}...")

    # Pattern 1: 十進位 @lat,long
    match = re.search(r'@(-?\d+\.\d+),(-?\d+\.\d+)', decoded_url)
    if match:
        return float(match.group(1)), float(match.group(2))
        
    # Pattern 2: 查詢參數 q=lat,long (十進位)
    match = re.search(r'q=(-?\d+\.\d+),(-?\d+\.\d+)', decoded_url)
    if match:
        return float(match.group(1)), float(match.group(2))
        
    # Pattern 3: Google 內嵌格式 !3d...!4d...
    match = re.search(r'!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)', decoded_url)
    if match:
        return float(match.group(1)), float(match.group(2))

    # Pattern 4: 度分秒格式 (DMS) q=25°03'56.9"N 121°30'31.4"E
    # 這是為了處理你剛剛遇到的那個狀況
    try:
        lat_dms_match = re.search(r'(\d+°\d+\'[\d.]+"[NS])', decoded_url)
        lng_dms_match = re.search(r'(\d+°\d+\'[\d.]+"[EW])', decoded_url)
        
        if lat_dms_match and lng_dms_match:
            lat = parse_dms(lat_dms_match.group(1))
            lng = parse_dms(lng_dms_match.group(1))
            return lat, lng
    except Exception as e:
        print(f"⚠️ DMS 解析失敗: {e}")

    return None, None

def save_location(supabase, user_id, url):
    print(f"🔍 正在解析: {url} ...")
    
    final_url = expand_url(url)
    print(f"➡️ 最終網址: {final_url[:100]}...") 
    
    shop_name = extract_name_from_url(final_url)
    print(f"🏷️ 偵測到店名: {shop_name}")
    
    lat, lng = extract_coordinates(final_url)
    
    if lat and lng:
        print(f"✅ 抓到座標: 緯度 {lat}, 經度 {lng}")
        
        data = {
            "user_id": user_id,
            "original_url": url,
            "name": shop_name,
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
    print("🚀 IG 美食地圖解析器 V3.0 (含度分秒解析) 啟動...")
    
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
        print("⚠️ 缺少參數，請透過 GitHub Actions 執行。")

if __name__ == "__main__":
    main()
