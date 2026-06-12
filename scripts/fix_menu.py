import re

with open('multiturn.py', 'r', encoding='utf-8') as f:
    content = f.read()

pattern = re.compile(r'def send_quiz_menu\(event\):.*?# === User Mode Management ===', re.DOTALL)

new_func = '''def send_quiz_menu(event):
    import json
    bubbles = []
    scopes = [
        {"title": "📚 專屬單字庫", "level": "單字庫", "desc": "從您的記憶庫中抽題", "color": "#1DB446"},
        {"title": "🌱 初級程度", "level": "初級", "desc": "基礎英文單字與文法", "color": "#FFC107"},
        {"title": "⭐ 中級程度", "level": "中級", "desc": "進階實用英文", "color": "#FF9800"},
        {"title": "🔥 高級程度", "level": "高級", "desc": "高難度挑戰", "color": "#F44336"}
    ]
    
    for s in scopes:
        bubbles.append({
            "type": "bubble",
            "size": "kilo",
            "header": {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": s["color"],
                "contents": [
                    {
                        "type": "text",
                        "text": s["title"],
                        "weight": "bold",
                        "color": "#FFFFFF",
                        "size": "xl"
                    },
                    {
                        "type": "text",
                        "text": s["desc"],
                        "color": "#FFFFFFcc",
                        "size": "xs",
                        "margin": "sm"
                    }
                ]
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "spacing": "md",
                "contents": [
                    {
                        "type": "button",
                        "style": "secondary",
                        "action": {"type": "message", "label": "選擇題", "text": f"測驗 選擇 {s['level']}"}
                    },
                    {
                        "type": "button",
                        "style": "secondary",
                        "action": {"type": "message", "label": "填空題", "text": f"測驗 填空 {s['level']}"}
                    },
                    {
                        "type": "button",
                        "style": "secondary",
                        "action": {"type": "message", "label": "閱讀題", "text": f"測驗 閱讀 {s['level']}"}
                    },
                    {
                        "type": "button",
                        "style": "primary",
                        "color": s["color"],
                        "action": {"type": "message", "label": "🎧 聽寫題", "text": f"測驗 聽寫 {s['level']}"}
                    }
                ]
            }
        })
        
    flex_content = {"type": "carousel", "contents": bubbles}
    
    with ApiClient(configuration) as api_client:
        line_api = MessagingApi(api_client)
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[FlexMessage(alt_text="測驗大廳", contents=FlexContainer.from_json(json.dumps(flex_content)))]
            )
        )

# === User Mode Management ==='''

content = pattern.sub(new_func, content)

with open('multiturn.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("send_quiz_menu successfully replaced!")
