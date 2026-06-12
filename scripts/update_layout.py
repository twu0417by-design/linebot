import re

with open("multiturn.py", "r", encoding="utf-8") as f:
    content = f.read()

# 1. Update Schemas
content = content.replace(
    'part_of_speech: str = Field(description="詞性，例如: n., v., adj.", default="")',
    'part_of_speech: str = Field(description="詞性（必須使用英文縮寫，如 n., v., adj., adv.）", default="")'
)
content = content.replace(
    'part_of_speech: str = Field(description="詞性（若輸入為單字才填）", default="")',
    'part_of_speech: str = Field(description="詞性（必須使用英文縮寫，如 n., v., adj.，若輸入為單字才填）", default="")'
)
content = content.replace(
    'part_of_speech: str = Field(description="詞性，例如: v. 或 n.，有多個請用逗號隔開")',
    'part_of_speech: str = Field(description="詞性（必須使用英文縮寫，如 n., v., adj.，有多個請用逗號隔開）")'
)

# 2. Update make_translation_flex single word branch
old_translation_body = """            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": result.word or "",
                        "weight": "bold",
                        "size": "xl",
                        "color": "#1DB446"
                    },
                    {
                        "type": "text",
                        "text": f"[{result.part_of_speech or ''}] {result.word_meaning or ''}",
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
                                    "text": f"發音: {result.word or ''}"
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
                                    "text": f"記憶新增快捷: 單字翻譯|{result.word or ''}|{result.word_meaning or ''}"
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
                        "text": result.example_sentence or "",
                        "wrap": True,
                        "margin": "sm",
                        "size": "sm",
                        "color": "#333333"
                    }
                ]
            }
        }"""

new_translation_body = """            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": result.word or "",
                        "weight": "bold",
                        "size": "xl",
                        "color": "#1DB446"
                    },
                    {
                        "type": "text",
                        "text": f"[{result.part_of_speech or ''}] {result.word_meaning or ''}" if result.part_of_speech else (result.word_meaning or ""),
                        "color": "#666666",
                        "size": "md",
                        "margin": "sm"
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
                        "text": result.example_sentence or "",
                        "wrap": True,
                        "margin": "sm",
                        "size": "sm",
                        "color": "#333333"
                    }
                ]
            },
            "footer": {
                "type": "box",
                "layout": "horizontal",
                "spacing": "sm",
                "contents": [
                    {
                        "type": "button",
                        "style": "secondary",
                        "height": "sm",
                        "action": {
                            "type": "message",
                            "label": "🔊 發音",
                            "text": f"發音: {result.word or ''}"
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
                            "text": f"記憶新增快捷: 單字翻譯|{result.word or ''}|{result.word_meaning or ''}"
                        }
                    }
                ]
            }
        }"""

content = content.replace(old_translation_body, new_translation_body)


# 3. Update make_daily_word_flex
old_daily_word_body = """        "body": {
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

new_daily_word_body = """        "body": {
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
        },
        "footer": {
            "type": "box",
            "layout": "horizontal",
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
        }
    }"""

content = content.replace(old_daily_word_body, new_daily_word_body)

with open("multiturn.py", "w", encoding="utf-8") as f:
    f.write(content)

print("Layout and schema refactored")
