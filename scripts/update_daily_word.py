import re

with open("multiturn.py", "r", encoding="utf-8") as f:
    content = f.read()

# 1. Update DailyWordItem
old_daily_word_item = """class DailyWordItem(BaseModel):
    word: str = Field(description="英文單字")
    meaning: str = Field(description="繁體中文意思")
    example: str = Field(description="英文例句，並附上中文翻譯，例如: 'This is an apple. (這是一個蘋果。)'")"""

new_daily_word_item = """class DailyWordItem(BaseModel):
    word: str = Field(description="英文單字")
    part_of_speech: str = Field(description="詞性，例如: n., v., adj.", default="")
    meaning: str = Field(description="繁體中文意思")
    example: str = Field(description="英文例句，並附上中文翻譯，例如: 'This is an apple. (這是一個蘋果。)'")"""

content = content.replace(old_daily_word_item, new_daily_word_item)

# 2. Update make_daily_word_flex
new_make_daily_word_flex = """def make_daily_word_flex(item: DailyWordItem) -> dict:
    return {
        "type": "bubble",
        "header": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": "#F7A800",
            "contents": [
                {
                    "type": "text",
                    "text": "💡 每日單字 (Daily Word)",
                    "color": "#ffffff",
                    "weight": "bold",
                    "size": "md"
                }
            ]
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "text",
                    "text": item.word or "",
                    "weight": "bold",
                    "size": "xl",
                    "color": "#1DB446"
                },
                {
                    "type": "text",
                    "text": f"[{item.part_of_speech or ''}] {item.meaning or ''}" if item.part_of_speech else (item.meaning or ""),
                    "color": "#666666",
                    "size": "md",
                    "margin": "sm"
                },
                {
                    "type": "box",
                    "layout": "horizontal",
                    "margin": "md",
                    "spacing": "sm",
                    "contents": [
                        {
                            "type": "button",
                            "style": "secondary",
                            "height": "sm",
                            "action": {
                                "type": "message",
                                "label": "🔊 發音",
                                "text": f"發音: {item.word or ''}"
                            }
                        },
                        {
                            "type": "button",
                            "style": "primary",
                            "color": "#1DB446",
                            "height": "sm",
                            "action": {
                                "type": "message",
                                "label": "➕ 收藏",
                                "text": f"記憶新增快捷: 每日單字|{item.word or ''}|{item.meaning or ''}"
                            }
                        }
                    ]
                },
                {
                    "type": "separator",
                    "margin": "lg"
                },
                {
                    "type": "text",
                    "text": "💡 實用例句：",
                    "weight": "bold",
                    "size": "sm",
                    "color": "#8c8c8c",
                    "margin": "md"
                },
                {
                    "type": "text",
                    "text": item.example or "",
                    "wrap": True,
                    "margin": "sm",
                    "size": "sm",
                    "color": "#333333"
                }
            ]
        }
    }"""

content = re.sub(r'def make_daily_word_flex\(item: DailyWordItem\) -> dict:.*?def make_pronunciation_flex', lambda m: new_make_daily_word_flex + "\n\n\ndef make_pronunciation_flex", content, flags=re.DOTALL)

with open("multiturn.py", "w", encoding="utf-8") as f:
    f.write(content)

print("Daily word refactor applied")
