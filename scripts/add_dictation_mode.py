import re

with open('multiturn.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Add dictation_memory and functions
dictation_funcs = '''
dictation_memory = {}

def handle_dictation_start(event, user_id: str):
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
        app.logger.error(f"Dictation fetch error: {e}")
        reply_text(event.reply_token, "發生錯誤，請稍後再試。")

def handle_dictation_answer(event, user_id: str, user_input: str):
    state = dictation_memory.get(user_id)
    if not state: return
    idx = state["current_idx"]
    word_obj = state["words"][idx]
    correct_word = word_obj["word"].strip().lower()
    user_ans = user_input.strip().lower()
    
    if user_ans == correct_word:
        state["score"] += 1
        feedback = "✅ 答對了！拼寫完全正確。"
    else:
        feedback = f"❌ 答錯囉！\\n您的答案：{user_input}\\n正確拼法：{word_obj['word']}"
        
    state["current_idx"] += 1
    idx = state["current_idx"]
    
    if idx >= len(state["words"]):
        score = state["score"]
        total = len(state["words"])
        del dictation_memory[user_id]
        reply_text(event.reply_token, f"{feedback}\\n\\n🎉 聽寫測驗結束！您的分數是：{score}/{total} 題。")
        return
        
    next_word = state["words"][idx]
    audio_url = get_pronunciation_audio(next_word["word"])
    
    messages = [TextMessage(text=f"{feedback}\\n\\n---\\n🎧 第 {idx+1} 題：請聽語音，並輸入正確的單字！\\n提示：{next_word['meaning']}")]
    if audio_url:
        messages.append(AudioMessage(original_content_url=audio_url, duration=2000))
        
    with ApiClient(configuration) as api_client:
        line_api = MessagingApi(api_client)
        line_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=messages))
'''

if 'dictation_memory = {}' not in content:
    content = content.replace('quiz_memory = {}', dictation_funcs + '\nquiz_memory = {}')

# 2. Update send_quiz_menu
old_menu = '''def send_quiz_menu(event):
    quick_reply = QuickReply(
        items=[
            QuickReplyItem(action=MessageAction(label="📚 選擇題 (單字庫)", text="測驗 選擇")),
            QuickReplyItem(action=MessageAction(label="📝 填空題 (單字庫)", text="測驗 填空")),
            QuickReplyItem(action=MessageAction(label="📖 閱讀題 (單字庫)", text="測驗 閱讀"))
        ]
    )'''
new_menu = '''def send_quiz_menu(event):
    quick_reply = QuickReply(
        items=[
            QuickReplyItem(action=MessageAction(label="📚 選擇題", text="測驗 選擇")),
            QuickReplyItem(action=MessageAction(label="📝 填空題", text="測驗 填空")),
            QuickReplyItem(action=MessageAction(label="📖 閱讀題", text="測驗 閱讀")),
            QuickReplyItem(action=MessageAction(label="🎧 聽寫題", text="測驗 聽寫"))
        ]
    )'''
if "測驗 聽寫" not in content:
    content = content.replace(old_menu, new_menu)

# 3. Update do_quiz to intercept dictation mode
old_quiz_start = '''    if start:
        prompt = ""
        mode = scope if scope in ["選擇", "填空", "閱讀"] else "選擇"'''
new_quiz_start = '''    if start:
        prompt = ""
        mode = scope if scope in ["選擇", "填空", "閱讀", "聽寫"] else "選擇"
        if mode == "聽寫":
            handle_dictation_start(event, user_id)
            return'''
if "handle_dictation_start(" not in content:
    content = content.replace(old_quiz_start, new_quiz_start)

# 4. Update handle_text_message to intercept dictation answers
interceptor = '''    # 0. 優先攔截聽寫測驗
    if user_id in dictation_memory:
        if user_input in ["退出", "結束", "取消", "不玩了"]:
            del dictation_memory[user_id]
            reply_text(event.reply_token, "已結束聽寫測驗。")
            return
        handle_dictation_answer(event, user_id, user_input)
        return

    # 0. 優先攔截網址進行自動摘要'''
if "dictation_memory:" not in content:
    content = content.replace('    # 0. 優先攔截網址進行自動摘要', interceptor)

with open('multiturn.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("Done!")
