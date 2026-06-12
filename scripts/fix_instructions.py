import re

with open('multiturn.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. grammar
old_grammar = '''        elif target_mode == "grammar":
            reply_text(
                event.reply_token,
                "已切換至【文法拆解】模式 📖\\n"
                "請輸入您覺得困難的英文長句，我會幫您拆解句子結構並解說文法！"
            )'''
new_grammar = '''        elif target_mode == "grammar":
            reply_text(
                event.reply_token,
                "已切換至【文法拆解】模式 📖\\n"
                "👉 請直接輸入長難句，自動為您解析句型與文法重點"
            )'''
content = content.replace(old_grammar, new_grammar)

# 2. vocab_manager
old_vocab = '''            prompt_text = (
                "📚 已進入【單字庫】模式！\\n"
                "🔹 查詢：請點擊下方分類卡片，或直接輸入單字/分類名稱。\\n"
                "🔹 新增：請依照以下格式分兩行輸入（AI 將自動翻譯）：\\n"
                "單字\\n分類"
            )'''
new_vocab = '''            prompt_text = (
                "已切換至【單字庫】模式 📚\\n"
                "👉 點擊卡片查閱分類單字\\n"
                "👉 輸入「單字」與「分類」（分兩行），自動翻譯並新增"
            )'''
content = content.replace(old_vocab, new_vocab)

# 3. conversation
old_conv = '''        elif target_mode == "conversation":
            reply_text(
                event.reply_token,
                "已切換至【會話】模式 🗣️\\n"
                "請輸入您想練習或聊天的內容，我會以英文跟您進行會話練習！"
            )'''
new_conv = '''        elif target_mode == "conversation":
            reply_text(
                event.reply_token,
                "已切換至【會話】模式 🗣️\\n"
                "👉 隨意輸入內容，進行全英文情境對話"
            )'''
content = content.replace(old_conv, new_conv)

# 4. pronunciation
old_pron = '''        elif target_mode == "pronunciation":
            reply_text(
                event.reply_token,
                "已切換至【發音】模式 🔊\\n"
                "請直接輸入欲查詢發音的英文單字，我會為您查詢發音與發音語音檔！"
            )'''
new_pron = '''        elif target_mode == "pronunciation":
            reply_text(
                event.reply_token,
                "已切換至【發音】模式 🔊\\n"
                "👉 輸入單字，為您生成標準發音語音檔與解析"
            )'''
content = content.replace(old_pron, new_pron)

# 5. general
old_gen = '''        else: # general
            reply_text(
                event.reply_token,
                "已切換至【英文會話】模式 💬\\n"
                "現在您可以與我隨意對話，我會自動用語音及文字與您進行英文交流，或隨時點選選單切換至其他功能。"
            )'''
new_gen = '''        else: # general
            reply_text(
                event.reply_token,
                "已切換至【英文會話】模式 💬\\n"
                "👉 隨意聊天，自動回覆有聲英文語音與文字\\n"
                "👉 即時糾正您的英文文法與用詞！"
            )'''
content = content.replace(old_gen, new_gen)

with open('multiturn.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("Updated all instructions")
