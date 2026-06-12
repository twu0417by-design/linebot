import re

with open('multiturn.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace the start logic for 填空
old_start = '''        else: # 填空
            messages = [TextMessage(text=f"📝 第 1 題：請閱讀句子並根據語意，直接輸入被挖空的英文單字！\\n\\n題目：{word_obj['sentence']}\\n提示：{word_obj['meaning']}")]'''

new_start = '''        else: # 填空
            q_text = "\\n\\n".join([f"📝 第 {i+1} 題：\\n題目：{w['sentence']}\\n提示：{w['meaning']}" for i, w in enumerate(words)])
            messages = [TextMessage(text=f"【填空測驗】請根據語意填入被挖空的單字！\\n請用「換行」分隔 3 題的答案（例如：\\napple\\nbanana\\ncat）\\n\\n{q_text}")]'''

content = content.replace(old_start, new_start)

# Replace the answer logic for 填空
old_answer_logic = '''    if user_ans == correct_word:
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

new_answer_logic = '''    if mode == "填空":
        user_lines = [line.strip().lower() for line in user_input.split('\\n') if line.strip()]
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
                
        feedback_text = "\\n".join(feedbacks)
        del typing_quiz_memory[user_id]
        reply_text(event.reply_token, f"批改結果：\\n{feedback_text}\\n\\n🎉 填空測驗結束！您的分數是：{score}/{total} 題。")
        return
    else:
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
        
        audio_url = get_pronunciation_audio(next_word["word"])
        messages = [TextMessage(text=f"{feedback}\\n\\n---\\n🎧 第 {idx+1} 題：請聽語音，並輸入正確的單字！\\n提示：{next_word['meaning']}")]
        if audio_url:
            messages.append(AudioMessage(original_content_url=audio_url, duration=2000))
            
        with ApiClient(configuration) as api_client:
            line_api = MessagingApi(api_client)
            line_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=messages))'''

content = content.replace(old_answer_logic, new_answer_logic)

with open('multiturn.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("Updated fill-in-the-blank logic to batch questions!")
