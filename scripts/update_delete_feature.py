import re

with open('multiturn.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Add handle delete logic in handle_text_message
# Search for handle_text_message(event):
# Add the interception right before the `elif target_mode == ...` or after `0a.`
delete_interception = '''
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
'''
if "刪除單字:" not in content:
    content = content.replace('    # 1. 根據使用者當前模式進行處理', delete_interception + '\n    # 1. 根據使用者當前模式進行處理')

# 2. Add delete_vocab and delete_vocab_category functions right after add_vocab
delete_funcs = '''
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
'''
if "def delete_vocab" not in content:
    content = content.replace('def get_vocab_list', delete_funcs + '\n\ndef get_vocab_list')

# 3. Add delete button in make_vocab_list_flex
old_action = '''                    {
                        "type": "text",
                        "text": "🔊",
                        "align": "end",
                        "size": "sm",
                        "action": {
                            "type": "message",
                            "label": "發音",
                            "text": f"發音: {r.get('word', '')}"
                        },
                        "flex": 1
                    }'''
new_action = '''                    {
                        "type": "box",
                        "layout": "horizontal",
                        "flex": 2,
                        "justifyContent": "flex-end",
                        "contents": [
                            {
                                "type": "text",
                                "text": "🔊",
                                "align": "center",
                                "size": "sm",
                                "action": {
                                    "type": "message",
                                    "label": "發音",
                                    "text": f"發音: {r.get('word', '')}"
                                }
                            },
                            {
                                "type": "text",
                                "text": "🗑️",
                                "align": "center",
                                "size": "sm",
                                "margin": "md",
                                "action": {
                                    "type": "message",
                                    "label": "刪除",
                                    "text": f"刪除單字: {r.get('word', '')}"
                                }
                            }
                        ]
                    }'''
if "🗑️" not in content:
    content = content.replace(old_action, new_action)


# 4. Add delete button in make_category_carousel_flex
# Replace footer content for categories
old_footer = '''            "footer": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "button",
                        "style": "primary",
                        "color": "#1A73E8",
                        "action": {"type": "message", "label": "查看", "text": cat}
                    }
                ]
            }'''
new_footer = '''            "footer": {
                "type": "box",
                "layout": "vertical",
                "spacing": "sm",
                "contents": [
                    {
                        "type": "button",
                        "style": "primary",
                        "color": "#1A73E8",
                        "action": {"type": "message", "label": "查看", "text": cat}
                    },
                    {
                        "type": "button",
                        "style": "secondary",
                        "color": "#FF4D4F",
                        "action": {"type": "message", "label": "刪除", "text": f"刪除分類: {cat}"}
                    }
                ]
            }'''
if "刪除分類:" not in content:
    content = content.replace(old_footer, new_footer)

with open('multiturn.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("Done!")
