import re

with open("multiturn.py", "r", encoding="utf-8") as f:
    content = f.read()

# 1. Add get_vocab_categories
categories_func = """
def get_vocab_categories(user_id: str) -> list:
    if not supabase:
        return []
    try:
        rows = supabase.table("vocab_memory").select("category").eq("user_id", user_id).execute().data or []
        categories = sorted(list(set(r["category"] for r in rows if r.get("category"))))
        return categories
    except Exception as e:
        app.logger.error(f"get_vocab_categories failed: {e}")
        return []
"""
if "def get_vocab_categories" not in content:
    content = content.replace("def daily_word() -> DailyWordItem | None:", categories_func + "\n\ndef daily_word() -> DailyWordItem | None:")

# 2. Add make_category_carousel_flex
category_carousel_func = """
def make_category_carousel_flex(categories: list) -> dict:
    if not categories:
        return {
            "type": "bubble",
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {"type": "text", "text": "📚 我的單字庫", "weight": "bold", "size": "md"},
                    {"type": "text", "text": "目前還沒有任何分類喔！", "wrap": True, "size": "sm", "color": "#8c8c8c", "margin": "md"}
                ]
            }
        }
    
    bubbles = []
    # Always add an "All" option
    bubbles.append({
        "type": "bubble",
        "size": "nano",
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {"type": "text", "text": "全部單字", "weight": "bold", "size": "md", "align": "center"}
            ],
            "justifyContent": "center",
            "alignItems": "center"
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "button",
                    "style": "primary",
                    "color": "#1DB446",
                    "action": {"type": "message", "label": "查看", "text": "全部"}
                }
            ]
        }
    })
    
    for cat in categories[:9]:  # limit to 10 bubbles total
        bubbles.append({
            "type": "bubble",
            "size": "nano",
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {"type": "text", "text": cat, "weight": "bold", "size": "md", "align": "center", "wrap": True}
                ],
                "justifyContent": "center",
                "alignItems": "center"
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "button",
                        "style": "secondary",
                        "action": {"type": "message", "label": "查看", "text": f"{cat}"}
                    }
                ]
            }
        })
    return {"type": "carousel", "contents": bubbles}
"""
if "def make_category_carousel_flex" not in content:
    content = content.replace("def make_vocab_list_flex", category_carousel_func + "\n\ndef make_vocab_list_flex")

# 3. Modify make_vocab_list_flex to support carousel chunking
new_vocab_list_flex = """
def make_vocab_list_flex(rows: list, category: str | None) -> dict:
    title = f"📚 我的單字庫 ({category})" if category and category != '全部' else "📚 我的單字庫 (最近 15 筆)"
    
    if not rows:
        return {
            "type": "bubble",
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {"type": "text", "text": title, "weight": "bold", "size": "md"},
                    {"type": "text", "text": "目前這個分類沒有任何詞彙喔！", "wrap": True, "color": "#8c8c8c", "size": "sm", "margin": "md"}
                ]
            }
        }
        
    bubbles = []
    chunk_size = 5
    for i in range(0, len(rows), chunk_size):
        chunk = rows[i:i+chunk_size]
        vocab_contents = []
        for r in chunk:
            vocab_contents.append({
                "type": "box",
                "layout": "horizontal",
                "margin": "md",
                "contents": [
                    {
                        "type": "box",
                        "layout": "vertical",
                        "flex": 4,
                        "contents": [
                            {"type": "text", "text": r["word"], "weight": "bold", "size": "md", "color": "#111111", "wrap": True},
                            {"type": "text", "text": r["meaning"], "size": "sm", "color": "#8c8c8c", "wrap": True}
                        ]
                    },
                    {
                        "type": "box",
                        "layout": "vertical",
                        "flex": 1,
                        "contents": [
                            {
                                "type": "button",
                                "style": "secondary",
                                "height": "sm",
                                "action": {"type": "message", "label": "🔊", "text": f"發音: {r['word']}"}
                            }
                        ]
                    }
                ]
            })
            vocab_contents.append({"type": "separator", "margin": "md"})
            
        if vocab_contents:
            vocab_contents.pop() # remove last separator

        bubbles.append({
            "type": "bubble",
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {"type": "text", "text": title, "weight": "bold", "size": "md", "color": "#1DB446"},
                    {"type": "separator", "margin": "md"},
                    {"type": "box", "layout": "vertical", "margin": "md", "contents": vocab_contents}
                ]
            }
        })
        
    if len(bubbles) == 1:
        return bubbles[0]
    return {"type": "carousel", "contents": bubbles[:10]}
"""
content = re.sub(r'def make_vocab_list_flex.*?return \{"type": "bubble", "body": .*?\}\s+\]\s+\}\s+\}', new_vocab_list_flex, content, flags=re.DOTALL)

# 4. Mode mappings
content = content.replace('"記憶新增": "vocab_add",\n    "記憶查詢": "vocab_query",', '"記憶新增": "vocab_manager",\n    "記憶查詢": "vocab_manager",\n    "單字庫": "vocab_manager",')

# 5. Handle routing for mode switch
old_vocab_switch = """        elif target_mode == "vocab_add":
            reply_text(
                event.reply_token,
                "已切換至【記憶新增】模式 💾\\n"
                "請分三行輸入您想新增的單字，格式如下：\\n"
                "分類\\n單字\\n中文意思\\n\\n"
                "例如：\\n食物\\napple\\n蘋果\\n\\n"
            )
        elif target_mode == "vocab_query":
            # 切換時，直接幫他查詢全部，並附上提示文字
            do_vocab_query(event, user_id, category=None, send_prompt=True)"""
            
new_vocab_switch = """        elif target_mode == "vocab_manager":
            categories = get_vocab_categories(user_id)
            flex_content = make_category_carousel_flex(categories)
            prompt_text = (
                "📚 已進入【單字庫】模式！\\n\\n"
                "🔹 查詢：請點擊上方分類卡片，或直接輸入單字/分類名稱。\\n"
                "🔹 新增：請依照以下格式分三行輸入：\\n\\n"
                "分類\\n單字\\n中文意思"
            )
            messages = [
                FlexMessage(alt_text="分類選擇", contents=FlexContainer.from_json(json.dumps(flex_content))),
                TextMessage(text=prompt_text)
            ]
            with ApiClient(configuration) as api_client:
                line_api = MessagingApi(api_client)
                line_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=messages
                    )
                )"""

content = content.replace(old_vocab_switch, new_vocab_switch)

# 6. Replace do_vocab_query entirely to support vocab_manager and remove send_prompt logic
new_vocab_manager = """
def do_vocab_manager(event, user_id: str, raw_input: str):
    if not supabase:
        reply_text(event.reply_token, "尚未設定 Supabase，請先設定 SUPABASE_URL / SUPABASE_KEY。")
        return
        
    parts = [x.strip() for x in raw_input.split('\\n') if x.strip()]
    if len(parts) == 3:
        # Add mode
        category, word, meaning = parts[0], parts[1], parts[2]
        res_text = add_vocab(user_id, category, word, meaning)
        if "已新增單字" in res_text:
            flex_content = make_vocab_added_flex(category, word, meaning)
            with ApiClient(configuration) as api_client:
                line_api = MessagingApi(api_client)
                line_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[FlexMessage(alt_text="單字已成功入庫", contents=FlexContainer.from_json(json.dumps(flex_content)))],
                    )
                )
        else:
            reply_text(event.reply_token, res_text)
    else:
        # Query mode
        category = raw_input if raw_input and raw_input != '全部' else None
        # Could also be querying a specific word, let's just query by category or fallback
        # Wait, if they query by word? get_vocab_list is only by category right now.
        # We will enhance get_vocab_list to search both category and word.
        rows = get_vocab_list(user_id, category)
        flex_content = make_vocab_list_flex(rows, category)
        messages = [FlexMessage(alt_text="我的單字庫", contents=FlexContainer.from_json(json.dumps(flex_content)))]
        with ApiClient(configuration) as api_client:
            line_api = MessagingApi(api_client)
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=messages,
                )
            )

def do_vocab_add(event, user_id: str, raw_input: str):
    do_vocab_manager(event, user_id, raw_input)

def do_vocab_query(event, user_id: str, category: str = None, send_prompt: bool = False):
    do_vocab_manager(event, user_id, category or '全部')
"""

# Instead of blindly replacing `do_vocab_add` and `do_vocab_query`, I will replace them from content
content = re.sub(r'def do_vocab_add\(event, user_id: str, raw_input: str\):.*?def do_daily_word', lambda m: new_vocab_manager + "\n\ndef do_daily_word", content, flags=re.DOTALL)

# 7. Modify current mode handler
old_handler = """    elif current_mode == "vocab_add":
        do_vocab_add(event, user_id, user_input)
        
    elif current_mode == "vocab_query":
        # 查詢特定分類，或者不帶參數查詢全部
        category = user_input if user_input and user_input != "全部" else None
        do_vocab_query(event, user_id, category=category)"""
        
new_handler = """    elif current_mode == "vocab_manager":
        do_vocab_manager(event, user_id, user_input)"""

content = content.replace(old_handler, new_handler)

with open("multiturn.py", "w", encoding="utf-8") as f:
    f.write(content)

print("Patch applied")
