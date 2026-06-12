import re

with open('multiturn.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update send_quiz_menu
old_menu = '''def send_quiz_menu(event):
    quick_reply = QuickReply(
        items=[
            QuickReplyItem(action=MessageAction(label="📚 選擇題", text="測驗 選擇")),
            QuickReplyItem(action=MessageAction(label="📝 填空題", text="測驗 填空")),
            QuickReplyItem(action=MessageAction(label="📖 閱讀題", text="測驗 閱讀")),
            QuickReplyItem(action=MessageAction(label="🎧 聽寫題", text="測驗 聽寫"))
        ]
    )'''

new_menu = '''def send_quiz_menu(event):
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
    )'''
content = content.replace(old_menu, new_menu)
content = content.replace('請選擇你要進行的測驗模式：\\n(將自動從您的單字庫抽出單字出題)', '請選擇測驗範圍與模式：\\n👉「單字庫」模式將根據您收藏的專屬單字出題\\n👉 也可以直接選擇挑戰全範圍的多益、雅思題庫喔！')

# 2. Update do_quiz logic
old_quiz_start = '''    if start:
        prompt = ""
        mode = scope if scope in ["選擇", "填空", "閱讀", "聽寫"] else "選擇"
        if mode == "聽寫":
            handle_dictation_start(event, user_id)
            return
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
            prompt = "請隨機出 3 題初中級的英文選擇題測驗。"'''

new_quiz_start = '''    if start:
        prompt = ""
        mode = scope if scope in ["選擇", "填空", "閱讀", "聽寫"] else "選擇"
        is_library_mode = scope in ["選擇", "填空", "閱讀", "聽寫", ""]
        
        if mode == "聽寫":
            handle_dictation_start(event, user_id)
            return
            
        if is_library_mode:
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
content = content.replace(old_quiz_start, new_quiz_start)

with open('multiturn.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Added external quizzes back to the menu and logic!")
