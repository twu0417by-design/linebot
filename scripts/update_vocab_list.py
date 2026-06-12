import re

with open('multiturn.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update get_vocab_list limit from 15 to 50
content = content.replace('.limit(15).execute()', '.limit(50).execute()')

# 2. Rewrite make_vocab_list_flex
old_func_pattern = re.compile(r'def make_vocab_list_flex\(rows: list, category: str \| None\) -> dict:.*?return \{(?:\n\s+.*)*?\n    \}\n', re.DOTALL)

new_func = '''def make_vocab_list_flex(rows: list, category: str | None) -> dict:
    base_title = f"📚 我的單字庫 ({category})" if category else "📚 我的單字庫"
    
    if not rows:
        return {
            "type": "bubble",
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": base_title,
                        "weight": "bold",
                        "size": "md",
                        "color": "#111111"
                    },
                    {
                        "type": "text",
                        "text": "目前沒有任何詞彙記錄喔！請先切換至「記憶新增」模式，並依照分行格式建立單字庫！",
                        "wrap": True,
                        "color": "#8c8c8c",
                        "size": "sm",
                        "margin": "md"
                    }
                ]
            }
        }
        
    bubbles = []
    chunk_size = 10
    total_pages = (len(rows) - 1) // chunk_size + 1
    
    for i in range(0, len(rows), chunk_size):
        chunk = rows[i:i+chunk_size]
        page_num = (i // chunk_size) + 1
        page_title = base_title if total_pages == 1 else f"{base_title} (第 {page_num}/{total_pages} 頁)"
        
        vocab_contents = []
        for index, r in enumerate(chunk):
            if index > 0:
                vocab_contents.append({
                    "type": "separator",
                    "margin": "sm"
                })
                
            vocab_contents.append({
                "type": "box",
                "layout": "horizontal",
                "margin": "sm",
                "alignItems": "center",
                "contents": [
                    {
                        "type": "box",
                        "layout": "vertical",
                        "backgroundColor": "#E8F0FE",
                        "cornerRadius": "md",
                        "paddingAll": "2px",
                        "alignItems": "center",
                        "justifyContent": "center",
                        "flex": 3,
                        "contents": [
                            {
                                "type": "text",
                                "text": r.get('category', ''),
                                "size": "xxs",
                                "color": "#1A73E8",
                                "weight": "bold",
                                "maxLines": 1
                            }
                        ]
                    },
                    {
                        "type": "text",
                        "text": r.get('word', ''),
                        "weight": "bold",
                        "color": "#333333",
                        "size": "sm",
                        "margin": "md",
                        "flex": 4,
                        "wrap": True
                    },
                    {
                        "type": "text",
                        "text": r.get('meaning', ''),
                        "color": "#666666",
                        "size": "sm",
                        "flex": 4,
                        "wrap": True
                    },
                    {
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
                    }
                ]
            })
            
        bubbles.append({
            "type": "bubble",
            "header": {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": "#1A73E8",
                "contents": [
                    {
                        "type": "text",
                        "text": page_title,
                        "color": "#ffffff",
                        "weight": "bold",
                        "size": "md"
                    }
                ]
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "spacing": "sm",
                "contents": vocab_contents
            }
        })
        
    if len(bubbles) == 1:
        return bubbles[0]
    else:
        return {"type": "carousel", "contents": bubbles[:12]}
'''

if not old_func_pattern.search(content):
    print("Function not found with regex.")
else:
    content = old_func_pattern.sub(new_func, content)
    with open('multiturn.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Done")
