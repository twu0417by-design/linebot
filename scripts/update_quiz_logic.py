import re

with open('multiturn.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update QuizGenerationResult schema
old_schema = '''class QuizGenerationResult(BaseModel):
    title: str = Field(description="測驗標題，例如：多益單字測驗")
    questions: List[QuizQuestion]'''
new_schema = '''class QuizGenerationResult(BaseModel):
    title: str = Field(description="測驗標題，例如：多益單字測驗")
    article: str = Field(default="", description="閱讀測驗的短文內容，若非閱讀測驗則留空")
    questions: List[QuizQuestion]'''
content = content.replace(old_schema, new_schema)

# 2. Update make_quiz_generation_flex
old_flex_header = '''    body_contents = [
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
    ]'''
new_flex_header = '''    body_contents = [
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
        })'''
content = content.replace(old_flex_header, new_flex_header)

# 3. Update send_quiz_menu
old_menu = '''def send_quiz_menu(event):
    quick_reply = QuickReply(
        items=[
            QuickReplyItem(action=MessageAction(label="📚 單字庫測驗", text="馬上測驗")),
            QuickReplyItem(action=MessageAction(label="💼 多益 (TOEIC)", text="測驗 多益")),
            QuickReplyItem(action=MessageAction(label="🎓 雅思 (IELTS)", text="測驗 雅思")),
            QuickReplyItem(action=MessageAction(label="📈 商業英文", text="測驗 商業英文"))
        ]
    )'''
new_menu = '''def send_quiz_menu(event):
    quick_reply = QuickReply(
        items=[
            QuickReplyItem(action=MessageAction(label="📚 選擇題 (單字庫)", text="測驗 選擇")),
            QuickReplyItem(action=MessageAction(label="📝 填空題 (單字庫)", text="測驗 填空")),
            QuickReplyItem(action=MessageAction(label="📖 閱讀題 (單字庫)", text="測驗 閱讀"))
        ]
    )'''
content = content.replace(old_menu, new_menu)
content = content.replace('請選擇你要進行的測驗範圍：\\n(若選擇單字庫測驗，將優先從你的記憶庫出題)', '請選擇你要進行的測驗模式：\\n(將自動從您的單字庫抽出單字出題)')

# 4. Update do_quiz logic
old_quiz_logic = '''    if start:
        prompt = ""
        if scope:
            prompt = f"請幫我出 3 題關於「{scope}」的英文選擇題測驗。"
        else:
            if supabase:
                try:
                    res = supabase.table("vocab_memory").select("word,meaning").eq("user_id", user_id).execute()
                    data = res.data or []
                    if len(data) < 3:
                        prompt = "使用者單字庫目前單字不足，請幫我隨機出 3 題初中級的英文單字或文法選擇題測驗。"
                    else:
                        words = random.sample(data, 3)
                        words_str = ", ".join([f"{w['word']} ({w['meaning']})" for w in words])
                        prompt = f"請用這三個單字幫我出 3 題英文選擇題測驗：{words_str}。"
                except Exception as e:
                    app.logger.error(f"Quiz fetch error: {e}")
                    prompt = "請隨機出 3 題初中級的英文單字選擇題測驗。"
            else:
                prompt = "請隨機出 3 題初中級的英文單字選擇題測驗。"'''

new_quiz_logic = '''    if start:
        prompt = ""
        mode = scope if scope in ["選擇", "填空", "閱讀"] else "選擇"
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
content = content.replace(old_quiz_logic, new_quiz_logic)


# Also ensure that user_input intercepts check for our new quick reply labels.
# In handle_text_message
# old: if user_input.startswith("測驗") or user_input.startswith("隨堂測驗") or user_input == "馬上測驗":
# We just need to make sure `馬上測驗` fallsback to `測驗 選擇`. Wait, we already replaced `馬上測驗` with `測驗 選擇` in send_quiz_menu.

with open('multiturn.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("Done!")
