# 檔案位置: ig_map/main.py
import os
import sys
import re
import json
import requests
from urllib.parse import unquote
from bs4 import BeautifulSoup

# 設定路徑以引用 utils
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from utils.supabase_client import init_supabase

def get_url_content(short_url):
    """
    獲取網址的最終 URL 和 HTML 內容
    """
    try:
        # 模擬真實瀏覽器 User-Agent
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
            "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7"
        }
        response = requests.get(short_url, headers=headers, allow_redirects=True, timeout=10)
        return response.url, response.text
    except Exception as e:
        print(f"❌ 網頁讀取失敗: {e}")
        return short_url, ""

def extract_from_json_ld(soup):
    """
    [V5.0 核心] 從 Google 的 JSON-LD 結構化資料中直接提取座標
    這是最準確的方法，專門對付餐廳/商家頁面
    """
    try:
        # 尋找所有 type="application/ld+json" 的腳本
        scripts = soup.find_all('script', type='application/ld+json')
        
        for script in scripts:
            try:
                data = json.loads(script.string)
                
                # 有時候 data 是一個 list，有時候是 dict
                if isinstance(data, list):
                    items = data
                else:
                    items = [data]
                
                for item in items:
                    # 確認是否有 @type 和 geo 屬性
                    if 'geo' in item and '@type' in item:
                        # 這是我們要的商家資料！
                        lat = float(item['geo']['latitude'])
                        lng = float(item['geo']['longitude'])
                        name = item.get('name', '')
                        print(f"💎 透過 JSON-LD 完美獲取: {name} ({lat}, {lng})")
                        return lat, lng, name
            except:
                continue
    except Exception as e:
        print(f"⚠️ JSON-LD 解析微恙 (不影響後續嘗試): {e}")
        
    return None, None, None

def extract_data_from_html(html):
    """
    綜合解析：JSON-LD (首選) -> Meta Tags (次選)
    """
    soup = BeautifulSoup(html, 'html.parser')

    # 1. 第一優先：嘗試解析 JSON-LD (最穩)
    lat, lng, name = extract_from_json_ld(soup)
    if lat and lng:
        return lat, lng, name

    # 2. 第二優先：如果 JSON-LD 失敗，嘗試抓 Meta Tags (og:image / og:title)
    print("⚠️ JSON-LD 未找到，降級使用 Meta Tags 解析...")
    
    # 抓店名
    if not name:
        og_title = soup.find("meta", property="og:title")
        if og_title and og_title.get("content"):
            name = og_title["content"].split('·')[0].strip()
            print(f"🕵️ 透過 Meta Tag 抓到店名: {name}")

    # 抓座標
    og_image = soup.find("meta", property="og:image")
    if og_image and og_image.get("content"):
        image_url = og_image["content"]
        # 嘗試從圖片網址找 center=lat,lng
        match = re.search(r'center=(-?\d+\.\d+)%2C(-?\d+\.\d+)', image_url)
        if not match:
            match = re.search(r'center=(-?\d+\.\d+),(-?\d+\.\d+)', image_url)
        
        if match:
            lat, lng = float(match.group(1)), float(match.group(2))
            print(f"🕵️ 透過 og:image 抓到座標: {lat}, {lng}")

    return lat, lng, name

def extract_coordinates_from_url(url):
    """
    最後手段：從網址解析 (備用)
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

    return None, None

def save_location(supabase, user_id, short_url):
    print(f"🔍 正在解析: {short_url} ...")
    
    # 1. 取得網頁內容
    final_url, html_content = get_url_content(short_url)
    print(f"➡️ 最終網址: {final_url[:80]}...") 
    
    # 2. 爬蟲解析 (JSON-LD > Meta Tags)
    lat, lng, shop_name = extract_data_from_html(html_content)
    
    # 3. 如果爬蟲全失敗，最後試試看網址有沒有
    if not lat or not lng:
        print("⚠️ HTML 解析無座標，最後嘗試 URL 分析...")
        lat, lng = extract_coordinates_from_url(final_url)
    
    # 確保有店名
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
        print("⚠️ 全面解析失敗：無法從該連結獲取座標。")
    
    return False

def main():
    print("🚀 IG 美食地圖解析器 V5.0 (結構化資料版) 啟動...")
    
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
