# Nobunaga Lineup Builder

**信長之野望：真戰** 編隊工具 — 從 game8.jp 爬取武將/戰法資料，透過 LLM 翻譯為繁體中文，並提供互動式編隊介面。

## Pipeline 總覽

![Pipeline Overview](doc/overview.jpg)

## 功能

- 147+ 位武將資料（數值、特性、技能、頭像）
- 227+ 個戰法翻譯（日文 → 繁體中文），含模板化數值顯示
- 38 種狀態效果定義
- 互動式編隊器（5 隊編制，主將/副將配置）
- 武將庫（依 Cost / 勢力多選篩選）
- 戰法庫（依類型 / 稀有度篩選）
- 庫存管理（標記已擁有武將/戰法）
- Override 機制（手動新增未上架武將/戰法）
- 帳號系統（Google / GitHub 登入、雲端角色配置同步、命名分享連結）— 詳見下方 [帳號系統 / Supabase](#帳號系統--supabase)

## 快速開始

### 環境需求

- Python 3.10+
- [uv](https://docs.astral.sh/uv/)（Python 套件管理）
- Node.js 20+
- [OpenRouter API Key](https://openrouter.ai/)（LLM 翻譯用）

### 安裝

```bash
npm install
uv sync          # 從 pyproject.toml 安裝 Python 依賴（自動建立 .venv）
```

### 設定

```bash
cp .env.example .env
# 填入 OPENROUTER_API_KEY (爬蟲/翻譯必要)
# 可選：填入 VITE_SUPABASE_URL + VITE_SUPABASE_PUBLISHABLE_KEY 啟用帳號系統
```

### 開發

```bash
npm run dev        # 建構資料 + 啟動開發伺服器
```

### 生產建構

```bash
npm run build      # 建構資料 + Vite 生產建構 → dist/index.html（單檔 SPA）
```

## 資料 Pipeline

### 1. 爬蟲

```bash
uv run script/crawl_heroes.py --detail              # 完整爬取
uv run script/crawl_heroes.py --detail --limit 5     # 測試 5 位
uv run script/crawl_heroes.py --detail --name 信長    # 篩選名稱
```

### 2. LLM 翻譯

透過 OpenRouter 呼叫 Claude Haiku，使用 Anthropic prompt caching 機制，全量翻譯（196 技能 + 133 特性 + 145 武將）費用 < 2 USD。

```bash
uv run script/llm_translate.py --batch-size 10 --parallel 3   # 翻譯全部（技能+特性+武將名）
uv run script/llm_translate.py --skills --force               # 強制重翻技能
uv run script/llm_translate.py --heroes                       # 僅翻譯武將名稱
```

### 3. 手動 Override

```bash
uv run script/override.py                            # 互動式選單
uv run script/override.py --quick-add                # 自然語言快速新增戰法
uv run script/override.py --add-hero                 # 新增武將
uv run script/override.py --modify-skill             # 修改既有戰法
```

### 4. 建構前端資料

```bash
npm run data       # build_frontend_data.py + check_data_integrity.py
```

## 帳號系統 / Supabase

帳號系統為**選用**功能 — 未設定 Supabase 環境變數時，所有編隊與庫存功能仍可在本機完整使用，僅雲端同步與命名分享連結會無聲關閉（透過 `isSupabaseConfigured()` 特徵檢測，不會拋錯）。

### 功能對照

| 功能 | 匿名 | 登入 |
|---|:---:|:---:|
| 編隊編輯 / 庫存標記 | ✓ | ✓ |
| 載入他人分享連結 | ✓ | ✓ |
| 建立分享連結（長 base64 hash） | ✓ | ✓ |
| 建立**短連結** (`#s/<slug>`) | ✓ | ✓ |
| 為分享命名 / 在「我的分享」管理 | ✗ | ✓ |
| 雲端**角色配置**（武將/戰法庫存）同步 | ✗ | ✓ |
| 多套配置切換、預設配置自動載入 | ✗ | ✓ |

### 登入流程

- **Provider**：Google、GitHub OAuth（implicit flow，全頁重導向 → Supabase GoTrue → 帶 `access_token` / `refresh_token` 回 SPA hash）
- **Session 持久化**：`localStorage.nobunaga.auth.session`（含 access/refresh token、過期時間、user id/email/display_name）
- **Token 續期**：距過期 < 60s 時自動續期，並行請求共享單一續期 promise（`inflightRefresh` 鎖）避免 race
- **失效處理**：401/403 視為**不可恢復**（清 session、廣播 `expired` 事件、彈出「登入已過期」提示）；5xx/網路錯誤視為**暫時性**，保留舊 token 重試
- **登入前快照**：點擊「登入」時把當前隊伍 + 庫存寫入 `nobunaga.auth.recovery`（5 分鐘 TTL），登入回呼後自動還原 — 避免 OAuth 重導向丟失正在編輯的內容
- **首次登入**：`display_name` 為空時自動彈出設定對話框（之後可從使用者下拉選單編輯）

### 資料庫結構（PostgREST + RLS）

無 Edge Function、無自訂 RPC — 全部透過 PostgREST 直連 + Row-Level Security 實現存取控制。

#### `character_profiles`（角色配置）

| 欄位 | 型別 | 說明 |
|---|---|---|
| `id` | uuid (PK) | |
| `user_id` | uuid → `auth.users.id` | RLS 限定僅擁有者讀寫 |
| `name` | text | 配置名稱（CHT，使用者命名） |
| `inv_h` | text[] | 已擁有武將（**JP 名稱**為 key — 對翻譯版本變更有韌性；override-added 武將以 CHT 名稱 fallback） |
| `inv_s` | text[] | 已擁有戰法（同上規則） |
| `is_default` | boolean | 登入時自動套用 |
| `created_at` / `updated_at` | timestamptz | |

#### `shares`（分享）

| 欄位 | 型別 | 說明 |
|---|---|---|
| `slug` | text (PK) | 12-14 字 base62 短碼 |
| `blob` | jsonb | v2 分享 payload（隊伍 + 庫存，全部以 JP 名稱 key） |
| `user_id` | uuid (nullable) | 匿名分享為 NULL；登入分享受 RLS 保護 |
| `display_name` | text (nullable) | 僅登入分享有效 |
| `pinned` | boolean | 釘選到「我的分享」頂端 |
| `created_at` / `updated_at` | timestamptz | |

**RLS 模式**：`shares` 為「公開讀、私有寫」— 任何人可讀取 slug 並建立新分享，但僅 `user_id = auth.uid()` 可 PATCH/DELETE。`character_profiles` 為「擁有者全權」— 列級 `user_id` 過濾。

### 環境變數

| 變數 | 用途 | 必要性 |
|---|---|---|
| `VITE_SUPABASE_URL` | Supabase 專案 URL（PostgREST + GoTrue 基底） | 啟用帳號系統時必填 |
| `VITE_SUPABASE_PUBLISHABLE_KEY` | 公開 anon key（瀏覽器安全，受 RLS 保護） | 啟用帳號系統時必填 |

兩者缺一即關閉帳號相關功能。

### 設計細節

- **無 SDK**：直接 `fetch` + 手動 JWT 處理，不引入 `@supabase/supabase-js`，減少 bundle 體積（單檔 SPA 對 size 敏感）
- **優雅降級**：短連結建立失敗時自動 fallback 為長 base64 hash URL（`#<base64>`），使用者無感
- **JP 名稱為 stable key**：`inv_h` / `inv_s` / 分享 blob 中所有武將/戰法都以**日文原名**為 key — 翻譯名稱變動或 LLM 重翻不影響既有資料對應
- **Override-added 例外**：S2/S3 等領先日服上線的內容由 `data/overrides.yaml` 補入，無 JP 名稱（戰法 pipeline 寫 `name_jp = null`，武將則直接省略此欄位），對應 key 自動 fallback 為 CHT 名稱（見 `useActiveProfile.ts` 的 finder 設計）
- **Session 生命週期事件總線**：`onSessionEvent()` 廣播 `persisted` / `expired` / `signed-out`，多個訂閱者（dialog 自動關閉、清空 active profile、提示訊息）統一響應，避免分散的 watch 邏輯

## 專案結構

```
script/
  crawl_heroes.py          # 網頁爬蟲（game8.jp）
  llm_translate.py         # OpenRouter 批次翻譯（預設 Claude Haiku）
  llm_core.py              # LLM 共用基礎設施（httpx API client、prompt caching、解析）
  build_frontend_data.py   # YAML → JSON 建構 + 後處理
  check_data_integrity.py  # 資料完整性驗證
  override.py              # 互動式 Override CLI

data/
  overrides.yaml           # 手動覆蓋資料（git 追蹤）
  statuses.yaml            # 狀態效果定義（git 追蹤）
  *_crawled.yaml           # 爬蟲輸出（gitignored）
  *_translated.yaml        # LLM 翻譯輸出（gitignored）

src/
  components/              # Vue 元件
  composables/             # Vue 組合式函數
  lib/                     # Supabase 客戶端（auth.ts, profiles.ts, share.ts, supabase.ts）
  main.ts                  # 應用程式入口

.build/                    # 前端 JSON（gitignored）
dist/                      # Vite 產出（gitignored）
```

## 技術棧

- **前端**: Vue 3 + Element Plus + TailwindCSS + Vite
- **後端 Pipeline**: Python + PyYAML + BeautifulSoup4
- **LLM**: OpenRouter API（預設 Claude Haiku 4.5，支援 prompt caching）
- **帳號 / 雲端同步**: Supabase（GoTrue + PostgREST + RLS，無 SDK，直連 fetch）
- **部署**: 單檔 SPA（`vite-plugin-singlefile`）

## Acknowledgements

- [Claude Code](https://claude.ai/claude-code) — 架構設計、Pipeline 開發、前端實作
- [OpenRouter](https://openrouter.ai/) + [Claude Haiku](https://www.anthropic.com/) — 日文→繁中批次翻譯、戰法結構化提取

## Disclaimer

This project is a fan-made tool for **信長之野望：真戰** (Nobunaga's Ambition: Shinsei). Game data, images, and trademarks belong to their respective owners (KOEI TECMO Games Co., Ltd.). This project is not affiliated with or endorsed by KOEI TECMO.

若本專案之內容侵犯了您的權益，請透過 yt.neko.vision@gmail.com 或 Discord（neko.vision）聯繫作者，將盡速配合處理（包括但不限於移除相關內容或下架本專案）。

## License

[MIT License](LICENSE)
