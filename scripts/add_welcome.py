import re

with open('multiturn.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Add FollowEvent to imports
import_old = "from linebot.v3.webhooks import ImageMessageContent, MessageEvent, TextMessageContent"
import_new = "from linebot.v3.webhooks import ImageMessageContent, MessageEvent, TextMessageContent, FollowEvent"
content = content.replace(import_old, import_new)

# 2. Add FollowEvent handler
follow_handler = '''
@handler.add(FollowEvent)
def handle_follow(event):
    welcome_text = (
        "🎉 歡迎加入！我是您的 AI 專屬英文家教！\\n\\n"
        "這裡有超多豐富的功能可以陪您輕鬆學英文：\\n"
        "👉 直接傳送英文單字或句子，我會立刻為您翻譯！\\n"
        "👉 點擊下方【選單】即可切換各種超強功能：\\n"
        "   📚 單字庫：收藏您的專屬單字\\n"
        "   🎓 隨堂測驗：初中高級、多益、雅思隨機出題！\\n"
        "   🗣️ 英文會話：跟 AI 教練進行情境對話演練\\n"
        "   📖 文法拆解：幫您秒懂長難句結構\\n"
        "   📅 每日單字：天天學習一個全新單字\\n\\n"
        "📸 小彩蛋：直接傳送一張有英文或物品的照片給我，我會自動幫您解析喔！快來試試看吧！"
    )
    with ApiClient(configuration) as api_client:
        line_api = MessagingApi(api_client)
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=welcome_text)]
            )
        )

# === LINE Message Handlers ==='''

content = content.replace('# === LINE Message Handlers ===', follow_handler)

with open('multiturn.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Added FollowEvent handler!")
