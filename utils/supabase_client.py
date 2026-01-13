import os
from supabase import create_client, Client

def init_supabase() -> Client:
    """
    建立並回傳 Supabase 連線物件。
    從環境變數讀取 URL 和 KEY，確保資安。
    """
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")

    if not url or not key:
        # 在 GitHub Actions 裡如果沒設 Secret，這裡會報錯提醒你
        raise ValueError("❌ 錯誤: 找不到 SUPABASE_URL 或 SUPABASE_KEY。請檢查 GitHub Secrets。")

    return create_client(url, key)