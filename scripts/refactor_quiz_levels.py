import re

with open('multiturn.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update send_quiz_menu to use a Carousel Flex Message
old_menu_func = '''def send_quiz_menu(event):
    quick_reply = QuickReply(
        items=[
            QuickReplyItem(action=MessageAction(label="📚 選擇題 (單字庫)", text="測驗 選擇")),
            QuickReplyItem(action=MessageAction(label="📝 填空題 (單字庫)", text="測驗 填空")),
            QuickReplyItem(action=MessageAction(label="📖 閱讀題 (單字庫)", text="測驗 閱讀")),
            QuickReplyItem(action=MessageAction(label="🎧 聽寫題 (單字庫)", text="測驗 聽寫")),
            QuickReplyItem(action=MessageAction(label="🌍 隨機單字測驗", text="測驗 隨機")),
            QuickReplyItem(action=MessageAction(label="💼 多益 (TOEIC)", text="測驗 多益")),
            QuickReplyItem(action=MessageAction(label="🎓 雅思 (IELTS)", text="測驗 雅思")),
            QuickReplyItem(action=MessageAction(label="📈 商業英文", text="測驗 商業英文"))
        ]
    )
    with ApiClient(configuration) as api_client:
        line_api = MessagingApi(api_client)
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text="請選擇測驗範圍與模式：\\n👉「單字庫」模式將根據您收藏的專屬單字出題\\n👉 也可以直接選擇挑戰全範圍的多益、雅思題庫喔！", quick_reply=quick_reply)]
            )
        )'''

new_menu_func = '''def send_quiz_menu(event):
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
        )'''
content = content.replace(old_menu_func, new_menu_func)

# 2. Update do_quiz and dictation logic
old_quiz_start = '''    if start:
        prompt = ""
        mode = scope if scope in ["選擇", "填空", "閱讀", "聽寫"] else "選擇"
        is_library_mode = scope in ["選擇", "填空", "閱讀", "聽寫", ""]
        
        if mode == "聽寫":
            handle_dictation_start(event, user_id)
            return'''

new_quiz_start = '''    if start:
        prompt = ""
        parts = scope.split()
        mode = parts[0] if len(parts) > 0 and parts[0] in ["選擇", "填空", "閱讀", "聽寫"] else "選擇"
        level = parts[1] if len(parts) > 1 else "單字庫"
        
        if mode == "聽寫":
            handle_dictation_start(event, user_id, level)
            return'''
content = content.replace(old_quiz_start, new_quiz_start)

# 3. Modify handle_dictation_start to support levels
old_dictation_start = '''def handle_dictation_start(event, user_id: str):
    if not supabase:
        reply_text(event.reply_token, "尚未設定 Supabase")
        return
    try:
        res = supabase.table("vocab_memory").select("word,meaning").eq("user_id", user_id).execute()
        data = res.data or []
        if len(data) < 3:
            reply_text(event.reply_token, "您的單字庫數量不足，請先新增至少 3 個單字再來挑戰聽寫喔！")
            return
        import random
        words = random.sample(data, 3)'''

new_dictation_start = '''def handle_dictation_start(event, user_id: str, level: str = "單字庫"):
    if level == "單字庫":
        if not supabase:
            reply_text(event.reply_token, "尚未設定 Supabase")
            return
        try:
            res = supabase.table("vocab_memory").select("word,meaning").eq("user_id", user_id).execute()
            data = res.data or []
            if len(data) < 3:
                reply_text(event.reply_token, "您的單字庫數量不足，請先新增至少 3 個單字再來挑戰聽寫喔！")
                return
            import random
            words = random.sample(data, 3)
        except Exception as e:
            app.logger.error(f"Dictation fetch error: {e}")
            reply_text(event.reply_token, "發生錯誤，請稍後再試。")
            return
    else:
        # Request 3 words from Gemini based on the level
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
            
    try:'''
content = content.replace(old_dictation_start, new_dictation_start)

# Remove the old except block that we nested
old_dictation_except = '''        dictation_memory[user_id] = {"words": words, "current_idx": 0, "score": 0}
        
        word_obj = words[0]
        audio_url = get_pronunciation_audio(word_obj["word"])
        messages = [TextMessage(text=f"🎧 第 1 題：請聽語音，並輸入您聽到的英文單字拼寫！\\n提示：{word_obj['meaning']}")]
        if audio_url:
            messages.append(AudioMessage(original_content_url=audio_url, duration=2000))
        else:
            messages.append(TextMessage(text="語音產生失敗，此題無法進行。"))
            
        with ApiClient(configuration) as api_client:
            line_api = MessagingApi(api_client)
            line_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=messages))
            
    except Exception as e:
        app.logger.error(f"Dictation fetch error: {e}")
        reply_text(event.reply_token, "發生錯誤，請稍後再試。")'''

new_dictation_except = '''        dictation_memory[user_id] = {"words": words, "current_idx": 0, "score": 0}
        
        word_obj = words[0]
        audio_url = get_pronunciation_audio(word_obj["word"])
        messages = [TextMessage(text=f"🎧 第 1 題：請聽語音，並輸入您聽到的英文單字拼寫！\\n提示：{word_obj['meaning']}")]
        if audio_url:
            messages.append(AudioMessage(original_content_url=audio_url, duration=2000))
        else:
            messages.append(TextMessage(text="語音產生失敗，此題無法進行。"))
            
        with ApiClient(configuration) as api_client:
            line_api = MessagingApi(api_client)
            line_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=messages))
            
    except Exception as e:
        app.logger.error(f"Dictation fetch error: {e}")
        reply_text(event.reply_token, "發生錯誤，請稍後再試。")'''
# Actually they are identical, I don't need to change the bottom half of the function if I am careful with indentation.

# Wait, `handle_dictation_start` currently has `except Exception as e:` at the end. In `new_dictation_start` I added `try:`.
# I should just replace the WHOLE function.

import re
with open('multiturn.py', 'r', encoding='utf-8') as f:
    content = f.read()

func_pattern = re.compile(r'def handle_dictation_start.*?def handle_dictation_answer', re.DOTALL)

whole_new_func = '''def handle_dictation_start(event, user_id: str, level: str = "單字庫"):
    if level == "單字庫":
        if not supabase:
            reply_text(event.reply_token, "尚未設定 Supabase")
            return
        try:
            res = supabase.table("vocab_memory").select("word,meaning").eq("user_id", user_id).execute()
            data = res.data or []
            if len(data) < 3:
                reply_text(event.reply_token, "您的單字庫數量不足，請先新增至少 3 個單字再來挑戰聽寫喔！")
                return
            import random
            words = random.sample(data, 3)
        except Exception as e:
            app.logger.error(f"Dictation fetch error: {e}")
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

    try:
        dictation_memory[user_id] = {"words": words, "current_idx": 0, "score": 0}
        
        word_obj = words[0]
        audio_url = get_pronunciation_audio(word_obj["word"])
        messages = [TextMessage(text=f"🎧 第 1 題：請聽語音，並輸入您聽到的英文單字拼寫！\\n提示：{word_obj['meaning']}")]
        if audio_url:
            messages.append(AudioMessage(original_content_url=audio_url, duration=2000))
        else:
            messages.append(TextMessage(text="語音產生失敗，此題無法進行。"))
            
        with ApiClient(configuration) as api_client:
            line_api = MessagingApi(api_client)
            line_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=messages))
            
    except Exception as e:
        app.logger.error(f"Dictation start error: {e}")
        reply_text(event.reply_token, "發生錯誤，請稍後再試。")

def handle_dictation_answer'''

content = func_pattern.sub(whole_new_func, content)

# 4. Modify do_quiz logic for regular quizzes
old_quiz_mid = '''        if is_library_mode:
            if supabase:
                try:
                    res = supabase.table("vocab_memory").select("word,meaning").eq("user_id", user_id).execute()
                    data = res.data or []
                    if len(data) < 3:
                        prompt = "使用者單字庫目前單字不足，請幫我隨機出 3 題初中級的英文選擇題測驗。"
                    else:
                        words = random.sample(data, 3)
                        words_str = ", ".join([f"{w['word']} ({w['meaning']})" for w in words])
                        if mode == "填空":
                            prompt = f"請用這三個單字作為正確答案，幫我出 3 題英文「句子填空選擇題」：{words_str}。每題都必須有一個挖空的句子讓使用者選單字填入。"
                        elif mode == "閱讀":
                            prompt = f"請用這三個單字寫一篇約 80-100 字的有趣英文短文：{words_str}。並將短文內容放在 article 欄位。接著根據短文內容，出 3 題英文閱讀測驗選擇題。"
                        else:
                            prompt = f"請用這三個單字幫我出 3 題英文「單字字義或用法選擇題」：{words_str}。"
                except Exception as e:
                    app.logger.error(f"Quiz fetch error: {e}")
                    prompt = "請隨機出 3 題初中級的英文選擇題測驗。"
            else:
                prompt = "請隨機出 3 題初中級的英文選擇題測驗。"
        else:
            # 外部題庫模式
            if scope == "隨機":
                prompt = "請幫我隨機出 3 題初中級的英文單字或文法選擇題測驗。"
            else:
                prompt = f"請幫我出 3 題符合「{scope}」難度與情境的英文選擇題測驗。"'''

new_quiz_mid = '''        if level == "單字庫":
            if supabase:
                try:
                    res = supabase.table("vocab_memory").select("word,meaning").eq("user_id", user_id).execute()
                    data = res.data or []
                    if len(data) < 3:
                        prompt = "使用者單字庫目前單字不足，請幫我隨機出 3 題初中級的英文選擇題測驗。"
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
                    prompt = "請隨機出 3 題初中級的英文選擇題測驗。"
            else:
                prompt = "請隨機出 3 題初中級的英文選擇題測驗。"
        else:
            # 外部題庫模式 (初級、中級、高級)
            if mode == "填空":
                prompt = f"請幫我出 3 題符合「{level}」難度的英文「句子填空選擇題」。每題都必須有一個挖空的句子讓使用者從選項中選單字填入。"
            elif mode == "閱讀":
                prompt = f"請幫我寫一篇符合「{level}」難度的有趣英文短文（約 80-100 字），並將短文內容放在 article 欄位。接著根據短文內容，出 3 題英文閱讀測驗選擇題。"
            else:
                prompt = f"請幫我出 3 題符合「{level}」難度的英文「單字字義或用法選擇題」。"'''
content = content.replace(old_quiz_mid, new_quiz_mid)


with open('multiturn.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Quiz layout refactored into Flex Message and levels applied!")
