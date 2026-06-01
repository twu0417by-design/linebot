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
```

## 4) 升級版亮點功能
- 🗣️ **多輪會話練習**：不需額外前綴，或使用 `會話:`，系統會自動載入最近的對話歷史，讓您與 AI 進行有前後文的連續會話練習。
- 🔊 **語音原生播放**：輸入 `發音: <單字>`，系統除了文字說明外，會直接回傳 LINE 原生語音訊息（AudioMessage），可直接於聊天室點擊播放。
- 📷 **圖片自動分析與記憶**：上傳圖片後，AI 除解說圖片外，會自動將 5 個相關英文單字直接匯入您的 Supabase 單字庫。
- 💡 **每日單字自動入庫**：若單字庫中沒有單字，系統由 Gemini 產生的新單字會自動新增至 `daily_words` 表，持續擴充題庫。
- ✨ **卡片化 Flex Message 美化**：針對「翻譯」、「發音」、「每日單字」、「單字庫查詢」、「記憶新增」以及「圖片自動分析」等功能，全部升級為 LINE 官方 Flex Message 卡片排版，融合圓角標籤、色彩視覺和快捷點擊動作（如點擊喇叭 🔊 直接聽發音），大幅提升視覺與互動體驗。

## 5) LINE 指令
- `翻譯: <文章內容>`
- `記憶新增: <分類>|<單字>|<中文意思>`
- `記憶查詢`
- `記憶查詢: <分類>`
- `每日單字`（從單字庫隨機挑選，若無則由 AI 產生並自動入庫）
- `會話: <你想練習或想修正的句子>`（支援多輪歷史記憶）
- `發音: <單字>`（同時回傳文字解釋與可直接播放的語音訊息）
- `生圖: <描述>`（採用最新 Imagen 3.0 圖像生成模型）
- 直接上傳圖片：自動進行圖像理解，並自動將產生的單字匯入單字庫中


## 5) 啟動方式（Space 會自動使用）
`Dockerfile` 已設定：

```bash
gunicorn -b 0.0.0.0:7860 multiturn:app
```
