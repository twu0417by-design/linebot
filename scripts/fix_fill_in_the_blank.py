import re

with open('multiturn.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Rename dictation_memory to typing_quiz_memory
content = content.replace("dictation_memory", "typing_quiz_memory")

# 2. Update do_quiz to route "填空" to typing quiz logic
old_route = '''        if mode == "聽寫":
            handle_dictation_start(event, user_id, level)
            return'''
new_route = '''        if mode in ["聽寫", "填空"]:
            handle_typing_quiz_start(event, user_id, level, mode)
            return'''
content = content.replace(old_route, new_route)

# 3. Replace handle_dictation_start and handle_dictation_answer
# Find the block from handle_dictation_start to the end of handle_dictation_answer
pattern = re.compile(r'def handle_dictation_start\(.*?\n        return', re.DOTALL)

typing_quiz_logic = '''def handle_typing_quiz_start(event, user_id: str, level: str = "單字庫", mode: str = "聽寫"):
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
            messages = [TextMessage(text=f"🎧 第 1 題：請聽語音，並輸入您聽到的英文單字拼寫！\\n提示：{word_obj['meaning']}")]
            if audio_url:
                messages.append(AudioMessage(original_content_url=audio_url, duration=2000))
            else:
                messages.append(TextMessage(text="語音產生失敗，此題無法進行。"))
        else: # 填空
            messages = [TextMessage(text=f"📝 第 1 題：請閱讀句子並根據語意，直接輸入被挖空的英文單字！\\n\\n題目：{word_obj['sentence']}\\n提示：{word_obj['meaning']}")]
            
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
    
    if user_ans == correct_word:
        state["score"] += 1
        feedback = "✅ 答對了！拼寫完全正確。"
    else:
        feedback = f"❌ 答錯囉！\\n您的答案：{user_input}\\n正確單字：{word_obj['word']}"
        
    state["current_idx"] += 1
    idx = state["current_idx"]
    
    if idx >= len(state["words"]):
        score = state["score"]
        total = len(state["words"])
        del typing_quiz_memory[user_id]
        reply_text(event.reply_token, f"{feedback}\\n\\n🎉 {mode}測驗結束！您的分數是：{score}/{total} 題。")
        return
        
    next_word = state["words"][idx]
    
    if mode == "聽寫":
        audio_url = get_pronunciation_audio(next_word["word"])
        messages = [TextMessage(text=f"{feedback}\\n\\n---\\n🎧 第 {idx+1} 題：請聽語音，並輸入正確的單字！\\n提示：{next_word['meaning']}")]
        if audio_url:
            messages.append(AudioMessage(original_content_url=audio_url, duration=2000))
    else:
        messages = [TextMessage(text=f"{feedback}\\n\\n---\\n📝 第 {idx+1} 題：請填入被挖空的單字！\\n\\n題目：{next_word['sentence']}\\n提示：{next_word['meaning']}")]
        
    with ApiClient(configuration) as api_client:
        line_api = MessagingApi(api_client)
        line_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=messages))'''

content = pattern.sub(typing_quiz_logic, content)

# 4. In handle_text_message, route user input to typing_quiz_memory if user in it
old_interceptor = '''    # 0a. 若在聽寫測驗中，優先處理聽寫答案
    if user_id in dictation_memory:
        handle_dictation_answer(event, user_id, user_input)
        return'''
new_interceptor = '''    # 0a. 若在打字測驗中（聽寫/填空），優先處理打字答案
    if user_id in typing_quiz_memory:
        handle_typing_quiz_answer(event, user_id, user_input)
        return'''
content = content.replace(old_interceptor, new_interceptor)

with open('multiturn.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("Replaced fill-in-the-blank logic successfully!")
