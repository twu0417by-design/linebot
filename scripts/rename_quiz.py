import re

with open('multiturn.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update the label and text in send_quiz_menu
content = content.replace('"label": "選擇題", "text": f"測驗 選擇 {s[\'level\']}"', '"label": "單字題", "text": f"測驗 單字 {s[\'level\']}"')

# 2. Update do_quiz parsing logic
content = content.replace('parts[0] in ["選擇", "填空", "閱讀", "聽寫"] else "選擇"', 'parts[0] in ["單字", "選擇", "填空", "閱讀", "聽寫"] else "單字"')

# 3. Handle backwards compatibility: map 選擇 to 單字 internally
# Wait, actually just update the if conditions
content = content.replace('is_library_mode = scope in ["選擇", "填空", "閱讀", "聽寫", ""]', 'is_library_mode = scope in ["單字", "選擇", "填空", "閱讀", "聽寫", ""]')

# Let's verify where mode is checked. If it's `mode == "填空"` and `mode == "閱讀"`, the `else` handles `單字`. So we don't need to change `if mode == "單字":` anywhere because it's in the `else:` blocks!
# Wait, let's make sure the default mode is "單字" and not "選擇". Yes, I did that in step 2.

# 4. In do_quiz prompt fallbacks, change "選擇題測驗" to "單字選擇題測驗" just to be safe
content = content.replace('初中級的英文選擇題測驗', '初中級的英文單字選擇題測驗')

with open('multiturn.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Renamed 選擇題 to 單字題")
