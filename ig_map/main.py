# 檔案位置: ig_map/main.py
import os
import sys
import re
import json
import requests
from urllib.parse import unquote, quote
from bs4 import BeautifulSoup

# 設定路徑以引用 utils
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from utils.supabase_client import init_supabase

# 模擬瀏覽器 Header (這很重要，騙過 Google 我們是電腦)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7"
}

def get_url_content(url):
    try:
        response = requests.get(url, headers=HEADERS, allow_redirects=True, timeout=10)
        return response.url, response.text
    except Exception as e:
        print(f"❌ 網頁讀取失敗: {e}")
        return url, ""

def extract_from_json_ld(soup):
    """ 從 JSON-LD 提取座標 (最準) """
    try:
        scripts = soup.find_all('script', type='application/ld+json')
        for script in scripts:
            try:
                data = json.loads(script.string)
                items = data if isinstance(data, list) else [data]
                for item in items:
                    if 'geo' in item and '@type' in item:
                        lat = float(item['geo']['latitude'])
                        lng = float(item['geo']['longitude'])
                        name = item.get('name', '')
                        print(f"💎 JSON-LD 命中: {name}")
                        return lat, lng, name
            except: continue
    except: pass
    return None, None, None

def extract_coordinates_from_text(text):
    """
    暴力搜尋：直接在文字/網址/HTML中尋找座標特徵
    """
    # 1. Google Maps URL pattern (!3d...!4d...)
    match = re.search(r'!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)', text)
    if match: return float(match.group(1)), float(match.group(2))

    # 2. @lat,long pattern
    match = re.search(r'@(-?\d+\.\d+),(-?\d+\.\d+)', text)
    if match: return float(match.group(1)), float(match.group(2))
    
    # 3. plain lat,long pattern (search param)
    match = re.search(r'q=(-?\d+\.\d+),(-?\d+\.\d+)', text)
    if match: return float(match.group(1)), float(match.group(2))

    return None, None

def extract_name_fallback(soup, url):
    """ 抓取店名 (Meta Tag 或 URL) """
    # 1. Meta Tag
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        return og_title["content"].split('·')[0].strip()
    
    # 2. URL decoding
    decoded_url = unquote(url)
    match = re.search(r'/place/([^/]+)/', decoded_url)
    if match:
        return match.group(1).replace('+', ' ')
        
    return "未命名地點"

def search_place_by_name(shop_name):
    """
    [V6.0 核心] 回馬槍戰術：用店名去 Google Maps 搜尋，獲取真正的座標 URL
    """
    print(f"🔄 啟動回馬槍戰術：正在搜尋「{shop_name}」...")
    try:
        # 構造搜尋連結
        search_url = f"https://www.google.com/maps/search/{quote(shop_name)}"
        response = requests.get(search_url, headers=HEADERS, allow_redirects=True, timeout=10)
        
        print(f"🔄 搜尋跳轉網址: {response.url[:60]}...")
        
        # 搜尋結果的網址通常會包含座標
        lat, lng = extract_coordinates_from_text(response.url)
        
        # 如果網址沒有，搜 HTML 內容
        if not lat:
            lat, lng = extract_coordinates_from_text(response.text)
            
        if lat and lng:
            print(f"🎯 搜尋成功！找回座標: {lat}, {lng}")
            return lat, lng
            
    except Exception as e:
        print(f"⚠️ 搜尋失敗: {e}")
        
    return None, None

def save_location(supabase, user_id, short_url):
    print(f"🔍 正在解析: {short_url} ...")
    
    # 1. 初步解析
    final_url, html_content = get_url_content(short_url)
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # 2. 嘗試獲取資料
    lat, lng, name = extract_from_json_ld(soup)
    
    # 如果 JSON-LD 沒抓到店名，用 Meta 補抓
    if not name:
        name = extract_name_fallback(soup, final_url)
    
    print(f"🏷️ 偵測店名: {name}")

    # 3. 如果沒座標，先試試看網址/HTML裡有沒有藏
    if not lat:
        lat, lng = extract_coordinates_from_text(final_url)
    if not lat:
        lat, lng = extract_coordinates_from_text(html_content)

    # 4. [大招] 如果還是沒座標，但我們有店名 -> 執行回馬槍搜尋！
    if (not lat or not lng) and name and name != "未命名地點":
        print("⚠️ 原始連結無座標，嘗試使用店名反查...")
        lat, lng = search_place_by_name(name)

    # 結算
    if lat and lng:
        print(f"✅ 最終鎖定: 緯度 {lat}, 經度 {lng}")
        
        data = {
            "user_id": user_id,
            "original_url": short_url,
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
        print("❌ 解析失敗：已嘗試所有手段 (JSON-LD, HTML, URL, 反查搜尋)，仍無法獲取座標。")
    
    return False

def main():
    print("🚀 IG 美食地圖解析器 V6.0 (回馬槍搜尋版) 啟動...")
    
    if len(sys.argv) > 2:
        target_url = sys.argv[1]
        user_id = sys.argv[2]
        try:
            supabase = init_supabase()
            save_location(supabase, user_id, target_url)
        except Exception as e:
            print(f"❌ 執行發生錯誤: {e}")
            sys.exit(1) 
    else:
        print("⚠️ 缺少參數")

if __name__ == "__main__":
    main()
