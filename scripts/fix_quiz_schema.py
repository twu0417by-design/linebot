import re

with open('multiturn.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix QuizGenerationResult schema to make `article` required
old_schema = '''class QuizGenerationResult(BaseModel):
    title: str = Field(description="測驗標題，例如：多益單字測驗")
    article: str = Field(default="", description="閱讀測驗的短文內容，若非閱讀測驗則留空")
    questions: List[QuizQuestion]'''

new_schema = '''class QuizGenerationResult(BaseModel):
    title: str = Field(description="測驗標題，例如：多益單字測驗")
    article: str = Field(description="閱讀測驗的短文內容，若是閱讀測驗請務必輸出超過50字的英文短文，若非閱讀測驗請一定要輸出空字串 \\"\\"")
    questions: List[QuizQuestion]'''

content = content.replace(old_schema, new_schema)

# Fix do_quiz system instruction
old_quiz_gen = '''        try:
            response = gemini_client.models.generate_content(
                model="gemini-2.5-flash",
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=QuizGenerationResult,
                    system_instruction=QUIZ_SYSTEM_PROMPT
                ),
                contents=prompt,
            )'''

new_quiz_gen = '''        try:
            if mode == "閱讀":
                sys_inst = "你是一個英文閱讀測驗出題系統。請務必在 article 欄位撰寫一篇包含給定單字的英文短文，並根據該短文出 3 題選擇題。"
            elif mode == "填空":
                sys_inst = "你是一個英文填空測驗出題系統。請針對每個給定的單字出一個情境句子，並在句子中挖空（使用 ___），讓使用者從 A/B/C/D 選項中選擇正確的單字填入。"
            else:
                sys_inst = QUIZ_SYSTEM_PROMPT

            response = gemini_client.models.generate_content(
                model="gemini-2.5-flash",
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=QuizGenerationResult,
                    system_instruction=sys_inst
                ),
                contents=prompt,
            )'''

content = content.replace(old_quiz_gen, new_quiz_gen)

with open('multiturn.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Quiz generation logic and schema fixed!")
