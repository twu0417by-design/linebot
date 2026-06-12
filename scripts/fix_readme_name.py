import re

with open('README.md', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace("支援 16 種難度與題型組合（選擇、填空、閱讀、聽寫）。", "支援 16 種難度與題型組合（單字、填空、閱讀、聽寫）。")
content = content.replace("支援 **4 大題型**：選擇題、填空題、閱讀題、🎧 聽寫題。", "支援 **4 大題型**：單字題、填空題、閱讀題、🎧 聽寫題。")

with open('README.md', 'w', encoding='utf-8') as f:
    f.write(content)
print("Updated README")
