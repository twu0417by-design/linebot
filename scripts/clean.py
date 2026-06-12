import os
with open("multiturn.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

new_lines = []
for line in lines:
    if '💡 若要回到一般聊天，請輸入「退出」或「一般聊天」。' in line:
        # Instead of replacing, just skip it or leave it empty so we don't break syntax
        # Actually some of these are inside multi-line strings, like:
        # "請輸入您想新增的單字...\n\n"
        # "💡 若要回到一般聊天，請輸入「退出」或「一般聊天」。"
        # Since Python implicitly concatenates literal strings, deleting the line is mostly safe.
        continue
    new_lines.append(line)

with open("multiturn.py", "w", encoding="utf-8") as f:
    f.writelines(new_lines)
