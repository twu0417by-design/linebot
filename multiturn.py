import os
import tempfile
import uuid
import random
import requests
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


def translate_article(text: str) -> str:
    prompt = (
        "請將以下文章翻譯成繁體中文，保留段落。最後補上3個關鍵詞彙解釋。\n\n"
        f"{text}"
    )
    return ask_gemini(prompt)


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


def word_pronunciation(word: str) -> tuple[str, str | None]:
    prompt = f"請提供單字 {word} 的IPA（英式與美式）、詞性與簡短中文解釋。"
    text_reply = ask_gemini(prompt)
    audio_url = get_pronunciation_audio(word)
    return text_reply, audio_url


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


def daily_word() -> str:
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
                return f"💡 每日單字：{row['word']}\n📖 意思：{row['meaning']}\n📝 例句：{row['example']}"
        except Exception as e:
            app.logger.error(f"Failed to fetch daily word from Supabase: {e}")

    if not gemini_client:
        return "💡 每日單字：apple\n📖 意思：蘋果\n📝 例句：An apple a day keeps the doctor away."

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
        return f"💡 每日單字：{item.word}\n📖 意思：{item.meaning}\n📝 例句：{item.example}"
    except Exception as e:
        app.logger.error(f"Failed to generate daily word: {e}")
        return "💡 每日單字：apple\n📖 意思：蘋果\n📝 例句：An apple a day keeps the doctor away. (一天一蘋果，醫生遠離我。)"


def generate_image(prompt: str) -> str | None:
    if not gemini_client:
        return None
    try:
        # 使用 Imagen 3 模型生成圖像
        response = gemini_client.models.generate_images(
            model="imagen-3.0-generate-002",
            prompt=prompt,
            config=types.GenerateImagesConfig(
                number_of_images=1
            )
        )
        if response.generated_images:
            image_data = response.generated_images[0].image.image_bytes
            image = Image.open(BytesIO(image_data))
            filename = f"gen_{uuid.uuid4().hex}.png"
            image.save(os.path.join(static_tmp_path, filename))
            return f"https://{SPACE_HOST}/images/{filename}" if SPACE_HOST else None
    except Exception as e:
        app.logger.error(f"Image generation failed: {e}")
    return None


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


# === LINE Message Handlers ===

@handler.add(MessageEvent, message=TextMessageContent)
def handle_text_message(event):
    user_id = getattr(event.source, "user_id", "anonymous")
    user_input = event.message.text.strip()

    if user_input.startswith("翻譯:"):
        reply_text(event.reply_token, translate_article(user_input.replace("翻譯:", "", 1).strip()))
        return
    if user_input.startswith("會話:"):
        # 會話練習也走多輪，但去除指令前綴
        practice_sentence = user_input.replace("會話:", "", 1).strip()
        output = ask_gemini_multiturn(user_id, practice_sentence)
        reply_text(event.reply_token, output)
        return
    if user_input.startswith("發音:"):
        word = user_input.replace("發音:", "", 1).strip()
        text_reply, audio_url = word_pronunciation(word)
        
        messages = [TextMessage(text=text_reply[:5000])]
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
        return
    if user_input.startswith("記憶新增:"):
        raw = user_input.replace("記憶新增:", "", 1).strip()
        parts = [x.strip() for x in raw.split("|")]
        if len(parts) != 3:
            reply_text(event.reply_token, "格式: 記憶新增: 分類|單字|中文意思")
            return
        reply_text(event.reply_token, add_vocab(user_id, parts[0], parts[1], parts[2]))
        return
    if user_input.startswith("記憶查詢"):
        category = None
        if ":" in user_input:
            category = user_input.split(":", 1)[1].strip() or None
        reply_text(event.reply_token, list_vocab(user_id, category))
        return
    if user_input == "每日單字":
        reply_text(event.reply_token, daily_word())
        return
    if user_input.startswith("生圖:"):
        image_url = generate_image(user_input.replace("生圖:", "", 1).strip())
        if not image_url:
            reply_text(event.reply_token, "生圖失敗，請確認 SPACE_HOST 與 Gemini 權限設定。")
            return
        with ApiClient(configuration) as api_client:
            line_api = MessagingApi(api_client)
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[
                        ImageMessage(
                            original_content_url=image_url,
                            preview_image_url=image_url,
                        )
                    ],
                )
            )
        return

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
        vocab_str = "\n".join([f"- [{item.category}] {item.word}：{item.meaning}" for item in result.vocab_list])
        reply_msg = (
            f"📷 圖片描述：\n{result.description}\n\n"
            f"💡 學習重點：\n{result.learning_points}\n\n"
            f"📚 學習單字：\n{vocab_str}"
        )
        if saved_count > 0:
            reply_msg += f"\n\n✨ 已自動將這 {saved_count} 個單字存入您的單字庫中！"

        reply_text(event.reply_token, reply_msg)
    except Exception as e:
        app.logger.error(f"Image analysis failed: {e}")
        reply_text(event.reply_token, "圖片理解失敗，請稍後再試。")
