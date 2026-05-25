import os
import tempfile
import uuid
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
    MessagingApi,
    MessagingApiBlob,
    ReplyMessageRequest,
    TextMessage,
)
from linebot.v3.webhooks import ImageMessageContent, MessageEvent, TextMessageContent
from supabase import Client, create_client


SYSTEM_PROMPT = """
你是繁體中文語言學習助教。回答要精準、簡潔、可直接學習。
若使用者要求翻譯、文法修正、會話演練，請分點輸出並附上1~2個例句。
"""

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
SPACE_HOST = os.getenv("SPACE_HOST", "")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

gemini_client = genai.Client(api_key=GEMINI_API_KEY)
app = Flask(__name__)
configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)
supabase: Client | None = (
    create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None
)
static_tmp_path = tempfile.gettempdir()
os.makedirs(static_tmp_path, exist_ok=True)


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
    response = gemini_client.models.generate_content(
        model="gemini-2.5-flash",
        config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT),
        contents=prompt,
    )
    return response.text or "目前無法產生內容，請稍後再試。"


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


def word_pronunciation(word: str) -> str:
    prompt = f"請提供單字 {word} 的IPA（英式與美式）、詞性與簡短中文解釋。"
    tts_url = (
        "https://translate.google.com/translate_tts?ie=UTF-8&client=tw-ob"
        f"&tl=en&q={quote_plus(word)}"
    )
    return f"{ask_gemini(prompt)}\n\n發音連結: {tts_url}"


def add_vocab(user_id: str, category: str, word: str, meaning: str) -> str:
    if not supabase:
        return "尚未設定 Supabase，請先設定 SUPABASE_URL / SUPABASE_KEY。"
    data = {
        "user_id": user_id,
        "category": category,
        "word": word,
        "meaning": meaning,
    }
    supabase.table("vocab_memory").insert(data).execute()
    return f"已新增單字 `{word}` 到分類 `{category}`。"


def list_vocab(user_id: str, category: str | None) -> str:
    if not supabase:
        return "尚未設定 Supabase，請先設定 SUPABASE_URL / SUPABASE_KEY。"
    query = supabase.table("vocab_memory").select("category,word,meaning").eq("user_id", user_id)
    if category:
        query = query.eq("category", category)
    rows = query.order("id", desc=True).limit(20).execute().data or []
    if not rows:
        return "目前沒有詞彙記錄。"
    lines = [f"- [{r['category']}] {r['word']}：{r['meaning']}" for r in rows]
    return "你的詞彙記憶：\n" + "\n".join(lines)


def daily_word() -> str:
    if supabase:
        rows = (
            supabase.table("daily_words")
            .select("word,meaning,example")
            .order("id", desc=False)
            .limit(1)
            .execute()
            .data
            or []
        )
        if rows:
            row = rows[0]
            return f"每日單字: {row['word']}\n意思: {row['meaning']}\n例句: {row['example']}"
    prompt = "請給我1個適合華語使用者學英文的每日單字，含中文意思與英文例句。"
    return ask_gemini(prompt)


def generate_image(prompt: str) -> str | None:
    response = gemini_client.models.generate_content(
        model="gemini-2.0-flash-preview-image-generation",
        contents=prompt,
        config=types.GenerateContentConfig(response_modalities=["TEXT", "IMAGE"]),
    )
    for part in response.candidates[0].content.parts:
        if part.inline_data:
            image = Image.open(BytesIO(part.inline_data.data))
            filename = f"{uuid.uuid4().hex}.png"
            image.save(os.path.join(static_tmp_path, filename))
            return f"https://{SPACE_HOST}/images/{filename}" if SPACE_HOST else None
    return None


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


@app.route("/", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature")
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return "OK"


@handler.add(MessageEvent, message=TextMessageContent)
def handle_text_message(event):
    user_id = getattr(event.source, "user_id", "anonymous")
    user_input = event.message.text.strip()

    if user_input.startswith("翻譯:"):
        reply_text(event.reply_token, translate_article(user_input.replace("翻譯:", "", 1).strip()))
        return
    if user_input.startswith("會話:"):
        reply_text(event.reply_token, conversation_coach(user_input.replace("會話:", "", 1).strip()))
        return
    if user_input.startswith("發音:"):
        reply_text(event.reply_token, word_pronunciation(user_input.replace("發音:", "", 1).strip()))
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

    output = ask_gemini(user_input)
    html_msg = markdown.markdown(output)
    soup = BeautifulSoup(html_msg, "html.parser")
    reply_text(event.reply_token, soup.get_text())


@handler.add(MessageEvent, message=ImageMessageContent)
def handle_image_message(event):
    with ApiClient(configuration) as api_client:
        blob_api = MessagingApiBlob(api_client)
        image_data = blob_api.get_message_content(message_id=event.message.id)

    with tempfile.NamedTemporaryFile(dir=static_tmp_path, suffix=".jpg", delete=False) as tmp:
        tmp.write(image_data)
        local_path = tmp.name

    image = Image.open(local_path)
    response = gemini_client.models.generate_content(
        model="gemini-2.5-flash",
        config=types.GenerateContentConfig(
            system_instruction="你是語言學習老師，請描述圖片內容並教5個相關英文單字（含中文）。"
        ),
        contents=[image, "請用繁體中文解說這張圖並提供學習重點。"],
    )
    reply_text(event.reply_token, response.text or "圖片理解失敗，請稍後再試。")
