import os
import sys
from dotenv import load_dotenv

# 取得目前腳本所在的目錄，並載入該目錄下的 .env
current_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(current_dir, ".env")
load_dotenv(env_path)

supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_KEY")

print(f"--- Supabase 連線測試 ---")
print(f"專案網址 (URL): {supabase_url}")
print(f"使用金鑰 (Key) 前五碼: {supabase_key[:5] if supabase_key else 'None'}...")

if not supabase_url or not supabase_key:
    print("❌ 錯誤：.env 中未設定 SUPABASE_URL 或 SUPABASE_KEY！")
    sys.exit(1)

try:
    from supabase import create_client
    
    # 建立 Supabase client
    supabase = create_client(supabase_url, supabase_key)
    print("✅ Supabase Client 初始化成功！")
    
    # 嘗試查詢 daily_words 表（此專案的每日單字表）
    print("⏳ 嘗試讀取 'daily_words' 資料表...")
    response = supabase.table("daily_words").select("*").limit(5).execute()
    print("✅ 讀取 'daily_words' 資料表成功！")
    print("資料庫回傳結果：")
    print(response.data)
    
except ImportError:
    print("❌ 錯誤：未安裝 supabase 模組。請確認是否已在虛擬環境中安裝。")
except Exception as e:
    print(f"❌ 測試過程中發生異常: {e}")
