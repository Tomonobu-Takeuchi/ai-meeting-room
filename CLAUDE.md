# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**AI-PERSONA会議室** (AI-Persona Meeting Room) — A web app where users create AI personas that conduct real-time AI-powered discussions about user-specified topics, powered by Claude.

**Current Version: v0.9.6**

## Development Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run development server (http://localhost:8765)
python src/main.py

# Run production server
gunicorn src.main:app --bind 0.0.0.0:$PORT --timeout 300 --workers 1
```

## Required Environment Variables

```
ANTHROPIC_API_KEY          # Claude API (conversation generation, minutes)
OPENAI_API_KEY             # Whisper transcription (audio/video learning data)
DATABASE_URL               # PostgreSQL connection string (with pgvector extension)
SECRET_KEY                 # Flask session secret
PORT                       # Default 8765 (dev) or set by Railway/Heroku
STRIPE_SECRET_KEY          # Stripe secret key (server-side)
STRIPE_PUBLIC_KEY          # Stripe publishable key (client-side)
STRIPE_WEBHOOK_SECRET      # Stripe webhook signing secret
STRIPE_PRICE_STANDARD      # Price ID for standard plan (¥480/50チケット)
STRIPE_PRICE_PRO           # Price ID for pro plan (¥980/月)
```

## Architecture

### Stack
- **Backend:** Python 3.12 + Flask, pg8000 (PostgreSQL), bcrypt sessions
- **Frontend:** Vanilla JS + HTML5, no build step, SSE for real-time streaming
- **Database:** PostgreSQL with pgvector extension (vector embeddings for RAG)
- **Deployment:** Railway via nixpacks (requires FFmpeg, libpq-dev)
- **Payments:** Stripe (sandbox tested; webhook name: adventurous-jubilee)

### Key Files
| File | Purpose |
|------|---------|
| `src/main.py` | Flask app + all API routes (~766 lines) |
| `src/database.py` | PostgreSQL CRUD, connection management (~647 lines) |
| `src/persona/persona_manager.py` | Persona CRUD, AI prompts, growth tracking (~488 lines) |
| `src/meeting/meeting_room.py` | Session state, streaming generation (~187 lines) |
| `web/index.html` | Single-page UI (dark mode, purple/blue theme) |
| `web/app.js` | Frontend logic, SSE consumption, auth UI (~1493 lines) |

### Data Flow
1. User creates personas with personalities, backgrounds, and learning data
2. User starts a meeting with a topic + selected personas
3. Backend creates an in-memory session (`MeetingRoom.sessions` dict)
4. Frontend uses SSE to stream responses from `/api/stream/member|facilitator|auto/<session_id>`
5. Meeting persists to JSON in `data/meetings/`; logs written to DB on PDF export

### Streaming API Response Format (SSE)
```
data: {"type": "chunk", "text": "...", "persona_id": "..."}
data: {"type": "done", "message": {...}}
data: {"type": "error", "message": "..."}
```

### Database Tables
- `users` — auth (email, bcrypt password hash, `plan` VARCHAR(20), `credits` INTEGER DEFAULT 0, `plan_expires_at` TIMESTAMP, `monthly_meeting_count` INTEGER, `monthly_reset_at` TIMESTAMP, `stripe_customer_id` VARCHAR)
- `payments` — Stripe payment records; `stripe_session_id` is unique (prevents double-grant)
- `personas` — persona definitions; `user_id=NULL` for system defaults, `role=facilitator|member`
- `persona_learn` — knowledge base with `vector(1536)` embeddings for semantic search
- `persona_patterns` — extracted conversation patterns
- `persona_growth` — maturity levels (0=初回, 1=見習い, 2=熟練, 3=達人) + scores
- `persona_meeting_stats` — meeting participation counts
- `feedback` — user ratings per persona response

### Billing Plans
| Plan | Price | Limit |
|------|-------|-------|
| 無料 | ¥0 | 月5回まで |
| スタンダード | ¥480 | 50チケット（都度購入） |
| プロ | ¥980/月 | 無制限 |

### Important Implementation Details
- **Single worker:** `gunicorn --workers 1` because active sessions are stored in-memory
- **Japanese support:** `app.json.ensure_ascii = False`; PDF uses HeiseiKakuGo-W5 font
- **Session state:** Flask session stores `user_id`/`user_email`; meeting state in `MeetingRoom.sessions`
- **Context window:** Last 10 messages passed as history in each Claude API call
- **Learning data inputs:** manual text, URL scraping, YouTube transcripts, Whisper (audio/video via FFmpeg + yt-dlp)
- **DB plan column:** `plan` (NOT `plan_type`) in the `users` table
- **Stripe SDK 7.x:** StripeObject fields must use dot notation or `getattr()` — `.get()` is not available
- **Double-grant prevention:** `payments` table checks `stripe_session_id` uniqueness before granting credits

## テストデータ管理ルール（本番DB汚染防止）

- テスト用ペルソナは必ず `user_id` を持つ専用テストユーザーで作成する
- `user_id=NULL`（デフォルトペルソナ枠）はテストに**使用禁止**
- テスト実施前に、テストデータ削除用SQLをセットで用意してから開始する
- テスト完了後は必ず削除SQLを実行し、本番DBにテストデータが残っていないことを確認する
- 確認クエリ（正規5件のみであること）：

```sql
SELECT id, name, user_id FROM personas WHERE user_id IS NULL ORDER BY id;
-- 期待値: elizabeth1 / facilitator / hideyoshi / koumei / professor の5件のみ
```

## テスト実行ルール（必ず守ること）

### テスト実行コマンド（本番DB混入防止）
```powershell
# 手順1: .envのDATABASE_URL行頭に # を付けて一時コメントアウト
# 手順2: テスト実行
python -X utf8 test_comprehensive.py 2>&1 | Out-File -Encoding utf8 "C:\Temp\test_result.txt"
Get-Content "C:\Temp\test_result.txt" | Select-Object -Last 15
# 手順3: テスト成否に関わらず .env の # を外してDATABASE_URLを復元（必須）
```

### テスト後の本番DB確認（必須）
以下をRailwayのQueryタブで実行し 0 rows であることを確認：
```sql
SELECT id, name FROM personas
WHERE user_id IS NULL
AND id NOT IN ('koumei','hideyoshi','professor','elizabeth1','facilitator');
```

### Codeへのプロンプトテンプレート（必ず使うこと）
```
【実装内容】
...
【デグレード確認】
① .envのDATABASE_URLを一時コメントアウト
   .envを開き DATABASE_URL=... の行頭に # を追加して保存

② テスト実行
   python -X utf8 test_comprehensive.py 2>&1 | Out-File -Encoding utf8 "C:\Temp\test_result.txt"
   Get-Content "C:\Temp\test_result.txt" | Select-Object -Last 15
   → 183件以上PASS確認

③ .envを必ず元に戻す（テスト成否に関わらず必須）
   # を外してDATABASE_URLを復元して保存

④ 復元確認
   .envを開いてDATABASE_URLが復元されていることを確認してから報告

【デグレード確認】
【本番環境確認】
【完了条件】
の3セクションは省略禁止。
⚠️ 【実装内容】が「なし」の場合も4セクション全て省略禁止

【デグレード確認】
上記①〜④を実施し完了を報告する

【本番環境確認】
本番URLでの動作確認（具体的な確認項目を列挙）
RailwayのQueryタブで以下を実行し0 rows確認：
SELECT id, name FROM personas WHERE user_id IS NULL
AND id NOT IN ('koumei','hideyoshi','professor','elizabeth1','facilitator');

【完了条件】
上記3つ全て確認後のみgit push
```

## Utility Scripts (Untracked)
- `check_db.py` — Database inspection
- `add_growth_tables.py` — Migration for growth feature tables

## Roadmap
1. ✅ Stripe課金実装（v0.9.5）
2. ✅ テスト強化・法律対応T-01〜T-04・iPhone修正（v0.9.6）
3. 利用規約・プライバシーポリシー正式版更新（5/14弁護士相談前）
4. iPhone Safari音声再生問題修正
5. PC版UI残課題（ログイン前ボタン等）
6. 法律対応T-05〜T-07
7. Stripe本番環境への切り替え（KYB・銀行口座登録）
8. βテスト（5〜10名）
9. v1.0正式リリース
