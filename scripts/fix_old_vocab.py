import os
import json
from supabase import create_client, Client
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("Supabase credentials not found.")
    exit(1)

if not GEMINI_API_KEY:
    print("Gemini API key not found.")
    exit(1)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.5-flash")

def fix_old_vocab():
    print("Fetching vocab memory...")
    response = supabase.table("vocab_memory").select("*").execute()
    data = response.data
    
    if not data:
        print("No vocab memory found.")
        return
        
    updated_count = 0
    for row in data:
        meaning = row.get("meaning", "")
        # If meaning doesn't start with a parenthesis or bracket, it likely misses the part of speech
        if not meaning.startswith("(") and not meaning.startswith("[") and not meaning.startswith("（"):
            word = row["word"]
            print(f"Updating '{word}' (Old meaning: {meaning})...")
            
            prompt = f"請提供英文單字/片語 '{word}' 的詞性與原本的繁體中文意思 '{meaning}'。格式請用「(詞性) 中文意思」，例如「(n.) {meaning}」。只需回答最常見的詞性與意思，不要加上任何其他說明。"
            
            try:
                gemini_res = model.generate_content(prompt)
                new_meaning = gemini_res.text.strip()
                print(f"  -> New meaning: {new_meaning}")
                
                # Update in supabase
                supabase.table("vocab_memory").update({"meaning": new_meaning}).eq("id", row["id"]).execute()
                updated_count += 1
            except Exception as e:
                print(f"Failed to update '{word}': {e}")
                
    print(f"Update complete! Fixed {updated_count} rows.")

if __name__ == "__main__":
    fix_old_vocab()
