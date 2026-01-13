# 檔案位置: ig_map/main.py
import os
import sys
import re
import json
import requests
import time
from urllib.parse import unquote, quote
from bs4 import BeautifulSoup

# 設定路徑以引用 utils
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from utils.supabase_client import init_supabase

# 模擬瀏覽器 Header
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7"
}

def get_url_content(url):
    try:
        # 增加 headers 與 timeout 穩定性
        response = requests.get(url, headers=HEADERS, allow_redirects=True, timeout=15)
        return response.url, response.text
    except Exception as e:
        print(f"❌ 網頁讀取失敗: {e}")
        return url, ""

def extract_from_json_ld(soup):
    """ [戰術 1] 從 JSON-LD 提取座標 (Google 標準) """
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

def search_osm_nominatim(shop_name):
    """
    [戰術 2 - 新功能] 呼叫 OpenStreetMap 免費 API 查詢
    這是非常乾淨且穩定的 API，不需爬蟲
    """
    print(f"🌍 呼叫 OSM 盟軍：查詢「{shop_name}」...")
    try:
        # 使用 Nominatim API
        base_url = "https://nominatim.openstreetmap.org/search"
        params = {
            "q": shop_name,
            "format": "json",
            "limit": 1,
            "accept-language": "zh-TW" # 指定中文
        }
        # OSM 要求必須帶 User-Agent
        osm_headers = {"User-Agent": "IG_Food_Map_Bot/1.0"}
        
        response = requests.get(base_url, params=params, headers=osm_headers, timeout=10)
        data = response.json()
        
        if data and len(data) > 0:
            lat = float(data[0]['lat'])
            lng = float(data[0]['lon'])
            print(f"🌍 OSM 查詢成功！座標: {lat}, {lng}")
            return lat, lng
        else:
            print("🌍 OSM 查無此地 (可能是新開店家)。")
            
    except Exception as e:
        print(f"⚠️ OSM 查詢失敗: {e}")
        
    return None, None

def extract_coordinates_brute_force(text):
    """
    [戰術 3] 暴力過濾：在 HTML 原始碼中尋找台灣範圍內的座標
    台灣範圍: Lat 21-26, Lng 119-123
    """
    try:
        # 尋找所有像是浮點數的數字
        # Google 座標通常小數點後有 5-7 位
        candidates = re.findall(r'(\d{2,3}\.\d{4,15})', text)
        
        valid_lat = None
        valid_lng = None
        
        for num_str in candidates:
            val = float(num_str)
            # 判斷是否為台灣緯度 (20~27)
            if 20 < val < 27:
                valid_lat = val
            # 判斷是否為台灣經度 (118~124)
            if 118 < val < 124:
                valid_lng = val
            
            # 如果湊齊一對，就回傳 (通常 HTML 裡經緯度會靠很近，這個簡單邏輯通常有效)
            if valid_lat and valid_lng:
                return valid_lat, valid_lng
                
    except:
        pass
    return None, None

def extract_name_fallback(soup, url):
    """ 抓取店名 """
    # 1. Meta Tag
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        return og_title["content"].split('·')[0].strip()
    
    # 2. HTML Title
    if soup.title:
        return soup.title.string.split(' - ')[0]
        
    return "未命名地點"

def search_place_by_name_google(shop_name):
    """
    [戰術 4] Google 回馬槍 (桌面版搜尋)
    """
    print(f"🔄 啟動 Google 回馬槍：搜尋「{shop_name}」...")
    try:
        # 強制使用桌面版搜尋 URL (這比 mobile redirect 穩定)
        search_url = f"https://www.google.com.tw/maps/search/{quote(shop_name)}?hl=zh-TW"
        response = requests.get(search_url, headers=HEADERS, allow_redirects=True, timeout=10)
        
        # 嘗試從搜尋結果 HTML 暴力抓座標
        lat, lng = extract_coordinates_brute_force(response.text)
        if lat and lng:
            print(f"🎯 Google 搜尋 HTML 暴力破解成功: {lat}, {lng}")
            return lat, lng
            
    except Exception as e:
        print(f"⚠️ Google 搜尋失敗: {e}")
        
    return None, None

def save_location(supabase, user_id, short_url):
    print(f"🔍 正在解析: {short_url} ...")
    
    # 1. 取得初始頁面
    final_url, html_content = get_url_content(short_url)
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # 2. 嘗試用標準方法抓
    lat, lng, name = extract_from_json_ld(soup)
    
    # 補抓店名
    if not name:
        name = extract_name_fallback(soup, final_url)
    print(f"🏷️ 偵測店名: {name}")

    # 3. 如果沒座標 -> 呼叫 OSM 盟軍 (最乾淨的解法)
    if (not lat or not lng) and name != "未命名地點":
        lat, lng = search_osm_nominatim(name)

    # 4. 如果 OSM 也沒找到 -> Google 搜尋頁面暴力破解 (最髒但有效的解法)
    if (not lat or not lng) and name != "未命名地點":
        lat, lng = search_place_by_name_google(name)

    # 5. 如果還是沒有 -> 試試看原始 HTML 裡有沒有藏台灣座標
    if not lat or not lng:
        print("⚠️ 最後手段：檢查原始 HTML 是否殘留座標...")
        lat, lng = extract_coordinates_brute_force(html_content)

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
        print("❌ 任務失敗：Google 與 OSM 皆無法定位此地點。")
    
    return False

def main():
    print("🚀 IG 美食地圖解析器 V7.0 (盟軍支援版) 啟動...")
    
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
