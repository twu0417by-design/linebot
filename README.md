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
```

## 4) LINE 指令
- `翻譯: <文章內容>`
- `記憶新增: <分類>|<單字>|<中文意思>`
- `記憶查詢`
- `記憶查詢: <分類>`
- `每日單字`
- `會話: <你想練習或想修正的句子>`
- `發音: <單字>`
- `生圖: <描述>`
- 直接上傳圖片：觸發圖片理解 + 圖像相關詞彙教學

## 5) 啟動方式（Space 會自動使用）
`Dockerfile` 已設定：

```bash
gunicorn -b 0.0.0.0:7860 multiturn:app
```
