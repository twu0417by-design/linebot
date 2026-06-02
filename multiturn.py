import os
import tempfile
import uuid
import random
import requests
import json
from io import BytesIO
from urllib.parse import quote_plus

from PIL import Image
from bs4 import BeautifulSoup
from flask import Flask, abort, request, send_from_directory
import markdown
from google import genai
from google.genai import types
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    ApiClient,
    Configuration,
    ImageMessage,
    AudioMessage,
    MessagingApi,
    MessagingApiBlob,
    ReplyMessageRequest,
    TextMessage,
    FlexMessage,
    FlexContainer,
)
from linebot.v3.webhooks import ImageMessageContent, MessageEvent, TextMessageContent
from supabase import Client, create_client
from pydantic import BaseModel, Field
from typing import List

SYSTEM_PROMPT = """
你是繁體中文語言學習助教。你的回答必須精準、簡潔，並且可以直接供學習使用。
對於使用者的翻譯、文法修正、會話演練等要求，請使用條列式（分點）輸出，並對重點單字或文法附上 1~2 個例句。
請一律使用繁體中文（台灣習慣用語，例如：請用『影片』而非『視頻』，『軟體』而非『軟件』，『螢幕』而非『屏幕』）。
"""

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
SPACE_HOST = os.getenv("SPACE_HOST", "")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None
app = Flask(__name__)
configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN or "DUMMY_TOKEN")
handler = WebhookHandler(LINE_CHANNEL_SECRET or "DUMMY_SECRET")
supabase: Client | None = (
    create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None
)
static_tmp_path = tempfile.gettempdir()
os.makedirs(static_tmp_path, exist_ok=True)


# === Pydantic Structures for Gemini Structured Outputs ===

class VocabItem(BaseModel):
    word: str = Field(description="英文單字，例如: 'apple'")
    meaning: str = Field(description="該單字的繁體中文意思，例如: '蘋果'")
    category: str = Field(description="該單字最適合的中文分類，必須使用繁體中文，例如: '食物'、'動物'、'交通'、'文具'")


class ImageAnalysisResult(BaseModel):
    description: str = Field(description="以繁體中文詳細描述圖片中的內容與場景")
    learning_points: str = Field(description="基於這張圖片，提供適合英語學習者的關鍵文法或情境學習重點")
    vocab_list: List[VocabItem] = Field(description="從圖片內容中挑選的 5 個相關英文單字，包含其英文及中文意思")


class DailyWordItem(BaseModel):
    word: str = Field(description="英文單字")
    meaning: str = Field(description="繁體中文意思")
    example: str = Field(description="英文例句，並附上中文翻譯，例如: 'This is an apple. (這是一個蘋果。)'")


class TranslationVocabItem(BaseModel):
    word: str = Field(description="文章中的關鍵英文單字或片語")
    meaning: str = Field(description="該單字或片語的中文解釋")


class TranslationResult(BaseModel):
    translated_text: str = Field(description="翻譯後的完整文章，必須保留原段落")
    vocabularies: List[TranslationVocabItem] = Field(description="從文章中挑選出的 3-5 個關鍵詞彙與其解釋")


class PronunciationResult(BaseModel):
    word: str = Field(description="英文單字")
    ipa_uk: str = Field(description="英式 IPA，例如: /əˈsəʊ.si.eɪt/")
    ipa_us: str = Field(description="美式 IPA，例如: /əˈsoʊ.ʃi.eɪt/")
    part_of_speech: str = Field(description="詞性，例如: v. 或 n.，有多個請用逗號隔開")
    meaning: str = Field(description="中文解釋，有多個意思請簡短列出")
    detail: str = Field(description="詳細用法、常見片語或小叮嚀（約50字）")


# === Flex Message Generators ===

def make_translation_flex(result: TranslationResult) -> dict:
    vocab_contents = []
    for v in result.vocabularies:
        vocab_contents.append({
            "type": "box",
            "layout": "horizontal",
            "margin": "md",
            "alignItems": "center",
            "contents": [
                {
                    "type": "text",
                    "text": v.word,
                    "weight": "bold",
                    "color": "#1DB446",
                    "size": "sm",
                    "flex": 4
                },
                {
                    "type": "text",
                    "text": v.meaning,
                    "color": "#666666",
                    "size": "sm",
                    "flex": 6
                },
                {
                    "type": "text",
                    "text": "🔊",
                    "align": "end",
                    "size": "sm",
                    "action": {
                        "type": "message",
                        "label": "發音",
                        "text": f"發音: {v.word}"
                    },
                    "flex": 1
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
                    "text": "中文翻譯：",
                    "weight": "bold",
                    "size": "sm",
                    "color": "#8c8c8c"
                },
                {
                    "type": "text",
                    "text": result.translated_text,
                    "wrap": True,
                    "margin": "sm",
                    "size": "md",
                    "color": "#333333"
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
                "text": "💡 關鍵單字：",
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
        
    return bubble


def make_daily_word_flex(item: DailyWordItem) -> dict:
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
                    "type": "box",
                    "layout": "horizontal",
                    "alignItems": "center",
                    "contents": [
                        {
                            "type": "text",
                            "text": item.word,
                            "weight": "bold",
                            "size": "xl",
                            "color": "#111111",
                            "flex": 8
                        },
                        {
                            "type": "button",
                            "action": {
                                "type": "message",
                                "label": "🔊 發音",
                                "text": f"發音: {item.word}"
                            },
                            "style": "secondary",
                            "height": "sm",
                            "flex": 3
                        }
                    ]
                },
                {
                    "type": "text",
                    "text": f"中文意思：{item.meaning}",
                    "margin": "md",
                    "size": "md",
                    "weight": "bold",
                    "color": "#333333"
                },
                {
                    "type": "separator",
                    "margin": "md"
                },
                {
                    "type": "text",
                    "text": "📝 實用例句：",
                    "weight": "bold",
                    "size": "sm",
                    "color": "#8c8c8c",
                    "margin": "md"
                },
                {
                    "type": "text",
                    "text": item.example,
                    "wrap": True,
                    "margin": "xs",
                    "size": "sm",
                    "color": "#555555",
                    "style": "italic"
                }
            ]
        }
    }


def make_pronunciation_flex(result: PronunciationResult) -> dict:
    return {
        "type": "bubble",
        "header": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": "#17A2B8",
            "contents": [
                {
                    "type": "text",
                    "text": "🔊 單字發音與解析",
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
                    "type": "box",
                    "layout": "horizontal",
                    "contents": [
                        {
                            "type": "text",
                            "text": result.word,
                            "weight": "bold",
                            "size": "xl",
                            "color": "#111111",
                            "flex": 7
                        },
                        {
                            "type": "text",
                            "text": f"[{result.part_of_speech}]",
                            "color": "#666666",
                            "size": "sm",
                            "align": "end",
                            "gravity": "center",
                            "flex": 3
                        }
                    ]
                },
                {
                    "type": "box",
                    "layout": "vertical",
                    "margin": "md",
                    "contents": [
                        {
                            "type": "text",
                            "text": f"🇬🇧 英式 IPA: {result.ipa_uk}",
                            "size": "xs",
                            "color": "#555555"
                        },
                        {
                            "type": "text",
                            "text": f"🇺🇸 美式 IPA: {result.ipa_us}",
                            "size": "xs",
                            "color": "#555555",
                            "margin": "xs"
                        }
                    ]
                },
                {
                    "type": "separator",
                    "margin": "md"
                },
                {
                    "type": "text",
                    "text": "📖 中文釋義：",
                    "weight": "bold",
                    "size": "sm",
                    "color": "#8c8c8c",
                    "margin": "md"
                },
                {
                    "type": "text",
                    "text": result.meaning,
                    "wrap": True,
                    "size": "md",
                    "weight": "bold",
                    "color": "#333333"
                },
                {
                    "type": "text",
                    "text": "💡 用法與補充：",
                    "weight": "bold",
                    "size": "sm",
                    "color": "#8c8c8c",
                    "margin": "md"
                },
                {
                    "type": "text",
                    "text": result.detail,
                    "wrap": True,
                    "size": "sm",
                    "color": "#555555"
                }
            ]
        }
    }


def make_vocab_added_flex(category: str, word: str, meaning: str) -> dict:
    return {
        "type": "bubble",
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "box",
                    "layout": "horizontal",
                    "alignItems": "center",
                    "contents": [
                        {
                            "type": "text",
                            "text": "✨ 單字已成功入庫！",
                            "weight": "bold",
                            "size": "md",
                            "color": "#28A745",
                            "flex": 8
                        }
                    ]
                },
                {
                    "type": "separator",
                    "margin": "md"
                },
                {
                    "type": "box",
                    "layout": "horizontal",
                    "margin": "md",
                    "contents": [
                        {
                            "type": "text",
                            "text": "分類",
                            "color": "#8c8c8c",
                            "size": "sm",
                            "flex": 3
                        },
                        {
                            "type": "text",
                            "text": category,
                            "weight": "bold",
                            "color": "#333333",
                            "size": "sm",
                            "flex": 7
                        }
                    ]
                },
                {
                    "type": "box",
                    "layout": "horizontal",
                    "margin": "sm",
                    "contents": [
                        {
                            "type": "text",
                            "text": "單字",
                            "color": "#8c8c8c",
                            "size": "sm",
                            "flex": 3
                        },
                        {
                            "type": "text",
                            "text": word,
                            "weight": "bold",
                            "color": "#007BFF",
                            "size": "sm",
                            "flex": 7
                        }
                    ]
                },
                {
                    "type": "box",
                    "layout": "horizontal",
                    "margin": "sm",
                    "contents": [
                        {
                            "type": "text",
                            "text": "中文意思",
                            "color": "#8c8c8c",
                            "size": "sm",
                            "flex": 3
                        },
                        {
                            "type": "text",
                            "text": meaning,
                            "weight": "bold",
                            "color": "#333333",
                            "size": "sm",
                            "flex": 7
                        }
                    ]
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
                    "style": "primary",
                    "height": "sm",
                    "color": "#007BFF",
                    "action": {
                        "type": "message",
                        "label": "🔊 發音",
                        "text": f"發音: {word}"
                    }
                },
                {
                    "type": "button",
                    "style": "secondary",
                    "height": "sm",
                    "action": {
                        "type": "message",
                        "label": "📚 查看單字庫",
                        "text": "記憶查詢"
                    }
                }
            ]
        }
    }


def make_vocab_list_flex(rows: list, category: str | None) -> dict:
    title = f"📚 我的單字庫 ({category})" if category else "📚 我的單字庫 (最近 15 筆)"
    
    vocab_contents = []
    
    if not rows:
        return {
            "type": "bubble",
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": title,
                        "weight": "bold",
                        "size": "md",
                        "color": "#111111"
                    },
                    {
                        "type": "text",
                        "text": "目前沒有任何詞彙記錄喔！可以輸入以下格式新增：\n記憶新增: 分類|單字|中文意思",
                        "wrap": True,
                        "color": "#8c8c8c",
                        "size": "sm",
                        "margin": "md"
                    }
                ]
            }
        }
        
    for index, r in enumerate(rows):
        if index > 0:
            vocab_contents.append({
                "type": "separator",
                "margin": "sm"
            })
            
        vocab_contents.append({
            "type": "box",
            "layout": "horizontal",
            "margin": "sm",
            "alignItems": "center",
            "contents": [
                {
                    "type": "box",
                    "layout": "vertical",
                    "backgroundColor": "#E8F0FE",
                    "cornerRadius": "md",
                    "paddingAll": "2px",
                    "alignItems": "center",
                    "justifyContent": "center",
                    "flex": 3,
                    "contents": [
                        {
                            "type": "text",
                            "text": r.get('category', ''),
                            "size": "xxs",
                            "color": "#1A73E8",
                            "weight": "bold",
                            "maxLines": 1
                        }
                    ]
                },
                {
                    "type": "text",
                    "text": r.get('word', ''),
                    "weight": "bold",
                    "color": "#333333",
                    "size": "sm",
                    "margin": "md",
                    "flex": 4,
                    "maxLines": 1
                },
                {
                    "type": "text",
                    "text": r.get('meaning', ''),
                    "color": "#666666",
                    "size": "sm",
                    "flex": 4,
                    "maxLines": 1
                },
                {
                    "type": "text",
                    "text": "🔊",
                    "align": "end",
                    "size": "sm",
                    "action": {
                        "type": "message",
                        "label": "發音",
                        "text": f"發音: {r.get('word', '')}"
                    },
                    "flex": 1
                }
            ]
        })
        
    return {
        "type": "bubble",
        "header": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": "#1A73E8",
            "contents": [
                {
                    "type": "text",
                    "text": title,
                    "color": "#ffffff",
                    "weight": "bold",
                    "size": "md"
                }
            ]
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "spacing": "sm",
            "contents": vocab_contents
        }
    }


def make_image_analysis_flex(result: ImageAnalysisResult, saved_count: int) -> dict:
    vocab_contents = []
    for item in result.vocab_list:
        vocab_contents.append({
            "type": "box",
            "layout": "horizontal",
            "margin": "sm",
            "alignItems": "center",
            "contents": [
                {
                    "type": "box",
                    "layout": "vertical",
                    "backgroundColor": "#E1F5FE",
                    "cornerRadius": "md",
                    "paddingAll": "2px",
                    "alignItems": "center",
                    "flex": 3,
                    "contents": [
                        {
                            "type": "text",
                            "text": item.category,
                            "size": "xxs",
                            "color": "#0288D1",
                            "weight": "bold"
                        }
                    ]
                },
                {
                    "type": "text",
                    "text": item.word,
                    "weight": "bold",
                    "color": "#333333",
                    "size": "sm",
                    "margin": "md",
                    "flex": 4
                },
                {
                    "type": "text",
                    "text": item.meaning,
                    "color": "#666666",
                    "size": "sm",
                    "flex": 4
                },
                {
                    "type": "text",
                    "text": "🔊",
                    "align": "end",
                    "size": "sm",
                    "action": {
                        "type": "message",
                        "label": "發音",
                        "text": f"發音: {item.word}"
                    },
                    "flex": 1
                }
            ]
        })

    bubble = {
        "type": "bubble",
        "header": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": "#6A1B9A",
            "contents": [
                {
                    "type": "text",
                    "text": "📷 智慧圖片分析",
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
                    "text": "📝 圖片內容描述：",
                    "weight": "bold",
                    "size": "sm",
                    "color": "#8c8c8c"
                },
                {
                    "type": "text",
                    "text": result.description,
                    "wrap": True,
                    "margin": "xs",
                    "size": "sm",
                    "color": "#333333"
                },
                {
                    "type": "separator",
                    "margin": "md"
                },
                {
                    "type": "text",
                    "text": "💡 英語學習重點：",
                    "weight": "bold",
                    "size": "sm",
                    "color": "#8c8c8c",
                    "margin": "md"
                },
                {
                    "type": "text",
                    "text": result.learning_points,
                    "wrap": True,
                    "margin": "xs",
                    "size": "sm",
                    "color": "#333333"
                },
                {
                    "type": "separator",
                    "margin": "md"
                },
                {
                    "type": "text",
                    "text": "📚 相關學習單字：",
                    "weight": "bold",
                    "size": "sm",
                    "color": "#8c8c8c",
                    "margin": "md"
                },
                {
                    "type": "box",
                    "layout": "vertical",
                    "margin": "xs",
                    "contents": vocab_contents
                }
            ]
        }
    }
    
    if saved_count > 0:
        bubble["body"]["contents"].extend([
            {
                "type": "separator",
                "margin": "md"
            },
            {
                "type": "text",
                "text": f"✨ 已自動將這 {saved_count} 個單字存入您的單字庫中！",
                "weight": "bold",
                "size": "xs",
                "color": "#28A745",
                "margin": "md",
                "align": "center"
            }
        ])
        
    return bubble


# === Helper Functions ===

def reply_text(reply_token: str, text: str) -> None:
    with ApiClient(configuration) as api_client:
        line_api = MessagingApi(api_client)
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text=text[:5000])],
            )
        )


def ask_gemini(prompt: str) -> str:
    if not gemini_client:
        return "尚未設定 GEMINI_API_KEY，請先設定。"
    try:
        response = gemini_client.models.generate_content(
            model="gemini-2.5-flash",
            config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT),
            contents=prompt,
        )
        return response.text or "目前無法產生內容，請稍後再試。"
    except Exception as e:
        app.logger.error(f"Gemini generation error: {e}")
        return "Gemini API 呼叫失敗，請確認 API Key 設定。"


def save_chat_history(user_id: str, role: str, content: str):
    if not supabase:
        return
    try:
        data = {
            "user_id": user_id,
            "role": role,
            "content": content,
        }
        supabase.table("chat_history").insert(data).execute()
    except Exception as e:
        app.logger.error(f"Failed to save chat history: {e}")


def ask_gemini_multiturn(user_id: str, prompt: str) -> str:
    if not gemini_client:
        return "尚未設定 GEMINI_API_KEY，請先設定。"

    # 1. 載入歷史
    history_contents = []
    if supabase:
        try:
            rows = (
                supabase.table("chat_history")
                .select("role,content")
                .eq("user_id", user_id)
                .order("id", desc=True)
                .limit(9)
                .execute()
                .data
                or []
            )
            rows.reverse()
            for r in rows:
                role = r["role"]
                content = r["content"]
                history_contents.append(
                    types.Content(role=role, parts=[types.Part.from_text(text=content)])
                )
        except Exception as e:
            app.logger.error(f"Failed to load chat history: {e}")

    # 2. 加入目前的 prompt
    history_contents.append(
        types.Content(role="user", parts=[types.Part.from_text(text=prompt)])
    )

    # 3. 呼叫 Gemini
    try:
        response = gemini_client.models.generate_content(
            model="gemini-2.5-flash",
            config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT),
            contents=history_contents,
        )
        model_reply = response.text or "目前無法產生內容，請稍後再試。"
    except Exception as e:
        app.logger.error(f"Gemini multiturn error: {e}")
        model_reply = "對不起，我現在有點累了，請稍後再試。"

    # 4. 儲存此次對話
    if supabase and model_reply != "對不起，我現在有點累了，請稍後再試。":
        save_chat_history(user_id, "user", prompt)
        save_chat_history(user_id, "model", model_reply)

    return model_reply


def translate_article(text: str) -> TranslationResult | None:
    if not gemini_client:
        return None
    prompt = f"請將以下文章翻譯成繁體中文，並挑選出 3-5 個關鍵詞彙進行解釋。\n\n文章內容：\n{text}"
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
        return None


def conversation_coach(text: str) -> str:
    prompt = (
        "請先修正以下句子的拼字與文法，再提供自然口語版本，"
        "最後給2個可替換說法：\n\n"
        f"{text}"
    )
    return ask_gemini(prompt)


def get_pronunciation_audio(word: str) -> str | None:
    tts_url = (
        "https://translate.google.com/translate_tts?ie=UTF-8&client=tw-ob"
        f"&tl=en&q={quote_plus(word)}"
    )
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        res = requests.get(tts_url, headers=headers, timeout=10)
        if res.status_code == 200:
            filename = f"pron_{uuid.uuid4().hex}.mp3"
            filepath = os.path.join(static_tmp_path, filename)
            with open(filepath, "wb") as f:
                f.write(res.content)
            if SPACE_HOST:
                return f"https://{SPACE_HOST}/audio/{filename}"
    except Exception as e:
        app.logger.error(f"Download TTS audio failed: {e}")
    return None


def word_pronunciation(word: str) -> tuple[PronunciationResult | None, str | None]:
    if not gemini_client:
        return None, None
    prompt = f"請提供單字 {word} 的IPA（英式與美式）、詞性、簡短中文解釋與補充用法。"
    try:
        response = gemini_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=PronunciationResult,
                system_instruction="你是一個英文老師，請一律使用繁體中文（台灣語境）回答。"
            ),
        )
        result: PronunciationResult = response.parsed
        audio_url = get_pronunciation_audio(word)
        return result, audio_url
    except Exception as e:
        app.logger.error(f"Failed to generate pronunciation: {e}")
        return None, None


def add_vocab(user_id: str, category: str, word: str, meaning: str) -> str:
    if not supabase:
        return "尚未設定 Supabase，請先設定 SUPABASE_URL / SUPABASE_KEY。"
    try:
        data = {
            "user_id": user_id,
            "category": category,
            "word": word,
            "meaning": meaning,
        }
        supabase.table("vocab_memory").insert(data).execute()
        return f"已新增單字 `{word}` 到分類 `{category}`。"
    except Exception as e:
        app.logger.error(f"Add vocab failed: {e}")
        return "新增單字失敗，請檢查資料庫連線。"


def list_vocab(user_id: str, category: str | None) -> str:
    if not supabase:
        return "尚未設定 Supabase，請先設定 SUPABASE_URL / SUPABASE_KEY。"
    try:
        query = supabase.table("vocab_memory").select("category,word,meaning").eq("user_id", user_id)
        if category:
            query = query.eq("category", category)
        rows = query.order("id", desc=True).limit(20).execute().data or []
        if not rows:
            return "目前沒有詞彙記錄。"
        lines = [f"- [{r['category']}] {r['word']}：{r['meaning']}" for r in rows]
        return "你的詞彙記憶：\n" + "\n".join(lines)
    except Exception as e:
        app.logger.error(f"List vocab failed: {e}")
        return "無法載入詞彙記憶，請稍後再試。"


def get_vocab_list(user_id: str, category: str | None) -> list:
    if not supabase:
        return []
    try:
        query = supabase.table("vocab_memory").select("category,word,meaning").eq("user_id", user_id)
        if category:
            query = query.eq("category", category)
        rows = query.order("id", desc=True).limit(15).execute().data or []
        return rows
    except Exception as e:
        app.logger.error(f"get_vocab_list failed: {e}")
        return []


def daily_word() -> DailyWordItem | None:
    if supabase:
        try:
            rows = (
                supabase.table("daily_words")
                .select("word,meaning,example")
                .execute()
                .data
                or []
            )
            if rows:
                row = random.choice(rows)
                return DailyWordItem(word=row['word'], meaning=row['meaning'], example=row['example'])
        except Exception as e:
            app.logger.error(f"Failed to fetch daily word from Supabase: {e}")

    if not gemini_client:
        return DailyWordItem(
            word="apple",
            meaning="蘋果",
            example="An apple a day keeps the doctor away. (一天一蘋果，醫生遠離我。)"
        )

    try:
        response = gemini_client.models.generate_content(
            model="gemini-2.5-flash",
            contents="請給我 1 個適合華語使用者學英文的每日單字，含中文意思與英文例句。",
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=DailyWordItem,
                system_instruction="你是一個英文老師，請一律使用繁體中文（台灣語境）回答。"
            ),
        )
        item: DailyWordItem = response.parsed
        # 自動入庫
        if supabase:
            try:
                supabase.table("daily_words").insert({
                    "word": item.word,
                    "meaning": item.meaning,
                    "example": item.example
                }).execute()
            except Exception as e:
                app.logger.error(f"Failed to auto-insert daily word: {e}")
        return item
    except Exception as e:
        app.logger.error(f"Failed to generate daily word: {e}")
        return DailyWordItem(
            word="apple",
            meaning="蘋果",
            example="An apple a day keeps the doctor away. (一天一蘋果，醫生遠離我。)"
        )



# === Flask Routing ===

@app.route("/", methods=["GET"])
def home():
    return {"message": "LINE + Gemini Language Learning Bot"}


@app.route("/healthz", methods=["GET"])
def healthz():
    return {
        "status": "ok",
        "line_secret_set": bool(LINE_CHANNEL_SECRET),
        "line_token_set": bool(LINE_CHANNEL_ACCESS_TOKEN),
        "gemini_key_set": bool(GEMINI_API_KEY),
        "supabase_configured": bool(SUPABASE_URL and SUPABASE_KEY),
        "space_host_set": bool(SPACE_HOST),
    }


@app.route("/images/<filename>", methods=["GET"])
def serve_image(filename: str):
    return send_from_directory(static_tmp_path, filename)


@app.route("/audio/<filename>", methods=["GET"])
def serve_audio(filename: str):
    return send_from_directory(static_tmp_path, filename)


@app.route("/translate", methods=["POST"])
def translate_api():
    data = request.get_json(silent=True) or {}
    text = data.get("text", "").strip()
    target_lang = data.get("target_lang", "繁體中文").strip()
    
    if not text:
        return {"error": "Missing 'text' field in request body."}, 400
        
    if not gemini_client:
        return {"error": "Gemini API is not configured."}, 500
        
    prompt = f"請將以下文章翻譯成 {target_lang}，並挑選出 3-5 個關鍵詞彙進行解釋。\n\n文章內容：\n{text}"
    
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
        result: TranslationResult = response.parsed
        return {
            "translated_text": result.translated_text,
            "vocabularies": [
                {"word": v.word, "meaning": v.meaning} for v in result.vocabularies
            ]
        }
    except Exception as e:
        app.logger.error(f"Translation API error: {e}")
        return {"error": "Failed to translate article. Please try again later."}, 500


@app.route("/", methods=["POST"])
def callback():
    if not LINE_CHANNEL_SECRET or not LINE_CHANNEL_ACCESS_TOKEN:
        return "LINE Hook credentials are not configured.", 500
    signature = request.headers.get("X-Line-Signature")
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return "OK"


# === User Mode Management ===
user_modes_memory = {}

def get_user_mode(user_id: str) -> str:
    if supabase:
        try:
            res = supabase.table("user_states").select("mode").eq("user_id", user_id).execute()
            if res.data:
                return res.data[0]["mode"]
        except Exception as e:
            app.logger.warning(f"Failed to get user mode from Supabase: {e}. Fallback to memory.")
    return user_modes_memory.get(user_id, "general")

def set_user_mode(user_id: str, mode: str):
    user_modes_memory[user_id] = mode
    if supabase:
        try:
            supabase.table("user_states").upsert({"user_id": user_id, "mode": mode}).execute()
        except Exception as e:
            app.logger.warning(f"Failed to set user mode in Supabase: {e}. Saved in memory.")

# === Sub-handlers for each feature ===

def do_translation(event, article: str):
    result = translate_article(article)
    if result:
        flex_content = make_translation_flex(result)
        with ApiClient(configuration) as api_client:
            line_api = MessagingApi(api_client)
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[FlexMessage(alt_text="翻譯與單字解析", contents=FlexContainer.from_json(json.dumps(flex_content)))],
                )
            )
    else:
        reply_text(event.reply_token, "翻譯失敗，請稍後再試。")

def do_conversation(event, user_id: str, practice_sentence: str):
    output = ask_gemini_multiturn(user_id, practice_sentence)
    reply_text(event.reply_token, output)

def do_pronunciation(event, word: str):
    result, audio_url = word_pronunciation(word)
    messages = []
    if result:
        flex_content = make_pronunciation_flex(result)
        messages.append(FlexMessage(alt_text=f"發音與解析: {word}", contents=FlexContainer.from_json(json.dumps(flex_content))))
    else:
        messages.append(TextMessage(text=f"無法查詢單字 {word}，但已為您產出發音語音。"))
        
    if audio_url:
        messages.append(
            AudioMessage(
                original_content_url=audio_url,
                duration=2000
            )
        )
    
    with ApiClient(configuration) as api_client:
        line_api = MessagingApi(api_client)
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=messages,
            )
        )

def do_vocab_add(event, user_id: str, raw_input: str):
    parts = [x.strip() for x in raw_input.split("|")]
    if len(parts) != 3:
        reply_text(event.reply_token, "格式錯誤！請依照格式輸入：\n分類|單字|中文意思\n例如：食物|apple|蘋果")
        return
    
    category, word, meaning = parts[0], parts[1], parts[2]
    res_text = add_vocab(user_id, category, word, meaning)
    
    if "已新增單字" in res_text:
        flex_content = make_vocab_added_flex(category, word, meaning)
        with ApiClient(configuration) as api_client:
            line_api = MessagingApi(api_client)
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[FlexMessage(alt_text="單字已成功入庫", contents=FlexContainer.from_json(json.dumps(flex_content)))],
                )
            )
    else:
        reply_text(event.reply_token, res_text)

def do_vocab_query(event, user_id: str, category: str = None, send_prompt: bool = False):
    if not supabase:
        reply_text(event.reply_token, "尚未設定 Supabase，請先設定 SUPABASE_URL / SUPABASE_KEY。")
        return
        
    rows = get_vocab_list(user_id, category)
    flex_content = make_vocab_list_flex(rows, category)
    
    messages = [FlexMessage(alt_text="我的單字庫", contents=FlexContainer.from_json(json.dumps(flex_content)))]
    if send_prompt:
        prompt_text = (
            "已切換至【記憶查詢】模式 🔍\n"
            "請輸入您想查詢的單字分類（例如：食物、動物），或輸入『全部』列出所有單字。\n\n"
            "💡 若要回到一般聊天，請輸入「退出」或「一般聊天」。"
        )
        messages.append(TextMessage(text=prompt_text))
        
    with ApiClient(configuration) as api_client:
        line_api = MessagingApi(api_client)
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=messages,
            )
        )

def do_daily_word(event, send_prompt: bool = False):
    item = daily_word()
    if item:
        flex_content = make_daily_word_flex(item)
        messages = [FlexMessage(alt_text="每日單字", contents=FlexContainer.from_json(json.dumps(flex_content)))]
        if send_prompt:
            prompt_text = (
                "已切換至【每日單字】模式 📅\n"
                "點擊或輸入任何字，將為您推薦下一個每日單字。\n\n"
                "💡 若要回到一般聊天，請輸入「退出」或「一般聊天」。"
            )
            messages.append(TextMessage(text=prompt_text))
            
        with ApiClient(configuration) as api_client:
            line_api = MessagingApi(api_client)
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=messages,
                )
            )
    else:
        reply_text(event.reply_token, "無法獲取每日單字，請稍後再試。")

# === LINE Message Handlers ===

MODE_MAPPING = {
    "翻譯": "translation",
    "記憶新增": "vocab_add",
    "記憶查詢": "vocab_query",
    "每日單字": "daily_word",
    "會話": "conversation",
    "發音": "pronunciation",
    "退出": "general",
    "一般聊天": "general",
    "一般": "general",
    "結束": "general",
}

@handler.add(MessageEvent, message=TextMessageContent)
def handle_text_message(event):
    user_id = getattr(event.source, "user_id", "anonymous")
    user_input = event.message.text.strip()

    # 1. 檢查是否為功能切換關鍵字
    if user_input in MODE_MAPPING:
        target_mode = MODE_MAPPING[user_input]
        set_user_mode(user_id, target_mode)
        
        if target_mode == "translation":
            reply_text(
                event.reply_token,
                "已切換至【翻譯】模式 📝\n"
                "請直接輸入要翻譯的文字或文章，我會為您翻譯並解析關鍵單字！\n\n"
                "💡 若要回到一般聊天，請輸入「退出」或「一般聊天」。"
            )
        elif target_mode == "vocab_add":
            reply_text(
                event.reply_token,
                "已切換至【記憶新增】模式 💾\n"
                "請輸入您想新增的單字，格式如下：\n"
                "分類|單字|中文意思\n"
                "例如：`食物|apple|蘋果`\n\n"
                "💡 若要回到一般聊天，請輸入「退出」或「一般聊天」。"
            )
        elif target_mode == "vocab_query":
            # 切換時，直接幫他查詢全部，並附上提示文字
            do_vocab_query(event, user_id, category=None, send_prompt=True)
        elif target_mode == "daily_word":
            # 切換時，直接幫他出一個每日單字，並附上提示文字
            do_daily_word(event, send_prompt=True)
        elif target_mode == "conversation":
            reply_text(
                event.reply_token,
                "已切換至【會話】模式 🗣️\n"
                "請輸入您想練習或聊天的內容，我會以英文跟您進行會話練習！\n\n"
                "💡 若要回到一般聊天，請輸入「退出」或「一般聊天」。"
            )
        elif target_mode == "pronunciation":
            reply_text(
                event.reply_token,
                "已切換至【發音】模式 🔊\n"
                "請直接輸入欲查詢發音的英文單字，我會為您查詢發音與發音語音檔！\n\n"
                "💡 若要回到一般聊天，請輸入「退出」或「一般聊天」。"
            )
        else: # general
            reply_text(
                event.reply_token,
                "已回到【一般聊天】模式 💬\n"
                "現在您可以與我隨意對話，或隨時點選選單切換至其他功能。"
            )
        return

    # 2. 若非切換關鍵字，根據當前模式執行
    current_mode = get_user_mode(user_id)
    
    if current_mode == "translation":
        do_translation(event, user_input)
    elif current_mode == "vocab_add":
        do_vocab_add(event, user_id, user_input)
    elif current_mode == "vocab_query":
        category = None if user_input in ["全部", "all", "全部單字"] else user_input
        do_vocab_query(event, user_id, category=category)
    elif current_mode == "daily_word":
        do_daily_word(event)
    elif current_mode == "conversation":
        do_conversation(event, user_id, user_input)
    elif current_mode == "pronunciation":
        do_pronunciation(event, user_input)
    else: # general / None
        # 一般聊天直接使用多輪會話功能
        output = ask_gemini_multiturn(user_id, user_input)
        reply_text(event.reply_token, output)



@handler.add(MessageEvent, message=ImageMessageContent)
def handle_image_message(event):
    user_id = getattr(event.source, "user_id", "anonymous")
    with ApiClient(configuration) as api_client:
        blob_api = MessagingApiBlob(api_client)
        image_data = blob_api.get_message_content(message_id=event.message.id)

    with tempfile.NamedTemporaryFile(dir=static_tmp_path, suffix=".jpg", delete=False) as tmp:
        tmp.write(image_data)
        local_path = tmp.name

    if not gemini_client:
        reply_text(event.reply_token, "Gemini API 未設定，無法理解圖片。")
        return

    try:
        image = Image.open(local_path)
        response = gemini_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[image, "請分析這張圖片，詳細描述內容、教導適合學生的關鍵學習點，並列出 5 個與圖片直接相關 of 英文單字。"],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=ImageAnalysisResult,
                system_instruction="你是英文語言學習老師。請使用繁體中文（台灣習慣用語）描述圖片，並教導 5 個英文單字。"
            )
        )
        result: ImageAnalysisResult = response.parsed
        
        # 自動儲存這 5 個單字到 Supabase
        saved_count = 0
        if supabase and result.vocab_list:
            for item in result.vocab_list:
                try:
                    supabase.table("vocab_memory").insert({
                        "user_id": user_id,
                        "category": item.category,
                        "word": item.word,
                        "meaning": item.meaning
                    }).execute()
                    saved_count += 1
                except Exception as e:
                    app.logger.error(f"Failed to auto-save image vocab: {e}")

        # 組合回覆
        flex_content = make_image_analysis_flex(result, saved_count)
        with ApiClient(configuration) as api_client:
            line_api = MessagingApi(api_client)
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[FlexMessage(alt_text="圖片分析與學習結果", contents=FlexContainer.from_json(json.dumps(flex_content)))],
                )
            )
    except Exception as e:
        app.logger.error(f"Image analysis failed: {e}")
        reply_text(event.reply_token, "圖片理解失敗，請稍後再試。")


# === 自動初始化 Rich Menu ===
try:
    from init_rich_menu import init_rich_menu
    # 僅在載入此模組時嘗試初始化一次，避免每次 Webhook 呼叫都執行。
    # 這會在應用啟動時被執行。
    init_rich_menu()
except Exception as e:
    app.logger.warning(f"Auto-initializing rich menu failed: {e}")

