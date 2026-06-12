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
- 📱 **功能選擇 Rich Menu**：內建精美的 2x3 網格 Rich Menu 選單，包含：翻譯、文法、每日單字、測驗、記憶查詢、英文會話。點擊即可直接切換模式。
- 🗣️ **多輪會話練習**：在「會話」模式下，系統會自動載入最近的對話歷史，讓您與 AI 進行有前後文的連續英文會話練習。
- 🔊 **語音原生播放**：在「發音」模式下，輸入單字，系統除了文字說明外，會直接回傳 LINE 原生語音訊息（AudioMessage），可直接於聊天室點擊播放。
- 📷 **圖片自動分析與記憶**：上傳圖片後，AI 除解說圖片外，會自動將 5 個相關英文單字直接匯入您的 Supabase 單字庫。
- 💡 **每日單字自動入庫**：若單字庫中沒有單字，系統由 Gemini 產生的新單字會自動新增至 `daily_words` 表，持續擴充題庫。
- ✨ **卡片化 Flex Message 美化**：針對「翻譯」、「發音」、「每日單字」、「單字庫查詢」、「記憶新增」以及「圖片自動分析」等功能，全部升級為 LINE 官方 Flex Message 卡片排版，融合圓角標籤、色彩視覺和快捷點擊動作（如點擊喇叭 🔊 直接聽發音），大幅提升視覺與互動體驗。

## 5) LINE 模式切換指令
點選 Rich Menu 選單或直接於聊天室輸入以下指令進行模式切換：
- `翻譯`：切換至【翻譯】模式，輸入待翻譯文字、網址，或直接傳送照片。
- `文法`：切換至【文法拆解】模式，輸入長難句由 AI 解析句型。
- `每日單字`：點選即會隨機由 AI 推送一個全新的英文單字與例句。
- `測驗`：開啟旋轉木馬測驗大廳，支援 16 種難度與題型組合（單字、填空、閱讀、聽寫）。
- `記憶查詢`：切換至【單字庫】模式，透過卡片或輸入指令查詢與新增單字。
- `英文會話`：切換至【英文會話】教練模式，與 AI 進行即時互動對話，AI 將自動用語音及文字回覆並糾正錯誤。
- `退出`：退出所有特殊模式。
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

## 8) 6/12 更新日誌 (Updates)
- 🧠 **AI 核心解析器強化**：新增自訂的 JSON 解析器，能自動過濾 Gemini 2.5 夾帶的 `<think>` 隱藏思考過程，大幅提升「文法拆解」與「測驗產生」的穩定度，徹底解決偶發的格式錯誤。
- 🔄 **會話連線自動修復**：為多輪「英文會話」功能導入自動重試與客戶端重建機制，大幅降低因網路瞬斷造成的「無法對話」問題。
- 📚 **單字庫防重複機制**：新增單字時自動檢查，若單字已存在則自動更新分類與意思，避免無效的重複記憶。
- 📅 **每日單字即時隨機化**：移除靜態資料庫撈取，改為每次呼叫皆由 AI 即時生成，保證每日都能學到全新單字。
- 🎡 **測驗大廳 16 模式大升級 (Carousel Flex)**：
  - 將測驗選單重構為精美的旋轉木馬 (Carousel) 形式，突破按鈕數量限制。
  - 支援 **4 大範圍**：📚 專屬單字庫、🌱 初級、⭐ 中級、🔥 高級。
  - 支援 **4 大題型**：單字題、填空題、閱讀題、🎧 聽寫題。
  - 共計 16 種組合，無論是想複習個人專屬單字，或是想挑戰隨機高級字彙的聽寫測驗，都能一鍵啟動！
- 📝 **測驗 Prompt 深度優化**：針對「閱讀」與「填空」測驗編寫獨立的高權限系統提示詞，並嚴格定義 JSON Schema 的必填選項，強迫 AI 產出 50 字以上的英文短文與挖空情境句，確保測驗題型的多樣性與精準度。
- ✏️ **填空題批量作答**：將填空題升級為一次出題，並支援使用「換行」一次提交多題答案，大幅提升複習效率。
- 🏷️ **題型名稱更新**：為符合實際測驗體驗，將原「選擇題」正式更名為「單字題」。
- 🗃️ **單字庫精準讀取與詞性支援**：
  - 修復了單字庫查詢時偶發讀取到「每日單字」模式紀錄的問題。
  - 強化所有「收藏」功能，現在一鍵加入單字庫時皆會自動附上對應詞性（例如 `(n.)`、`(v.)`），並透過指令自動修復了舊有資料的詞性缺漏。
- 🧹 **專案結構優化**：將系統維護與資料庫一次性操作腳本統一整理至 `scripts/` 資料夾中，讓主程式結構更加清晰。
