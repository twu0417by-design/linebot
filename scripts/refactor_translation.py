import re

with open("multiturn.py", "r", encoding="utf-8") as f:
    content = f.read()

# 1. Replace TranslationResult
old_translation_result = """class TranslationVocabItem(BaseModel):
    word: str = Field(description="文章中的關鍵英文單字或片語")
    meaning: str = Field(description="該單字或片語的中文解釋")


class TranslationResult(BaseModel):
    translated_text: str = Field(description="翻譯後的完整文章，必須保留原段落")
    vocabularies: List[TranslationVocabItem] = Field(description="從文章中挑選出的 3-5 個關鍵詞彙與其解釋")"""

new_translation_result = """class TranslationVocabItem(BaseModel):
    word: str = Field(description="文章中的關鍵英文單字或片語")
    meaning: str = Field(description="該單字或片語的中文解釋")


class TranslationResult(BaseModel):
    is_word: bool = Field(description="輸入的內容是否為單一單字")
    original_text: str = Field(description="原文章段落或句子（若輸入為文章才填）", default="")
    translated_text: str = Field(description="文章中文翻譯（若輸入為文章才填）", default="")
    vocabularies: List[TranslationVocabItem] = Field(description="文章中挑選出的 3-5 個關鍵詞彙與解釋（若輸入為文章才填）", default_factory=list)
    word: str = Field(description="原單字（若輸入為單字才填）", default="")
    word_meaning: str = Field(description="單字中文意思（若輸入為單字才填）", default="")
    part_of_speech: str = Field(description="詞性（若輸入為單字才填）", default="")
    example_sentence: str = Field(description="英文例句與其中文翻譯（若輸入為單字才填）", default="")"""

content = content.replace(old_translation_result, new_translation_result)


# 2. Replace translate_article
old_translate_article = """def translate_article(text: str) -> TranslationResult | None:
    if not gemini_client:
        return None
    prompt = f"請將以下文章翻譯成繁體中文，並挑選出 3-5 個關鍵詞彙進行解釋。\\n\\n文章內容：\\n{text}"
    try:
        response = gemini_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=TranslationResult,
                system_instruction="你是一個專業的翻譯與語言學習專家。請一律使用繁體中文（台灣語境）回覆翻譯結果與解釋。"
            )
        )
        return response.parsed
    except Exception as e:
        app.logger.error(f"translate_article error: {e}")
        return None"""

new_translate_article = """def translate_article(text: str) -> TranslationResult | None:
    if not gemini_client:
        return None
    prompt = f"請判斷以下輸入是「單一單字」還是「文章/句子」。\\n如果是單字，請提供中文意思、詞性、以及一句包含中文翻譯的例句。\\n如果是文章或句子，請提供原句、將其翻譯成繁體中文，並挑選出 3-5 個關鍵詞彙進行解釋。\\n\\n輸入內容：\\n{text}"
    try:
        response = gemini_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=TranslationResult,
                system_instruction="你是一個專業的翻譯與語言學習專家。請一律使用繁體中文（台灣語境）回覆。"
            )
        )
        return response.parsed
    except Exception as e:
        app.logger.error(f"translate_article error: {e}")
        return None"""

content = content.replace(old_translate_article, new_translate_article)

# 3. Replace make_translation_flex
new_make_translation_flex = """def make_translation_flex(result: TranslationResult) -> dict:
    if result.is_word:
        return {
            "type": "bubble",
            "header": {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": "#050B24",
                "contents": [
                    {
                        "type": "text",
                        "text": "📝 單字解析",
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
        }
    else:
        vocab_contents = []
        for v in (result.vocabularies or []):
            vocab_contents.append({
                "type": "box",
                "layout": "vertical",
                "margin": "md",
                "paddingAll": "10px",
                "backgroundColor": "#F9F9F9",
                "cornerRadius": "md",
                "contents": [
                    {
                        "type": "text",
                        "text": v.word,
                        "weight": "bold",
                        "color": "#1DB446",
                        "size": "md"
                    },
                    {
                        "type": "text",
                        "text": v.meaning,
                        "color": "#666666",
                        "size": "sm",
                        "wrap": True,
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
                                    "text": f"發音: {v.word}"
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
                                    "text": f"記憶新增快捷: 文章翻譯|{v.word}|{v.meaning}"
                                }
                            }
                        ]
                    }
                ]
            })
        
        bubble = {
            "type": "bubble",
            "header": {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": "#050B24",
                "contents": [
                    {
                        "type": "text",
                        "text": "📝 翻譯與單字解析",
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
                        "text": "原文：",
                        "weight": "bold",
                        "size": "sm",
                        "color": "#8c8c8c"
                    },
                    {
                        "type": "text",
                        "text": result.original_text or "",
                        "wrap": True,
                        "margin": "sm",
                        "size": "md",
                        "color": "#333333",
                        "style": "italic"
                    },
                    {
                        "type": "separator",
                        "margin": "md"
                    },
                    {
                        "type": "text",
                        "text": "中文翻譯：",
                        "weight": "bold",
                        "size": "sm",
                        "color": "#8c8c8c",
                        "margin": "md"
                    },
                    {
                        "type": "text",
                        "text": result.translated_text or "",
                        "wrap": True,
                        "margin": "sm",
                        "size": "md",
                        "color": "#111111"
                    }
                ]
            }
        }
        
        if vocab_contents:
            bubble["body"]["contents"].extend([
                {
                    "type": "separator",
                    "margin": "lg"
                },
                {
                    "type": "text",
                    "text": "💡 關鍵單字片語：",
                    "weight": "bold",
                    "size": "sm",
                    "color": "#8c8c8c",
                    "margin": "md"
                },
                {
                    "type": "box",
                    "layout": "vertical",
                    "contents": vocab_contents
                }
            ])
            
        return bubble"""

content = re.sub(r'def make_translation_flex\(result: TranslationResult\) -> dict:.*?return bubble', new_make_translation_flex, content, flags=re.DOTALL)

with open("multiturn.py", "w", encoding="utf-8") as f:
    f.write(content)

print("Translation refactor applied")
