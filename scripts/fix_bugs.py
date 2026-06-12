import re

with open('multiturn.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Add `parse_gemini_json` helper function
helper_func = '''
def parse_gemini_json(response, schema_class):
    import re, json
    raw = response.text or ""
    clean = re.sub(r'<think>.*?</think>', '', raw, flags=re.DOTALL).strip()
    clean = clean.replace('```json', '').replace('```', '').strip()
    return schema_class.model_validate_json(clean)
'''
if 'def parse_gemini_json' not in content:
    content = content.replace('quiz_memory = {}', helper_func + '\nquiz_memory = {}')

# 2. Fix add_vocab duplication issue
old_add_vocab_try = '''    try:
        supabase.table("vocab_memory").insert(data).execute()
        return f"已新增單字 `{word}` 到分類 `{category}`。"'''

new_add_vocab_try = '''    try:
        existing = supabase.table("vocab_memory").select("id").eq("user_id", user_id).eq("word", word).execute().data
        if existing:
            supabase.table("vocab_memory").update({"category": category, "meaning": meaning}).eq("id", existing[0]["id"]).execute()
            return f"單字 `{word}` 已更新並移動到分類 `{category}`。"
        
        supabase.table("vocab_memory").insert(data).execute()
        return f"已新增單字 `{word}` 到分類 `{category}`。"'''
content = content.replace(old_add_vocab_try, new_add_vocab_try)

# 3. Fix daily_word (always AI, fix JSON parse)
old_daily_word = '''def daily_word() -> DailyWordItem | None:
    if supabase:
        try:
            rows = (
                supabase.table("daily_words")
                .select("word,meaning,example")
                .execute()
                .data
                or []
            )
            if rows:
                row = random.choice(rows)
                return DailyWordItem(word=row['word'], meaning=row['meaning'], example=row['example'])
        except Exception as e:
            app.logger.error(f"Failed to fetch daily word from Supabase: {e}")

    if not gemini_client:
        return DailyWordItem(
            word="apple",
            meaning="蘋果",
            example="An apple a day keeps the doctor away. (一天一蘋果，醫生遠離我。)"
        )

    try:
        response = gemini_client.models.generate_content(
            model="gemini-2.5-flash",
            contents="請給我 1 個適合華語使用者學英文的每日單字，需包含：單字、詞性、中文意思與英文例句。",
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=DailyWordItem,
                system_instruction="你是一個英文老師，請一律使用繁體中文（台灣語境）回答。"
            ),
        )
        item: DailyWordItem = response.parsed
        # 自動入庫'''

new_daily_word = '''def daily_word() -> DailyWordItem | None:
    if not gemini_client:
        return DailyWordItem(
            word="apple",
            meaning="蘋果",
            example="An apple a day keeps the doctor away. (一天一蘋果，醫生遠離我。)"
        )

    try:
        response = gemini_client.models.generate_content(
            model="gemini-2.5-flash",
            contents="請隨機給我 1 個適合華語使用者學英文的每日單字（確保每次都不一樣），需包含：單字、詞性、中文意思與英文例句。",
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=DailyWordItem,
                temperature=1.0,
                system_instruction="你是一個英文老師，請一律使用繁體中文（台灣語境）回答。"
            ),
        )
        item: DailyWordItem = parse_gemini_json(response, DailyWordItem)
        # 自動入庫'''
content = content.replace(old_daily_word, new_daily_word)

# 4. Fix do_grammar_analysis (use parse_gemini_json)
content = content.replace('result = response.parsed\n        flex_content = make_grammar_flex(result)', 'result = parse_gemini_json(response, GrammarAnalysisResult)\n        flex_content = make_grammar_flex(result)')

# 5. Fix do_quiz (use parse_gemini_json)
content = content.replace('result = response.parsed\n            \n            # Save to chat history', 'result = parse_gemini_json(response, QuizGenerationResult)\n            \n            # Save to chat history')

# 6. Fix ask_gemini_multiturn (handle ConnectionTerminated)
old_ask_multiturn_try = '''    try:
        response = gemini_client.models.generate_content(
            model="gemini-2.5-flash",
            config=types.GenerateContentConfig(system_instruction=system_instruction),
            contents=history_contents,
        )
        raw_reply = response.text or "目前無法產生內容，請稍後再試。"
        model_reply = re.sub(r'<think>.*?</think>', '', raw_reply, flags=re.DOTALL).strip()
    except Exception as e:
        app.logger.error(f"Gemini multiturn error: {e}")
        model_reply = "對不起，我現在有點累了，請稍後再試。"'''

new_ask_multiturn_try = '''    try:
        response = gemini_client.models.generate_content(
            model="gemini-2.5-flash",
            config=types.GenerateContentConfig(system_instruction=system_instruction),
            contents=history_contents,
        )
        raw_reply = response.text or "目前無法產生內容，請稍後再試。"
        model_reply = re.sub(r'<think>.*?</think>', '', raw_reply, flags=re.DOTALL).strip()
    except Exception as e:
        app.logger.error(f"Gemini multiturn error: {e}")
        try:
            # Retry once on connection failure
            from google.genai import Client
            import os
            new_client = Client(api_key=os.environ.get("GEMINI_API_KEY"))
            response = new_client.models.generate_content(
                model="gemini-2.5-flash",
                config=types.GenerateContentConfig(system_instruction=system_instruction),
                contents=history_contents,
            )
            raw_reply = response.text or "目前無法產生內容，請稍後再試。"
            model_reply = re.sub(r'<think>.*?</think>', '', raw_reply, flags=re.DOTALL).strip()
        except Exception as retry_e:
            app.logger.error(f"Gemini multiturn retry error: {retry_e}")
            model_reply = "對不起，我現在有點累了，請稍後再試。"'''

content = content.replace(old_ask_multiturn_try, new_ask_multiturn_try)

with open('multiturn.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Fixes applied successfully!")
