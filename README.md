---
title: Linebot-Language-Learning
emoji: 📘
colorFrom: blue
colorTo: green
sdk: docker
pinned: false
---

# LINE x Gemini 語言學習機器人（Hugging Face Spaces）

此專案可直接部署於 Hugging Face Spaces（Docker），整合：
- LINE Messaging API Webhook
- Google Gemini（文字生成、圖像生成、圖像理解）
- Supabase（詞彙記憶、分類、每日單字）

## 1) Space 環境變數
請在 Hugging Face Space 的 `Settings > Variables and secrets` 設定：

- `LINE_CHANNEL_SECRET`
- `LINE_CHANNEL_ACCESS_TOKEN`
- `GEMINI_API_KEY`
- `SPACE_HOST`（例如 `your-space-name.hf.space`，不要加 `https://`）
- `SUPABASE_URL`
- `SUPABASE_KEY`

## 2) LINE Webhook 設定
- Webhook URL：`https://<你的SPACE_HOST>/`
- 開啟 `Use webhook`

## 3) Supabase 建表 SQL
在 Supabase SQL Editor 執行：

```sql
create table if not exists vocab_memory (
  id bigint generated always as identity primary key,
  user_id text not null,
  category text not null,
  word text not null,
  meaning text not null,
  created_at timestamptz default now()
);

create table if not exists daily_words (
  id bigint generated always as identity primary key,
  word text not null,
  meaning text not null,
  example text not null,
  created_at timestamptz default now()
);

create table if not exists chat_history (
  id bigint generated always as identity primary key,
  user_id text not null,
  role text not null,
  content text not null,
  created_at timestamptz default now()
);

-- （選用，可用於跨 Worker 持久化儲存使用者模式，若不建表則預設使用伺服器記憶體儲存狀態）
create table if not exists user_states (
  user_id text primary key,
  mode text not null,
  updated_at timestamptz default now()
);
```

## 4) 升級版亮點功能
- 🎛️ **功能切換模式**：不需每次重複輸入功能名稱/前綴。輸入對應功能指令（如「翻譯」、「會話」、「發音」、「記憶新增」、「記憶查詢」、「每日單字」）後，Bot 會自動切換到該模式。在此模式下的所有後續對話皆會視為該功能輸入，直到輸入「退出」或點選其他功能為止。
- 📱 **功能選擇 Rich Menu**：內建精美的 2x3 網格 Rich Menu 選單，包含：翻譯、記憶新增、記憶查詢、每日單字、會話、發音。點擊即可直接切換模式。
- 🗣️ **多輪會話練習**：在「會話」模式下，系統會自動載入最近的對話歷史，讓您與 AI 進行有前後文的連續英文會話練習。
- 🔊 **語音原生播放**：在「發音」模式下，輸入單字，系統除了文字說明外，會直接回傳 LINE 原生語音訊息（AudioMessage），可直接於聊天室點擊播放。
- 📷 **圖片自動分析與記憶**：上傳圖片後，AI 除解說圖片外，會自動將 5 個相關英文單字直接匯入您的 Supabase 單字庫。
- 💡 **每日單字自動入庫**：若單字庫中沒有單字，系統由 Gemini 產生的新單字會自動新增至 `daily_words` 表，持續擴充題庫。
- ✨ **卡片化 Flex Message 美化**：針對「翻譯」、「發音」、「每日單字」、「單字庫查詢」、「記憶新增」以及「圖片自動分析」等功能，全部升級為 LINE 官方 Flex Message 卡片排版，融合圓角標籤、色彩視覺和快捷點擊動作（如點擊喇叭 🔊 直接聽發音），大幅提升視覺與互動體驗。

## 5) LINE 模式切換指令
點選 Rich Menu 選單或直接於聊天室輸入以下指令進行模式切換：
- `翻譯`：切換至【翻譯】模式，直接輸入待翻譯文章或句子。
- `記憶新增`：切換至【記憶新增】模式，輸入格式：`分類|單字|中文意思`。
- `記憶查詢`：切換至【記憶查詢】模式，輸入分類名稱（如：食物）或輸入 `全部` 進行查詢。
- `每日單字`：切換至【每日單字】模式，點擊或輸入任意內容即會推薦新單字。
- `會話`：切換至【會話】模式，直接輸入對話與 AI 進行口說/寫作演練。
- `發音`：切換至【發音】模式，直接輸入英文單字取得英美發音及原生語音檔。
- `退出` / `一般聊天`：切換回【一般聊天】模式，可隨意向 AI 提問。
- **直接上傳圖片**：自動進行圖像理解，並自動將產生的單字匯入單字庫中（不限模式）。

## 6) 啟動與 Rich Menu 初始化
專案啟動時會自動讀取 `LINE_CHANNEL_ACCESS_TOKEN` 並自動向 LINE 伺服器註冊預設的 Rich Menu 及其底圖（`rich_menu.png`）。

手動註冊 Rich Menu 腳本：
```bash
python init_rich_menu.py
```

`Dockerfile` 已設定自動啟動：
```bash
gunicorn -b 0.0.0.0:7860 multiturn:app
```

## 7) 6/4 更新日誌 (Updates)
- 🔗 **網址自動摘要**：貼上網址即自動抓取內文，並由 AI 摘要重點與關鍵單字。
- 📖 **文法拆解模式**：專屬的文法拆解模式，貼上長句立刻解析句子結構（主詞、動詞、受詞）與重要文法觀念。
- 🎓 **互動式隨堂測驗 (卡片化)**：全新升級的測驗模式！
  - 支援「快速回覆 (Quick Reply)」選單：點擊測驗後可一鍵選擇「單字庫、多益、雅思、商業英文」等不同出題範圍。
  - 出題與批改全面升級為精緻的 Flex Message 卡片介面。
  - 答題超簡潔：直接回傳如 `ABC` 即可瞬間獲得批改與詳解。
  - 強化記憶系統：透過內部快取解決 AI 幻覺與記憶遺失問題，精準對應批改考卷。
- 🗣️ **英文會話教練**：一般聊天模式全面進化為英文對話教練，隨時用語音及文字糾正文法與用詞。
- 📱 **6 宮格 Rich Menu 重新設計**：替換全新 AI 產生的底圖，並重新綁定最新六大功能（翻譯、文法、每日單字、測驗、記憶查詢、英文會話）。
