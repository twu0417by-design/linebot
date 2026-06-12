import os
import requests

def load_env():
    """載入本地 .env 檔案的環境變數"""
    if os.path.exists(".env"):
        with open(".env", "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip().strip('"').strip("'")
                    v = v.strip().strip('"').strip("'")
                    os.environ[k] = v

def init_rich_menu():
    load_env()
    token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
    
    if not token or token == "請在此處填入您的 LINE Channel Access Token":
        print("❌ 錯誤：未設定 LINE_CHANNEL_ACCESS_TOKEN 環境變數。請在環境變數或 .env 檔案中設定。")
        return False
        
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    # 1. 取得現有的 rich menu 列表並全部刪除
    print("正在清理舊的 Rich Menu...")
    try:
        res = requests.get("https://api.line.me/v2/bot/richmenu/list", headers={"Authorization": f"Bearer {token}"})
        res.raise_for_status()
        rich_menus = res.json().get("richmenus", [])
        for menu in rich_menus:
            menu_id = menu.get("richMenuId")
            print(f"刪除舊的 Rich Menu: {menu_id}")
            requests.delete(f"https://api.line.me/v2/bot/richmenu/{menu_id}", headers={"Authorization": f"Bearer {token}"})
    except Exception as e:
        print(f"❌ 清理舊 Rich Menu 失敗：{e}")
        
    target_menu_id = None
            
    # 2. 如果不存在，則建立新的 Rich Menu
    if not target_menu_id:
        print("正在建立新的 Rich Menu...")
        rich_menu_data = {
            "size": {
                "width": 2500,
                "height": 1686
            },
            "selected": True,
            "name": "Language Learning Rich Menu",
            "chatBarText": "功能選單",
            "areas": [
                {
                    "bounds": {"x": 0, "y": 0, "width": 833, "height": 843},
                    "action": {"type": "message", "label": "翻譯", "text": "翻譯"}
                },
                {
                    "bounds": {"x": 833, "y": 0, "width": 833, "height": 843},
                    "action": {"type": "message", "label": "文法", "text": "文法"}
                },
                {
                    "bounds": {"x": 1666, "y": 0, "width": 834, "height": 843},
                    "action": {"type": "message", "label": "每日單字", "text": "每日單字"}
                },
                {
                    "bounds": {"x": 0, "y": 843, "width": 833, "height": 843},
                    "action": {"type": "message", "label": "測驗", "text": "測驗"}
                },
                {
                    "bounds": {"x": 833, "y": 843, "width": 833, "height": 843},
                    "action": {"type": "message", "label": "記憶查詢", "text": "記憶查詢"}
                },
                {
                    "bounds": {"x": 1666, "y": 843, "width": 834, "height": 843},
                    "action": {"type": "message", "label": "英文會話", "text": "英文會話"}
                }
            ]
        }
        
        try:
            res = requests.post("https://api.line.me/v2/bot/richmenu", headers=headers, json=rich_menu_data)
            res.raise_for_status()
            target_menu_id = res.json().get("richMenuId")
            print(f"成功建立 Rich Menu，ID: {target_menu_id}")
        except Exception as e:
            print(f"❌ 建立 Rich Menu 失敗：{e}")
            if 'res' in locals():
                print(f"回應內容: {res.text}")
            return False
            
    # 3. 上傳 Rich Menu 圖片
    img_path = "rich_menu1.jpg"
    if not os.path.exists(img_path):
        print(f"❌ 錯誤：找不到 {img_path} 圖片。請確認圖片是否存在。")
        return False
        
    print("正在上傳 Rich Menu 圖片...")
    try:
        with open(img_path, "rb") as f:
            img_data = f.read()
        upload_headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "image/jpeg"
        }
        res = requests.post(
            f"https://api-data.line.me/v2/bot/richmenu/{target_menu_id}/content",
            headers=upload_headers,
            data=img_data
        )
        res.raise_for_status()
        print("圖片上傳成功！")
    except Exception as e:
        print(f"❌ 上傳 Rich Menu 圖片失敗：{e}")
        if 'res' in locals():
            print(f"回應內容: {res.text}")
        return False
            
    # 4. 設定為預設 Rich Menu
    print("正在將 Rich Menu 設定為預設...")
    try:
        res = requests.post(
            f"https://api.line.me/v2/bot/user/all/richmenu/{target_menu_id}",
            headers={"Authorization": f"Bearer {token}"}
        )
        res.raise_for_status()
        print("🎉 成功將 Rich Menu 設定為預設！")
        return True
    except Exception as e:
        print(f"❌ 設定預設 Rich Menu 失敗：{e}")
        if 'res' in locals():
            print(f"回應內容: {res.text}")
        return False

if __name__ == "__main__":
    init_rich_menu()
