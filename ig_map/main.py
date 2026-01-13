# 檔案位置: ig_map/main.py
import os
import sys
import re
import requests
from urllib.parse import unquote
from bs4 import BeautifulSoup # 引入強大的網頁解析工具

# 設定路徑以引用 utils
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from utils.supabase_client import init_supabase

def get_url_content(short_url):
    """
    獲取網址的最終 URL 和 HTML 內容
    """
    try:
        # 模擬真實瀏覽器，確保 Google 給我們完整的網頁
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
            "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7"
        }
        response = requests.get(short_url, headers=headers, allow_redirects=True, timeout=10)
        return response.url, response.text
    except Exception as e:
        print(f"❌ 網頁讀取失敗: {e}")
        return short_url, ""

def parse_dms(dms_str):
    """
    將度分秒格式 (25°03'56.9"N) 轉換為十進位
    """
    try:
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

def extract_data_from_html(html):
    """
    [V4.0 新功能] 從網頁 HTML 的 meta tag 中挖出座標和店名
    這是處理手機版連結的關鍵！
    """
    lat, lng, name = None, None, None
    try:
        soup = BeautifulSoup(html, 'html.parser')

        # 1. 抓取店名 (og:title 通常是 "店名 · 地址")
        og_title = soup.find("meta", property="og:title")
        if og_title and og_title.get("content"):
            full_title = og_title["content"]
            # Google 的標題通常是 "店名 · 地址"，我們只取前面
            name = full_title.split('·')[0].strip()
            print(f"🕵️ 透過 HTML 抓到店名: {name}")

        # 2. 抓取座標 (從 og:image 抓取 center 參數)
        # 範例: https://maps.google.com/.../staticmap?center=24.743,121.730&zoom=...
        og_image = soup.find("meta", property="og:image")
        if og_image and og_image.get("content"):
            image_url = og_image["content"]
            match = re.search(r'center=(-?\d+\.\d+)%2C(-?\d+\.\d+)', image_url)
            # 有時候是用逗號分隔，沒編碼
            if not match:
                match = re.search(r'center=(-?\d+\.\d+),(-?\d+\.\d+)', image_url)
                
            if match:
                lat, lng = float(match.group(1)), float(match.group(2))
                print(f"🕵️ 透過 HTML og:image 抓到座標: {lat}, {lng}")

    except Exception as e:
        print(f"⚠️ HTML 解析失敗: {e}")
    
    return lat, lng, name

def extract_name_from_url(url):
    """
    從網址中挖掘店名 (備用)
    """
    try:
        decoded_url = unquote(url)
        match = re.search(r'/place/([^/]+)/', decoded_url)
        if match:
            return match.group(1).replace('+', ' ')
    except:
        pass
    return None

def extract_coordinates_from_url(url):
    """
    從網址解析經緯度 (備用)
    """
    decoded_url = unquote(url)
    
    # Pattern 1: @lat,long
    match = re.search(r'@(-?\d+\.\d+),(-?\d+\.\d+)', decoded_url)
    if match: return float(match.group(1)), float(match.group(2))
        
    # Pattern 2: q=lat,long
    match = re.search(r'q=(-?\d+\.\d+),(-?\d+\.\d+)', decoded_url)
    if match: return float(match.group(1)), float(match.group(2))
        
    # Pattern 3: !3d...!4d...
    match = re.search(r'!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)', decoded_url)
    if match: return float(match.group(1)), float(match.group(2))

    # Pattern 4: DMS 格式
    try:
        lat_match = re.search(r'(\d+°\d+\'[\d.]+"[NS])', decoded_url)
        lng_match = re.search(r'(\d+°\d+\'[\d.]+"[EW])', decoded_url)
        if lat_match and lng_match:
            return parse_dms(lat_match.group(1)), parse_dms(lng_match.group(1))
    except:
        pass

    return None, None

def save_location(supabase, user_id, short_url):
    print(f"🔍 正在解析: {short_url} ...")
    
    # 1. 取得最終網址與網頁內容 (這是 V4.0 的核心)
    final_url, html_content = get_url_content(short_url)
    print(f"➡️ 最終網址: {final_url[:80]}...") 
    
    # 2. 先嘗試從 HTML (爬蟲) 獲取資料 -> 這是最準的
    lat, lng, html_name = extract_data_from_html(html_content)
    
    # 3. 如果 HTML 沒抓到，再用舊方法從 URL 算
    if not lat or not lng:
        print("⚠️ HTML 內無座標，嘗試從網址解析...")
        lat, lng = extract_coordinates_from_url(final_url)
        
    # 店名邏輯：優先用 HTML 抓到的中文名，沒有才用網址解碼
    shop_name = html_name if html_name else extract_name_from_url(final_url)
    if not shop_name:
        shop_name = "未命名地點"

    print(f"🏷️ 最終判定店名: {shop_name}")
    
    if lat and lng:
        print(f"✅ 成功鎖定: 緯度 {lat}, 經度 {lng}")
        
        data = {
            "user_id": user_id,
            "original_url": short_url,
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
        print("⚠️ 無法解析出座標 (URL與HTML皆失敗)。")
    
    return False

def main():
    print("🚀 IG 美食地圖解析器 V4.0 (爬蟲強攻版) 啟動...")
    
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
