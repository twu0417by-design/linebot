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
import re
from google import genai
from google.genai import types
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    MessagingApiBlob,
    ReplyMessageRequest,
    TextMessage,
    ImageMessage,
    AudioMessage,
    FlexMessage,
    FlexContainer,
    PushMessageRequest,
    QuickReply,
    QuickReplyItem,
    MessageAction,
)
from linebot.v3.webhooks import ImageMessageContent, MessageEvent, TextMessageContent, FollowEvent
from supabase import Client, create_client
from pydantic import BaseModel, Field
from typing import List

SYSTEM_PROMPT = """
你是繁體中文語言學習助教。你的回答必須精準、簡潔，並且可以直接供學習使用。
對於使用者的翻譯、文法修正、會話演練等要求，請使用條列式（分點）輸出，並對重點單字或文法附上 1~2 個例句。
請一律使用繁體中文（台灣習慣用語，例如：請用『影片』而非『視頻』，『軟體』而非『軟件』，『螢幕』而非『屏幕』）。
"""

CONVERSATION_SYSTEM_PROMPT = """
你是一位親切的英語會話教練。請與使用者進行一問一答的英文對話練習。

請遵循以下規則：
1. 【拼字與文法檢查】：
   - 仔細檢查使用者剛剛輸入的英文句子。
   - 如果使用者有任何文法錯誤、拼字錯誤或不自然的表達：
     請在回覆的最開頭，使用「📌 拼字與文法提醒：」標籤，並用親切、易懂的繁體中文（台灣習慣用語）說明錯誤在哪裡，並提供修正後的句子。
     例如：
     📌 拼字與文法提醒：
     - "I has a book" 應改為 "I have a book"（動詞 have 要配合第一人稱 I）。
   - 如果完全沒有錯誤，請直接進行步驟 2 的英文對話，千萬不要顯示任何提醒標籤，也不要說 "Your sentence is correct" 等贅詞。

2. 【一問一答對話】：
   - 請用自然、口語的「英文」回應使用者剛才的話。
   - 回覆內容請控制在 2-4 句話內，保持簡潔易懂。
   - 在你的英文回覆結尾，必須問使用者一個相關的簡單英文問題，引導使用者回答，以維持一問一答的對話流程。
"""

QUIZ_SYSTEM_PROMPT = """
你是一個客觀、簡潔的測驗系統。
出題時：請直接根據提供的單字或範圍，出 3 題英文選擇題測驗（克漏字或意思選擇），並提供 4 個選項 (A/B/C/D)。
批改時：使用者會直接輸入三個英文字母作為答案（例如：ABC 或 bca）。請直接比對答案，並計算答對題數，然後簡潔地給出每一題的解答與原因。絕對不需要任何多餘的老師口吻、寒暄或冗長的鼓勵對話。
請一律使用繁體中文。
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
class SupabaseWrapper:
    def __init__(self, url, key):
        self.url = url
        self.key = key
    def table(self, table_name):
        return create_client(self.url, self.key).table(table_name)

supabase = SupabaseWrapper(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None
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
    part_of_speech: str = Field(description="詞性（必須使用英文縮寫，如 n., v., adj., adv.）", default="")
    meaning: str = Field(description="繁體中文意思")
    example: str = Field(description="英文例句，並附上中文翻譯，例如: 'This is an apple. (這是一個蘋果。)'")


class UrlSummaryResult(BaseModel):
    title: str = Field(description="文章或網頁的標題")
    summary: str = Field(description="網頁內容的繁體中文重點摘要，約 50-100 字")
    vocab_list: List[VocabItem] = Field(description="從該網頁內容中挑選出的 5 個進階英文單字")


class GrammarPoint(BaseModel):
    rule: str = Field(description="文法規則名稱或標題，例如：現在完成式、關係代名詞")
    explanation: str = Field(description="詳細的繁體中文解釋與用法解析")

class GrammarAnalysisResult(BaseModel):
    sentence: str = Field(description="原句")
    translation: str = Field(description="整句的繁體中文翻譯")
    structure: str = Field(description="句子結構拆解，例如：主詞(I)+動詞(have)+受詞(apple)")
    grammar_points: List[GrammarPoint] = Field(description="這句話中值得學習的重要文法觀念")


class QuizOption(BaseModel):
    label: str = Field(description="選項代號 (A/B/C/D)")
    text: str = Field(description="選項內容")

class QuizQuestion(BaseModel):
    number: int = Field(description="題號 (1, 2, 3)")
    question: str = Field(description="題目句子，需填空處用 ___ 表示")
    options: List[QuizOption] = Field(description="四個選項")
    answer: str = Field(description="正確答案代號 (A/B/C/D)")
    explanation: str = Field(description="繁體中文詳解")

class QuizGenerationResult(BaseModel):
    title: str = Field(description="測驗標題，例如：多益單字測驗")
    article: str = Field(description="閱讀測驗的短文內容，若是閱讀測驗請務必輸出超過50字的英文短文，若非閱讀測驗請一定要輸出空字串 \"\"")
    questions: List[QuizQuestion]

class QuizGradingResult(BaseModel):
    score_text: str = Field(description="分數標題，例如：答對 2/3 題！")
    feedback: str = Field(description="總體鼓勵與回饋，約 20 字")
    details: List[str] = Field(description="每一題的正確解答與使用者的錯誤糾正")


class TranslationVocabItem(BaseModel):
    word: str = Field(description="文章中的關鍵英文單字或片語")
    meaning: str = Field(description="該單字或片語的中文解釋")


class TranslationResult(BaseModel):
    is_word: bool = Field(description="輸入的內容是否為單一單字")
    original_text: str = Field(description="原文章段落或句子（若輸入為文章才填）", default="")
    translated_text: str = Field(description="文章中文翻譯（若輸入為文章才填）", default="")
    vocabularies: List[TranslationVocabItem] = Field(description="文章中挑選出的 3-5 個關鍵詞彙與解釋（若輸入為文章才填）", default_factory=list)
    word: str = Field(description="原單字（若輸入為單字才填）", default="")
    word_meaning: str = Field(description="單字中文意思（若輸入為單字才填）", default="")
    part_of_speech: str = Field(description="詞性（必須使用英文縮寫，如 n., v., adj.，若輸入為單字才填）", default="")
    example_sentence: str = Field(description="英文例句與其中文翻譯（若輸入為單字才填）", default="")


class PronunciationResult(BaseModel):
    word: str = Field(description="英文單字")
    ipa_uk: str = Field(description="英式 IPA，例如: /əˈsəʊ.si.eɪt/")
    ipa_us: str = Field(description="美式 IPA，例如: /əˈsoʊ.ʃi.eɪt/")
    part_of_speech: str = Field(description="詞性（必須使用英文縮寫，如 n., v., adj.，有多個請用逗號隔開）")
    meaning: str = Field(description="中文解釋，有多個意思請簡短列出")
    detail: str = Field(description="詳細用法、常見片語或小叮嚀（約50字）")


# === Flex Message Generators ===

def make_quiz_generation_flex(result: QuizGenerationResult) -> dict:
    body_contents = [
        {
            "type": "text",
            "text": result.title,
            "weight": "bold",
            "size": "xl",
            "color": "#111111"
        },
        {
            "type": "separator",
            "margin": "md"
        }
    ]
    if hasattr(result, "article") and result.article:
        body_contents.append({
            "type": "text",
            "text": result.article,
            "wrap": True,
            "size": "sm",
            "color": "#444444",
            "margin": "md",
            "weight": "bold"
        })
        body_contents.append({
            "type": "separator",
            "margin": "md"
        })
    
    for q in result.questions:
        body_contents.append(
            {
                "type": "text",
                "text": f"Q{q.number}. {q.question}",
                "weight": "bold",
                "wrap": True,
                "margin": "md",
                "color": "#007BFF"
            }
        )
        for opt in q.options:
            body_contents.append(
                {
                    "type": "text",
                    "text": f"({opt.label}) {opt.text}",
                    "wrap": True,
                    "size": "sm",
                    "color": "#555555"
                }
            )
        body_contents.append(
            {
                "type": "separator",
                "margin": "md"
            }
        )
        
    body_contents.append(
        {
            "type": "text",
            "text": "💡 請直接輸入三個英文字母作為答案 (例如：ABC)",
            "size": "sm",
            "color": "#8c8c8c",
            "margin": "md",
            "wrap": True
        }
    )

    return {
        "type": "bubble",
        "size": "mega",
        "header": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": "#FFC107",
            "contents": [
                {
                    "type": "text",
                    "text": "🎓 隨堂測驗",
                    "color": "#ffffff",
                    "weight": "bold",
                    "size": "md"
                }
            ]
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": body_contents
        }
    }

def make_quiz_grading_flex(result: QuizGradingResult) -> dict:
    contents = [
        {
            "type": "text",
            "text": result.score_text,
            "weight": "bold",
            "size": "xl",
            "color": "#E83E8C"
        },
        {
            "type": "text",
            "text": result.feedback,
            "wrap": True,
            "margin": "sm",
            "color": "#666666"
        },
        {
            "type": "separator",
            "margin": "md"
        }
    ]
    for d in result.details:
        contents.append({
            "type": "text",
            "text": "📌 " + d,
            "wrap": True,
            "size": "sm",
            "margin": "md",
            "color": "#333333"
        })
        
    return {
        "type": "bubble",
        "size": "mega",
        "header": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": "#28A745",
            "contents": [
                {
                    "type": "text",
                    "text": "✅ 測驗批改結果",
                    "color": "#ffffff",
                    "weight": "bold",
                    "size": "md"
                }
            ]
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": contents
        }
    }


def make_grammar_flex(result: GrammarAnalysisResult) -> dict:
    grammar_contents = []
    for g in result.grammar_points:
        grammar_contents.extend([
            {
                "type": "text",
                "text": f"📌 {g.rule}",
                "weight": "bold",
                "size": "sm",
                "color": "#007BFF",
                "margin": "md"
            },
            {
                "type": "text",
                "text": g.explanation,
                "wrap": True,
                "size": "sm",
                "color": "#333333",
                "margin": "xs"
            }
        ])

    return {
        "type": "bubble",
        "size": "mega",
        "header": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": "#6f42c1",
            "paddingAll": "15px",
            "contents": [
                {
                    "type": "text",
                    "text": "📖 文法拆解與分析",
                    "color": "#ffffff",
                    "weight": "bold",
                    "size": "md"
                }
            ]
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "paddingAll": "20px",
            "contents": [
                {
                    "type": "text",
                    "text": result.sentence,
                    "weight": "bold",
                    "size": "md",
                    "wrap": True,
                    "color": "#111111",
                    "style": "italic"
                },
                {
                    "type": "separator",
                    "margin": "lg"
                },
                {
                    "type": "text",
                    "text": "📝 中文翻譯：",
                    "weight": "bold",
                    "size": "sm",
                    "color": "#8c8c8c",
                    "margin": "md"
                },
                {
                    "type": "text",
                    "text": result.translation,
                    "wrap": True,
                    "margin": "sm",
                    "size": "md",
                    "color": "#333333"
                },
                {
                    "type": "separator",
                    "margin": "lg"
                },
                {
                    "type": "text",
                    "text": "🧩 結構拆解：",
                    "weight": "bold",
                    "size": "sm",
                    "color": "#8c8c8c",
                    "margin": "md"
                },
                {
                    "type": "text",
                    "text": result.structure,
                    "wrap": True,
                    "margin": "sm",
                    "size": "sm",
                    "color": "#E83E8C",
                    "weight": "bold"
                },
                {
                    "type": "separator",
                    "margin": "lg"
                }
            ] + grammar_contents
        }
    }


def make_url_summary_flex(result: UrlSummaryResult, url: str) -> dict:
    vocab_contents = []
    for v in result.vocab_list:
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
                    "text": f"{v.meaning} ({v.category})",
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
        
    return {
        "type": "bubble",
        "size": "mega",
        "header": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": "#FF5722",
            "paddingAll": "15px",
            "contents": [
                {
                    "type": "text",
                    "text": "🔗 網頁重點摘要",
                    "color": "#ffffff",
                    "weight": "bold",
                    "size": "md"
                }
            ]
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "paddingAll": "20px",
            "contents": [
                {
                    "type": "text",
                    "text": result.title,
                    "weight": "bold",
                    "size": "md",
                    "wrap": True,
                    "color": "#111111"
                },
                {
                    "type": "separator",
                    "margin": "lg"
                },
                {
                    "type": "text",
                    "text": "📝 摘要：",
                    "weight": "bold",
                    "size": "sm",
                    "color": "#8c8c8c",
                    "margin": "md"
                },
                {
                    "type": "text",
                    "text": result.summary,
                    "wrap": True,
                    "margin": "sm",
                    "size": "sm",
                    "color": "#333333"
                },
                {
                    "type": "separator",
                    "margin": "lg"
                },
                {
                    "type": "text",
                    "text": "💡 必學單字 (已存入單字庫)：",
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
            ]
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "button",
                    "style": "link",
                    "action": {
                        "type": "uri",
                        "label": "開啟原始網頁",
                        "uri": url
                    },
                    "color": "#007BFF"
                }
            ]
        }
    }


def make_general_chat_flex(user_input: str, reply_text: str) -> dict:
    return {
        "type": "bubble",
        "size": "mega",
        "header": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": "#2B3A4C",
            "paddingAll": "15px",
            "contents": [
                {
                    "type": "text",
                    "text": "✨ AI 語言助教",
                    "color": "#FFFFFF",
                    "weight": "bold",
                    "size": "md"
                }
            ]
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "paddingAll": "20px",
            "contents": [
                {
                    "type": "box",
                    "layout": "horizontal",
                    "contents": [
                        {
                            "type": "text",
                            "text": "💬",
                            "size": "sm",
                            "flex": 1
                        },
                        {
                            "type": "text",
                            "text": user_input,
                            "wrap": True,
                            "size": "sm",
                            "color": "#8c8c8c",
                            "weight": "bold",
                            "flex": 9
                        }
                    ]
                },
                {
                    "type": "separator",
                    "margin": "lg",
                    "color": "#EEEEEE"
                },
                {
                    "type": "text",
                    "text": reply_text,
                    "wrap": True,
                    "margin": "lg",
                    "size": "md",
                    "color": "#333333"
                }
            ]
        }
    }


def make_translation_flex(result: TranslationResult) -> dict:
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
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "button",
                    "style": "primary",
                    "color": "#1DB446",
                    "action": {
                        "type": "message",
                        "label": "💾 加入單字庫",
                        "text": f"記憶新增快捷: 發音收藏|{result.word}|{result.meaning}"
                    }
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



def make_category_carousel_flex(categories: list) -> dict:
    if not categories:
        return {
            "type": "bubble",
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {"type": "text", "text": "📚 我的單字庫", "weight": "bold", "size": "md"},
                    {"type": "text", "text": "目前還沒有任何分類喔！", "wrap": True, "size": "sm", "color": "#8c8c8c", "margin": "md"}
                ]
            }
        }
    
    bubbles = []
    # Always add an "All" option
    bubbles.append({
        "type": "bubble",
        "size": "nano",
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {"type": "text", "text": "全部單字", "weight": "bold", "size": "md", "align": "center"}
            ],
            "justifyContent": "center",
            "alignItems": "center"
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "button",
                    "style": "primary",
                    "color": "#1DB446",
                    "action": {"type": "message", "label": "查看", "text": "全部"}
                }
            ]
        }
    })
    
    for cat in categories[:9]:  # limit to 10 bubbles total
        bubbles.append({
            "type": "bubble",
            "size": "nano",
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {"type": "text", "text": cat, "weight": "bold", "size": "md", "align": "center", "wrap": True}
                ],
                "justifyContent": "center",
                "alignItems": "center"
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "spacing": "sm",
                "contents": [
                    {
                        "type": "button",
                        "style": "secondary",
                        "action": {"type": "message", "label": "查看", "text": f"{cat}"}
                    },
                    {
                        "type": "button",
                        "style": "primary",
                        "color": "#FF4D4F",
                        "action": {"type": "message", "label": "刪除", "text": f"刪除分類: {cat}"}
                    }
                ]
            }
        })
    return {"type": "carousel", "contents": bubbles}


def make_vocab_list_flex(rows: list, category: str | None) -> dict:
    base_title = f"📚 我的單字庫 ({category})" if category else "📚 我的單字庫"
    
    if not rows:
        return {
            "type": "bubble",
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": base_title,
                        "weight": "bold",
                        "size": "md",
                        "color": "#111111"
                    },
                    {
                        "type": "text",
                        "text": "目前沒有任何詞彙記錄喔！請先切換至「記憶新增」模式，並依照分行格式建立單字庫！",
                        "wrap": True,
                        "color": "#8c8c8c",
                        "size": "sm",
                        "margin": "md"
                    }
                ]
            }
        }
        
    bubbles = []
    chunk_size = 10
    total_pages = (len(rows) - 1) // chunk_size + 1
    
    for i in range(0, len(rows), chunk_size):
        chunk = rows[i:i+chunk_size]
        page_num = (i // chunk_size) + 1
        page_title = base_title if total_pages == 1 else f"{base_title} (第 {page_num}/{total_pages} 頁)"
        
        vocab_contents = []
        for index, r in enumerate(chunk):
            if index > 0:
                vocab_contents.append({
                    "type": "separator",
                    "margin": "sm"
                })
                
            vocab_contents.append({
                "type": "box",
                "layout": "vertical",
                "margin": "sm",
                "contents": [
                    {
                        "type": "box",
                        "layout": "horizontal",
                        "alignItems": "center",
                        "contents": [
                            {
                                "type": "text",
                                "text": "🔊",
                                "align": "start",
                                "size": "sm",
                                "action": {
                                    "type": "message",
                                    "label": "發音",
                                    "text": f"發音: {r.get('word', '')}"
                                },
                                "flex": 1
                            },
                            {
                                "type": "text",
                                "text": r.get('word', ''),
                                "weight": "bold",
                                "color": "#333333",
                                "size": "sm",
                                "flex": 7,
                                "wrap": True
                            },
                            {
                                "type": "text",
                                "text": "🗑️",
                                "align": "end",
                                "size": "sm",
                                "action": {
                                    "type": "message",
                                    "label": "刪除",
                                    "text": f"刪除單字: {r.get('word', '')}"
                                },
                                "flex": 1
                            }
                        ]
                    },
                    {
                        "type": "text",
                        "text": r.get('meaning', ''),
                        "color": "#666666",
                        "size": "sm",
                        "wrap": True,
                        "margin": "sm"
                    }
                ]
            })
            
        bubbles.append({
            "type": "bubble",
            "header": {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": "#1A73E8",
                "contents": [
                    {
                        "type": "text",
                        "text": page_title,
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
        })
        
    if len(bubbles) == 1:
        return bubbles[0]
    else:
        return {"type": "carousel", "contents": bubbles[:12]}


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
        text_res = response.text or "目前無法產生內容，請稍後再試。"
        return re.sub(r'<think>.*?</think>', '', text_res, flags=re.DOTALL).strip()
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


def ask_gemini_multiturn(user_id: str, prompt: str, system_instruction: str = SYSTEM_PROMPT) -> str:
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
            config=types.GenerateContentConfig(system_instruction=system_instruction),
            contents=history_contents,
        )
        raw_reply = response.text or "目前無法產生內容，請稍後再試。"
        model_reply = re.sub(r'<think>.*?</think>', '', raw_reply, flags=re.DOTALL).strip()
    except Exception as e:
        app.logger.error(f"Gemini multiturn error: {e}")
        try:
            # Retry once on connection failure
            from google.genai import Client
            import os
            new_client = Client(api_key=os.environ.get("GEMINI_API_KEY"))
            response = new_client.models.generate_content(
                model="gemini-2.5-flash",
                config=types.GenerateContentConfig(system_instruction=system_instruction),
                contents=history_contents,
            )
            raw_reply = response.text or "目前無法產生內容，請稍後再試。"
            model_reply = re.sub(r'<think>.*?</think>', '', raw_reply, flags=re.DOTALL).strip()
        except Exception as retry_e:
            app.logger.error(f"Gemini multiturn retry error: {retry_e}")
            model_reply = "對不起，我現在有點累了，請稍後再試。"

    # 4. 儲存此次對話
    if supabase and model_reply != "對不起，我現在有點累了，請稍後再試。":
        save_chat_history(user_id, "user", prompt)
        save_chat_history(user_id, "model", model_reply)

    return model_reply


def translate_article(text: str) -> TranslationResult | None:
    if not gemini_client:
        return None
    prompt = f"請判斷以下輸入是「單一單字」還是「文章/句子」。\n如果是單字，請提供中文意思、詞性、以及一句包含中文翻譯的例句。\n如果是文章或句子，請提供原句、將其翻譯成繁體中文，並挑選出 3-5 個關鍵詞彙進行解釋。\n\n輸入內容：\n{text}"
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
    global supabase
    if not supabase:
        return "尚未設定 Supabase，請先設定 SUPABASE_URL / SUPABASE_KEY。"
    
    data = {
        "user_id": user_id,
        "category": category,
        "word": word,
        "meaning": meaning,
    }
    
    try:
        existing = supabase.table("vocab_memory").select("id").eq("user_id", user_id).eq("word", word).execute().data
        if existing:
            supabase.table("vocab_memory").update({"category": category, "meaning": meaning}).eq("id", existing[0]["id"]).execute()
            return f"單字 `{word}` 已更新並移動到分類 `{category}`。"
        
        supabase.table("vocab_memory").insert(data).execute()
        return f"已新增單字 `{word}` 到分類 `{category}`。"
    except Exception as e:
        error_msg = str(e)
        app.logger.error(f"Add vocab failed: {error_msg}")
        if "duplicate" in error_msg.lower() or "unique constraint" in error_msg.lower() or "conflict" in error_msg.lower():
            return f"單字 `{word}` 已經存在於您的單字庫中囉！"
        return f"新增單字失敗，請檢查資料庫連線。(錯誤細節: {error_msg[:100]})"


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



def delete_vocab(user_id: str, word: str) -> str:
    global supabase
    if not supabase: return "尚未設定 Supabase"
    try:
        supabase.table("vocab_memory").delete().eq("user_id", user_id).eq("word", word).execute()
        return f"已成功刪除單字：{word}"
    except Exception as e:
        app.logger.error(f"Delete vocab failed: {e}")
        return f"刪除單字失敗，請稍後再試。"

def delete_vocab_category(user_id: str, category: str) -> str:
    global supabase
    if not supabase: return "尚未設定 Supabase"
    try:
        supabase.table("vocab_memory").delete().eq("user_id", user_id).eq("category", category).execute()
        return f"已成功刪除分類：{category} (及其所有單字)"
    except Exception as e:
        app.logger.error(f"Delete vocab category failed: {e}")
        return f"刪除分類失敗，請稍後再試。"


def get_vocab_list(user_id: str, category: str | None) -> list:
    if not supabase:
        return []
    try:
        query = supabase.table("vocab_memory").select("category,word,meaning").eq("user_id", user_id)
        if category:
            query = query.eq("category", category)
        rows = query.order("id", desc=True).limit(50).execute().data or []
        return rows
    except Exception as e:
        app.logger.error(f"get_vocab_list failed: {e}")
        return []



def get_vocab_categories(user_id: str) -> list:
    if not supabase:
        return []
    try:
        rows = supabase.table("vocab_memory").select("category").eq("user_id", user_id).execute().data or []
        categories = sorted(list(set(r["category"] for r in rows if r.get("category"))))
        return categories
    except Exception as e:
        app.logger.error(f"get_vocab_categories failed: {e}")
        return []


def daily_word() -> DailyWordItem | None:
    if not gemini_client:
        return DailyWordItem(
            word="apple",
            meaning="蘋果",
            example="An apple a day keeps the doctor away. (一天一蘋果，醫生遠離我。)"
        )

    try:
        response = gemini_client.models.generate_content(
            model="gemini-2.5-flash",
            contents="請隨機給我 1 個適合華語使用者學英文的每日單字（確保每次都不一樣），需包含：單字、詞性、中文意思與英文例句。",
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=DailyWordItem,
                temperature=1.0,
                system_instruction="你是一個英文老師，請一律使用繁體中文（台灣語境）回答。"
            ),
        )
        item: DailyWordItem = parse_gemini_json(response, DailyWordItem)
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


# === Quick Reply Menu ===

def send_quiz_menu(event):
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
                        "action": {"type": "message", "label": "單字題", "text": f"測驗 單字 {s['level']}"}
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
                        "style": "secondary",
                        "action": {"type": "message", "label": "聽寫題", "text": f"測驗 聽寫 {s['level']}"}
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

# === User Mode Management ===
user_modes_memory = {}

typing_quiz_memory = {}

def handle_typing_quiz_start(event, user_id: str, level: str = "單字庫", mode: str = "聽寫"):
    words = []
    if level == "單字庫":
        if not supabase:
            reply_text(event.reply_token, "尚未設定 Supabase")
            return
        try:
            res = supabase.table("vocab_memory").select("word,meaning").eq("user_id", user_id).execute()
            data = res.data or []
            if len(data) < 3:
                reply_text(event.reply_token, "您的單字庫數量不足，請先新增至少 3 個單字再來挑戰喔！")
                return
            import random
            words = random.sample(data, 3)
        except Exception as e:
            app.logger.error(f"Typing quiz fetch error: {e}")
            reply_text(event.reply_token, "發生錯誤，請稍後再試。")
            return
    else:
        try:
            sys_inst = "你是一個英文老師，請一律回覆符合指定難度的英文單字 JSON 陣列。格式為 [{'word': '...', 'meaning': '...'}]"
            class WordGenItem(BaseModel):
                word: str
                meaning: str
            class WordGenList(BaseModel):
                words: List[WordGenItem]
            
            res = gemini_client.models.generate_content(
                model="gemini-2.5-flash",
                contents=f"請隨機給我 3 個「{level}」程度的英文單字。",
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=WordGenList,
                    system_instruction=sys_inst,
                    temperature=1.0
                )
            )
            parsed = parse_gemini_json(res, WordGenList)
            words = [{"word": w.word, "meaning": w.meaning} for w in parsed.words]
        except Exception as e:
            app.logger.error(f"Gemini dictation gen error: {e}")
            reply_text(event.reply_token, "生成測驗失敗，請稍後再試。")
            return

    # If mode is 填空, generate sentences for these words
    if mode == "填空":
        try:
            words_str = ", ".join([w["word"] for w in words])
            class SentenceGenItem(BaseModel):
                sentence_with_blank: str
            class SentenceGenList(BaseModel):
                sentences: List[SentenceGenItem]
                
            res = gemini_client.models.generate_content(
                model="gemini-2.5-flash",
                contents=f"請針對以下 3 個單字，各造一個情境英文句子，並將該單字挖空替換為 ___：{words_str}。請保證按順序回傳 3 個句子。",
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=SentenceGenList,
                    temperature=0.7
                )
            )
            parsed = parse_gemini_json(res, SentenceGenList)
            for i in range(3):
                words[i]["sentence"] = parsed.sentences[i].sentence_with_blank
        except Exception as e:
            app.logger.error(f"Gemini sentence gen error: {e}")
            reply_text(event.reply_token, "生成填空句子失敗，請稍後再試。")
            return

    try:
        typing_quiz_memory[user_id] = {"words": words, "current_idx": 0, "score": 0, "mode": mode}
        
        word_obj = words[0]
        if mode == "聽寫":
            audio_url = get_pronunciation_audio(word_obj["word"])
            messages = [TextMessage(text=f"🎧 第 1 題：請聽語音，並輸入您聽到的英文單字拼寫！\n提示：{word_obj['meaning']}")]
            if audio_url:
                messages.append(AudioMessage(original_content_url=audio_url, duration=2000))
            else:
                messages.append(TextMessage(text="語音產生失敗，此題無法進行。"))
        else: # 填空
            q_text = "\n\n".join([f"📝 第 {i+1} 題：\n題目：{w['sentence']}\n提示：{w['meaning']}" for i, w in enumerate(words)])
            messages = [TextMessage(text=f"【填空測驗】請根據語意填入被挖空的單字！\n請用「換行」分隔 3 題的答案（例如：\napple\nbanana\ncat）\n\n{q_text}")]
            
        with ApiClient(configuration) as api_client:
            line_api = MessagingApi(api_client)
            line_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=messages))
            
    except Exception as e:
        app.logger.error(f"Typing quiz start error: {e}")
        reply_text(event.reply_token, "發生錯誤，請稍後再試。")

def handle_typing_quiz_answer(event, user_id: str, user_input: str):
    state = typing_quiz_memory.get(user_id)
    if not state: return
    idx = state["current_idx"]
    word_obj = state["words"][idx]
    mode = state.get("mode", "聽寫")
    correct_word = word_obj["word"].strip().lower()
    user_ans = user_input.strip().lower()
    
    if mode == "填空":
        user_lines = [line.strip().lower() for line in user_input.split('\n') if line.strip()]
        feedbacks = []
        score = 0
        total = len(state["words"])
        for i, word_obj in enumerate(state["words"]):
            correct_word = word_obj["word"].strip().lower()
            ans = user_lines[i] if i < len(user_lines) else "(未作答)"
            if correct_word in ans: # Allow some leniency, or exact match? Let's exact match or if ans is equal to correct word
                # Wait, what if they write "1. apple"? let's check if correct_word in ans
                if correct_word in ans.replace(".", " ").replace(",", " ").split():
                    score += 1
                    feedbacks.append(f"第 {i+1} 題 ✅ 答對！({word_obj['word']})")
                elif ans == correct_word:
                    score += 1
                    feedbacks.append(f"第 {i+1} 題 ✅ 答對！({word_obj['word']})")
                else:
                    feedbacks.append(f"第 {i+1} 題 ❌ 答錯 (您的答案: {ans}，正確: {word_obj['word']})")
            else:
                feedbacks.append(f"第 {i+1} 題 ❌ 答錯 (您的答案: {ans}，正確: {word_obj['word']})")
                
        feedback_text = "\n".join(feedbacks)
        del typing_quiz_memory[user_id]
        reply_text(event.reply_token, f"批改結果：\n{feedback_text}\n\n🎉 填空測驗結束！您的分數是：{score}/{total} 題。")
        return
    else:
        if user_ans == correct_word:
            state["score"] += 1
            feedback = "✅ 答對了！拼寫完全正確。"
        else:
            feedback = f"❌ 答錯囉！\n您的答案：{user_input}\n正確單字：{word_obj['word']}"
            
        state["current_idx"] += 1
        idx = state["current_idx"]
        
        if idx >= len(state["words"]):
            score = state["score"]
            total = len(state["words"])
            del typing_quiz_memory[user_id]
            reply_text(event.reply_token, f"{feedback}\n\n🎉 {mode}測驗結束！您的分數是：{score}/{total} 題。")
            return
            
        next_word = state["words"][idx]
        
        audio_url = get_pronunciation_audio(next_word["word"])
        messages = [TextMessage(text=f"{feedback}\n\n---\n🎧 第 {idx+1} 題：請聽語音，並輸入正確的單字！\n提示：{next_word['meaning']}")]
        if audio_url:
            messages.append(AudioMessage(original_content_url=audio_url, duration=2000))
            
        with ApiClient(configuration) as api_client:
            line_api = MessagingApi(api_client)
            line_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=messages))
        
    next_word = state["words"][idx]
    audio_url = get_pronunciation_audio(next_word["word"])
    
    messages = [TextMessage(text=f"{feedback}\n\n---\n🎧 第 {idx+1} 題：請聽語音，並輸入正確的單字！\n提示：{next_word['meaning']}")]
    if audio_url:
        messages.append(AudioMessage(original_content_url=audio_url, duration=2000))
        
    with ApiClient(configuration) as api_client:
        line_api = MessagingApi(api_client)
        line_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=messages))


def parse_gemini_json(response, schema_class):
    import re, json
    raw = response.text or ""
    clean = re.sub(r'<think>.*?</think>', '', raw, flags=re.DOTALL).strip()
    clean = clean.replace('```json', '').replace('```', '').strip()
    return schema_class.model_validate_json(clean)

quiz_memory = {}

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

def do_url_summary(event, user_id: str, url: str):
    if not gemini_client:
        reply_text(event.reply_token, "尚未設定 GEMINI_API_KEY，請先設定。")
        return
    try:
        reply_text(event.reply_token, "⏳ 正在讀取網頁並由 AI 摘要中，請稍候...")
        # 抓取網頁
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.content, "html.parser")
        text = soup.get_text(separator="\n", strip=True)[:15000]

        prompt = f"這是一篇來自網頁的內容：\n\n{text}\n\n請根據內容，產生繁體中文的重點摘要，並從中挑選5個進階英文單字。"
        
        response = gemini_client.models.generate_content(
            model="gemini-2.5-flash",
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=UrlSummaryResult,
            ),
            contents=prompt,
        )
        result = response.parsed
        
        # 存入單字庫
        for v in result.vocab_list:
            add_vocab(user_id, v.category, v.word, v.meaning)

        flex_content = make_url_summary_flex(result, url)
        
        with ApiClient(configuration) as api_client:
            line_api = MessagingApi(api_client)
            line_api.push_message(
                PushMessageRequest(
                    to=user_id,
                    messages=[FlexMessage(
                        alt_text="🔗 網頁摘要已完成",
                        contents=FlexContainer.from_json(json.dumps(flex_content))
                    )]
                )
            )
    except Exception as e:
        app.logger.error(f"URL Summary error: {e}")
        with ApiClient(configuration) as api_client:
            line_api = MessagingApi(api_client)
            line_api.push_message(PushMessageRequest(to=user_id, messages=[TextMessage(text="❌ 無法讀取該網址內容或解析失敗，請確認網址是否正確且允許讀取。")]))


def do_grammar_analysis(event, sentence: str):
    if not gemini_client:
        reply_text(event.reply_token, "尚未設定 GEMINI_API_KEY，請先設定。")
        return
    try:
        prompt = f"請幫我分析以下英文句子的文法結構與重點：\n\n{sentence}"
        response = gemini_client.models.generate_content(
            model="gemini-2.5-flash",
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=GrammarAnalysisResult,
            ),
            contents=prompt,
        )
        result = parse_gemini_json(response, GrammarAnalysisResult)
        flex_content = make_grammar_flex(result)
        
        with ApiClient(configuration) as api_client:
            line_api = MessagingApi(api_client)
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[FlexMessage(
                        alt_text="📖 文法拆解完成",
                        contents=FlexContainer.from_json(json.dumps(flex_content))
                    )]
                )
            )
    except Exception as e:
        app.logger.error(f"Grammar analysis error: {e}")
        reply_text(event.reply_token, "文法分析失敗，請檢查句子或稍後再試。")


def do_quiz(event, user_id: str, user_input: str = "", start: bool = False, scope: str = ""):
    if not gemini_client:
        reply_text(event.reply_token, "尚未設定 GEMINI_API_KEY，請先設定。")
        return
        
    if start:
        prompt = ""
        parts = scope.split()
        mode = parts[0] if len(parts) > 0 and parts[0] in ["單字", "選擇", "填空", "閱讀", "聽寫"] else "單字"
        level = parts[1] if len(parts) > 1 and parts[1] in ["初級", "中級", "高級", "單字庫"] else "單字庫"
        
        if mode in ["聽寫", "填空"]:
            handle_typing_quiz_start(event, user_id, level, mode)
            return
            
        if level == "單字庫":
            if supabase:
                try:
                    res = supabase.table("vocab_memory").select("word,meaning").eq("user_id", user_id).execute()
                    data = res.data or []
                    if len(data) < 3:
                        prompt = "使用者單字庫目前單字不足，請幫我隨機出 3 題初中級的英文單字選擇題測驗。"
                    else:
                        words = random.sample(data, 3)
                        words_str = ", ".join([f"{w['word']} ({w['meaning']})" for w in words])
                        if mode == "填空":
                            prompt = f"請用這三個單字作為正確答案，幫我出 3 題英文「句子填空選擇題」：{words_str}。每題都必須有一個挖空的句子讓使用者從選項中選單字填入。"
                        elif mode == "閱讀":
                            prompt = f"請用這三個單字寫一篇約 80-100 字的有趣英文短文：{words_str}。並將短文內容放在 article 欄位。接著根據短文內容，出 3 題英文閱讀測驗選擇題。"
                        else:
                            prompt = f"請用這三個單字幫我出 3 題英文「單字字義或用法選擇題」：{words_str}。"
                except Exception as e:
                    app.logger.error(f"Quiz fetch error: {e}")
                    prompt = "請隨機出 3 題初中級的英文單字選擇題測驗。"
            else:
                prompt = "請隨機出 3 題初中級的英文單字選擇題測驗。"
        else:
            # 外部題庫模式 (初級、中級、高級)
            if mode == "填空":
                prompt = f"請幫我出 3 題符合「{level}」難度的英文「句子填空選擇題」。每題都必須有一個挖空的句子讓使用者從選項中選單字填入。"
            elif mode == "閱讀":
                prompt = f"請幫我寫一篇符合「{level}」難度的有趣英文短文（約 80-100 字），並將短文內容放在 article 欄位。接著根據短文內容，出 3 題英文閱讀測驗選擇題。"
            else:
                prompt = f"請幫我出 3 題符合「{level}」難度的英文「單字字義或用法選擇題」。"
        
        try:
            if mode == "閱讀":
                sys_inst = "你是一個英文閱讀測驗出題系統。請務必在 article 欄位撰寫一篇包含給定單字的英文短文，並根據該短文出 3 題選擇題。"
            elif mode == "填空":
                sys_inst = "你是一個英文填空測驗出題系統。請針對每個給定的單字出一個情境句子，並在句子中挖空（使用 ___），讓使用者從 A/B/C/D 選項中選擇正確的單字填入。"
            else:
                sys_inst = QUIZ_SYSTEM_PROMPT

            response = gemini_client.models.generate_content(
                model="gemini-2.5-flash",
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=QuizGenerationResult,
                    system_instruction=sys_inst
                ),
                contents=prompt,
            )
            result = parse_gemini_json(response, QuizGenerationResult)
            
            # Save to chat history so Gemini remembers the correct answers for grading
            save_chat_history(user_id, "user", prompt)
            save_chat_history(user_id, "model", response.text)
            quiz_memory[user_id] = response.text
            
            flex_content = make_quiz_generation_flex(result)
            with ApiClient(configuration) as api_client:
                line_api = MessagingApi(api_client)
                line_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[FlexMessage(
                            alt_text="🎓 新的隨堂測驗來囉",
                            contents=FlexContainer.from_json(json.dumps(flex_content))
                        )]
                    )
                )
        except Exception as e:
            app.logger.error(f"Quiz Generation error: {e}")
            reply_text(event.reply_token, "測驗產生失敗，請稍後再試。")
    else:
        # Grading
        quiz_json = quiz_memory.get(user_id, "")
        if not quiz_json and supabase:
            try:
                rows = supabase.table("chat_history").select("role,content").eq("user_id", user_id).order("id", desc=True).limit(10).execute().data or []
                for r in rows:
                    if r["role"] == "model" and "questions" in r["content"]:
                        quiz_json = r["content"]
                        break
            except Exception:
                pass
                
        if not quiz_json:
            reply_text(event.reply_token, "⚠️ 找不到剛剛的測驗題目，請重新輸入「測驗」來產生新題目。")
            return
            
        prompt = f"以下是剛才出給使用者的測驗題目資料：\n{quiz_json}\n\n使用者的答案是：\n{user_input}\n\n請進行比對批改。如果使用者輸入了 A/B/C/D 以外的無效內容（且無法對應到正確答案的文字），請在 feedback 中友善提醒『請輸入正確的選項代號（如 ABC）』，且分數判定為答錯。"
        
        try:
            response = gemini_client.models.generate_content(
                model="gemini-2.5-flash",
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=QuizGradingResult,
                    system_instruction=QUIZ_SYSTEM_PROMPT
                ),
                contents=prompt,
            )
            result = response.parsed
            save_chat_history(user_id, "user", user_input)
            save_chat_history(user_id, "model", result.score_text + " " + result.feedback)
            
            flex_content = make_quiz_grading_flex(result)
            with ApiClient(configuration) as api_client:
                line_api = MessagingApi(api_client)
                line_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[FlexMessage(
                            alt_text="✅ 測驗批改結果",
                            contents=FlexContainer.from_json(json.dumps(flex_content))
                        )]
                    )
                )
        except Exception as e:
            app.logger.error(f"Quiz Grading error: {e}")
            reply_text(event.reply_token, "批改失敗，可能格式不符，請重新輸入答案。")


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
    output = ask_gemini_multiturn(user_id, practice_sentence, system_instruction=CONVERSATION_SYSTEM_PROMPT)
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
        messages.append(AudioMessage(original_content_url=audio_url, duration=2000))
        
    with ApiClient(configuration) as api_client:
        line_api = MessagingApi(api_client)
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=messages
            )
        )


def do_vocab_manager(event, user_id: str, raw_input: str):
    if not supabase:
        reply_text(event.reply_token, "尚未設定 Supabase，請先設定 SUPABASE_URL / SUPABASE_KEY。")
        return
        
    parts = [x.strip() for x in raw_input.split('\n') if x.strip()]
    if len(parts) == 2:
        # Add mode
        word, category = parts[0], parts[1]
        meaning = ask_gemini(f"請提供英文單字/片語 '{word}' 的詞性與繁體中文意思。格式請用「(詞性) 中文意思」，例如「(n.) 蘋果」或「(v.) 跑」。只需回答最常見的意思，不要加上任何其他說明。").strip()
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
    else:
        # Query mode
        category = raw_input if raw_input and raw_input != '全部' else None
        # Could also be querying a specific word, let's just query by category or fallback
        # Wait, if they query by word? get_vocab_list is only by category right now.
        # We will enhance get_vocab_list to search both category and word.
        rows = get_vocab_list(user_id, category)
        flex_content = make_vocab_list_flex(rows, category)
        messages = [FlexMessage(alt_text="我的單字庫", contents=FlexContainer.from_json(json.dumps(flex_content)))]
        with ApiClient(configuration) as api_client:
            line_api = MessagingApi(api_client)
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=messages,
                )
            )

def do_vocab_add(event, user_id: str, raw_input: str):
    do_vocab_manager(event, user_id, raw_input)

def do_vocab_query(event, user_id: str, category: str = None, send_prompt: bool = False):
    do_vocab_manager(event, user_id, category or '全部')


def do_daily_word(event, send_prompt: bool = False):
    item = daily_word()
    if item:
        flex_content = make_daily_word_flex(item)
        messages = [FlexMessage(alt_text="每日單字", contents=FlexContainer.from_json(json.dumps(flex_content)))]
        if send_prompt:
            prompt_text = (
                "已切換至【每日單字】模式 📅\n"
                "點擊或輸入任何字，將為您推薦下一個每日單字。"
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


@handler.add(FollowEvent)
def handle_follow(event):
    welcome_text = (
        "🎉 歡迎加入！我是您的 AI 專屬英文家教！\n\n"
        "這裡有超多豐富的功能可以陪您輕鬆學英文：\n"
        "👉 直接傳送英文單字或句子，我會立刻為您翻譯！\n"
        "👉 點擊下方【選單】即可切換各種超強功能：\n"
        "   📚 單字庫：收藏您的專屬單字\n"
        "   🎓 隨堂測驗：初中高級、多益、雅思隨機出題！\n"
        "   🗣️ 英文會話：跟 AI 教練進行情境對話演練\n"
        "   📖 文法拆解：幫您秒懂長難句結構\n"
        "   📅 每日單字：天天學習一個全新單字\n\n"
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

# === LINE Message Handlers ===

MODE_MAPPING = {
    "翻譯": "translation",
    "文法拆解": "grammar",
    "文法": "grammar",
    "記憶新增": "vocab_manager",
    "記憶查詢": "vocab_manager",
    "單字庫": "vocab_manager",
    "每日單字": "daily_word",
    "會話": "conversation",
    "英文會話": "general",
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

    # 0. 優先攔截聽寫測驗
    if user_id in typing_quiz_memory:
        if user_input in ["退出", "結束", "取消", "不玩了"]:
            del typing_quiz_memory[user_id]
            reply_text(event.reply_token, "已結束測驗。")
            return
        handle_typing_quiz_answer(event, user_id, user_input)
        return

    # 0. 優先攔截網址進行自動摘要
    if user_input.startswith("http://") or user_input.startswith("https://"):
        do_url_summary(event, user_id, user_input)
        return

    # 0a. 優先攔截「記憶新增快捷:」前綴（翻譯卡片上的加入單字庫按鈕）
    if user_input.startswith("記憶新增快捷:") or user_input.startswith("記憶新增快捷："):
        payload = user_input.split(":", 1)[1].strip()
        parts = [x.strip() for x in payload.split("|")]
        if len(parts) == 3:
            category, word, meaning = parts[0], parts[1], parts[2]
            res_text = add_vocab(user_id, category, word, meaning)
            if "已新增單字" in res_text:
                flex_content = make_vocab_added_flex(category, word, meaning)
                with ApiClient(configuration) as api_client:
                    line_api = MessagingApi(api_client)
                    line_api.reply_message(
                        ReplyMessageRequest(
                            reply_token=event.reply_token,
                            messages=[FlexMessage(
                                alt_text=f"✅ {word} 已加入單字庫",
                                contents=FlexContainer.from_json(json.dumps(flex_content))
                            )],
                        )
                    )
            else:
                reply_text(event.reply_token, res_text)
        else:
            reply_text(event.reply_token, "快速加入格式錯誤，請重新嘗試。")
        return

    # 0b. 攔截「刪除單字:」與「刪除分類:」
    if user_input.startswith("刪除單字:") or user_input.startswith("刪除單字："):
        word = user_input.split(":", 1)[1].strip() if ":" in user_input else user_input.split("：", 1)[1].strip()
        res = delete_vocab(user_id, word)
        reply_text(event.reply_token, res)
        return
        
    if user_input.startswith("刪除分類:") or user_input.startswith("刪除分類："):
        category = user_input.split(":", 1)[1].strip() if ":" in user_input else user_input.split("：", 1)[1].strip()
        res = delete_vocab_category(user_id, category)
        reply_text(event.reply_token, res)
        return

    # 0c. 優先攔截「發音: 」前綴的快捷指令
    if user_input.startswith("發音:") or user_input.startswith("發音："):
        word = user_input[3:].strip()
        audio_url = get_pronunciation_audio(word)
        messages = [TextMessage(text=f"發音: {word}")]
        if audio_url:
            messages.append(
                AudioMessage(
                    original_content_url=audio_url,
                    duration=2000
                )
            )
        else:
            messages.append(TextMessage(text="暫時無法提供此單字的發音音檔。"))
            
        with ApiClient(configuration) as api_client:
            line_api = MessagingApi(api_client)
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=messages,
                )
            )
        return

    # 0c. 攔截「測驗」前綴指令，支援指定範圍 (例如：測驗 多益)
    if user_input == "測驗":
        send_quiz_menu(event)
        return
        
    if user_input.startswith("測驗") or user_input.startswith("隨堂測驗") or user_input == "馬上測驗":
        scope = user_input.replace("馬上測驗", "").replace("隨堂測驗", "").replace("測驗", "").strip()
        set_user_mode(user_id, "quiz")
        do_quiz(event, user_id, start=True, scope=scope)
        return

    # 0d. 攔截測驗答案 (3個 A-D 的字母組合，例如 ABC, bca)
    if re.fullmatch(r"[A-Da-d]{3}", user_input):
        do_quiz(event, user_id, user_input=user_input, start=False)
        return

    # 1. 檢查是否為功能切換關鍵字
    if user_input in MODE_MAPPING:
        target_mode = MODE_MAPPING[user_input]
        set_user_mode(user_id, target_mode)
        
        if target_mode == "translation":
            reply_text(
                event.reply_token,
                "已切換至【翻譯】模式 📝\n"
                "👉 請直接輸入要翻譯的文字或文章\n"
                "👉 或是貼上「網址」，我會自動為您摘要內容\n"
                "👉 也可以直接傳送「照片」，我會分析畫面並教您 5 個相關單字喔！"
            )
        elif target_mode == "grammar":
            reply_text(
                event.reply_token,
                "已切換至【文法拆解】模式 📖\n"
                "👉 請直接輸入長難句，自動為您解析句型與文法重點"
            )
        elif target_mode == "vocab_manager":
            categories = get_vocab_categories(user_id)
            flex_content = make_category_carousel_flex(categories)
            prompt_text = (
                "已切換至【單字庫】模式 📚\n"
                "👉 點擊卡片查閱分類單字\n"
                "👉 輸入「單字」與「分類」（分兩行），自動翻譯並新增"
            )
            messages = [
                TextMessage(text=prompt_text),
                FlexMessage(alt_text="分類選擇", contents=FlexContainer.from_json(json.dumps(flex_content)))
            ]
            with ApiClient(configuration) as api_client:
                line_api = MessagingApi(api_client)
                line_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=messages
                    )
                )
        elif target_mode == "daily_word":
            # 切換時，直接幫他出一個每日單字，不附上提示文字
            do_daily_word(event)
        elif target_mode == "conversation":
            reply_text(
                event.reply_token,
                "已切換至【會話】模式 🗣️\n"
                "👉 隨意輸入內容，進行全英文情境對話"
            )
        elif target_mode == "pronunciation":
            reply_text(
                event.reply_token,
                "已切換至【發音】模式 🔊\n"
                "👉 輸入單字，為您生成標準發音語音檔與解析"
            )
        else: # general
            reply_text(
                event.reply_token,
                "已切換至【英文會話】模式 💬\n"
                "👉 隨意聊天，自動回覆有聲英文語音與文字\n"
                "👉 即時糾正您的英文文法與用詞！"
            )
        return

    # 2. 若非切換關鍵字，根據當前模式執行
    current_mode = get_user_mode(user_id)
    
    if current_mode == "translation":
        do_translation(event, user_input)
    elif current_mode == "grammar":
        do_grammar_analysis(event, user_input)
    elif current_mode == "quiz":
        do_quiz(event, user_id, user_input=user_input, start=False)
    elif current_mode == "vocab_manager":
        do_vocab_manager(event, user_id, user_input)
    elif current_mode == "daily_word":
        do_daily_word(event)
    elif current_mode == "conversation":
        do_conversation(event, user_id, user_input)
    elif current_mode == "pronunciation":
        do_pronunciation(event, user_input)
    else: # general / None
        # 一般聊天直接使用多輪會話功能，並預設為會話演練教練
        output = ask_gemini_multiturn(user_id, user_input, system_instruction=CONVERSATION_SYSTEM_PROMPT)
        flex_content = make_general_chat_flex(user_input, output)
        with ApiClient(configuration) as api_client:
            line_api = MessagingApi(api_client)
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[FlexMessage(
                        alt_text="🗣️ 會話演練回覆",
                        contents=FlexContainer.from_json(json.dumps(flex_content))
                    )]
                )
            )



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
    # init_rich_menu() # 註解掉此行，避免每次重啟容器都會刪除並重建 Rich Menu 導致使用者端消失
except Exception as e:
    app.logger.warning(f"Auto-initializing rich menu failed: {e}")

