# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 作成日：2026年5月14日（v8からの更新版）

## Project Overview

**AI-PERSONA会議室** (AI-Persona Meeting Room) — A web app where users create AI personas that conduct real-time AI-powered discussions about user-specified topics, powered by Claude.

**現在バージョン**: v0.9.9（コピー・オン・エディット実装済み）
**最新コミット**: f4d0855

## 完成済み機能

| 機能 | 状態 |
|------|------|
| Stripe課金実装 | ✅（v0.9.5） |
| テスト強化・法律対応T-01〜T-04・iPhone修正 | ✅（v0.9.6） |
| T-05：禁止事項・情報公開禁止モーダル | ✅（2026/05/13） |
| T-06：故人ペルソナ同意確認モーダル | ✅（2026/05/13） |
| コピー・オン・エディット機能 | ✅（2026/05/14実装・本番確認済み） |
| source_persona_id / extra_settings カラム追加 | ✅（2026/05/14） |
| PUT /api/personas/:id に @login_required追加 | ✅（2026/05/14） |

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

### ANTHROPIC_API_KEY 運用管理ルール（BUG-06対応）
- APIキーはAnthropicコンソール（console.anthropic.com）で発行・ローテーション
- 設定場所：Railway → プロジェクト → Variables タブ → `ANTHROPIC_API_KEY`
- ローカル開発：`.env` ファイルに設定（Git管理外・`.gitignore`に記載済み）
- **キーを再発行した際は Railway Variables を必ず同時に更新すること**
- 有効期限切れ・クォータ超過時は `500 Internal Server Error` でAI応答が止まる
  → Railwayのログで `AuthenticationError` または `RateLimitError` を確認してキーを更新する

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
  ※ source_persona_id: コピー元デフォルトペルソナのID（コピー・オン・エディット用）
  ※ extra_settings: JSONB拡張カラム（将来の設定項目追加用）
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

## 開発方針

### チャット（claude.ai）とCodeの役割分担（確定版）

| 作業 | 担当 | 方法 |
|---|---|---|
| コード修正・git操作 | Claude Code | 従来通り |
| バグ原因の特定・解析 | このチャット | ソースファイルをアップロードして解析 |
| 本番環境の動作確認 | このチャット | スクリーンショットを貼って確認 |
| RailwayのQueryタブSQL | 智信さん＋チャット | SQLをチャットで案内→実行→結果を貼る |
| Codeへの指示作成 | このチャット | 原因・修正箇所・検証方法を全て明記した仕様書として渡す |
| 外部サービス設定変更 | 智信さん自身 | APIキー再発行・Railway環境変数等 |

### バグ発生時のフロー（必ず守ること）

1. 本番でバグ発生 → スクリーンショット＋コンソールエラーをチャットに貼る
2. チャットがソースファイル（app.js・index.html等）のアップロードを要求する
3. チャットがコードを直接解析し「どのファイルの何行目に何の問題があるか」まで特定する
4. チャットがCodeへの指示を「修正ファイル・修正行・修正内容・検証方法」を全て明記した仕様書として作成する
5. Codeは指示通りに実装し、完了条件チェックリストを全項目報告する
6. チャットでスクリーンショットを受け取り合否判定する
7. NGなら再度コード解析してCodeに差し戻す

### Codeへの指示で「調査してください」は禁止
- NG：「調査して修正してください」
- OK：「○○ファイルの○○行目の○○を○○に変更する」

### バックアップ体制
- ai-meeting-roomフォルダはGoogle Drive（G:）に自動同期済み
- 同期先：taketomo6630@gmail.com のマイコンピュータ

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

## 2026/05/13 実施済み作業

### 法律対応改修（5/15相談前対応）
- terms.html / privacy.html：日付5/14→5/15修正・デプロイ済み
- T-05：禁止事項・情報公開禁止モーダル実装済み（localStorage: prohibited_notice_agreed）
- T-06：故人ペルソナ同意確認モーダル実装済み（is_deceased_confirmed カラム使用）

### バグ修正
- CSS: .form-group input の width:100% がcheckboxに適用されるバグ修正
  → :not([type=checkbox]) を追加
- JS: submitAddPersonaからdoCreatePersona呼び出し前のaddSubmittingリセット漏れ修正
- API: /api/personas/add に @login_required 追加

### フロントエンドデバッグの教訓
- ClaudeCodeはブラウザ描画を確認できないため、フロントエンドのバグ調査は
  このチャットにファイルをアップロードして直接解析する
- Claude in Chrome (Beta) のClaudeCode連携は未確立（引き続き設定要）

## 2026/05/14 実施済み作業

### コピー・オン・エディット機能実装
- デフォルトペルソナの編集時に自動でユーザー専用コピーを作成する機能
- DBカラム追加：source_persona_id（コピー元ID）、extra_settings（JSONB拡張）
- copyPersonaモーダルHTMLをscriptタグ前に移動（DOM null参照バグ修正）
- PUT /api/personas/:id に @login_required 追加

### .gitignore修正
- env（ドットなし）を追加（GitHub Secret Scanning対策）

## ⚠️ 教訓

| 日付 | 教訓 | 対策 |
|---|---|---|
| 2026/05/13 | ClaudeCodeはブラウザ描画を確認できない | フロントエンドのバグ調査はチャットにファイルをアップロードして直接解析する |
| 2026/05/14 | HTMLモーダルをscriptタグより後に配置するとDOM初期化時にnullになる | 新規モーダルHTMLは必ず`<script src="app.js">`より前に配置すること |
| 2026/05/14 | .envファイルをgitにコミットするとGitHubのSecret Scanningでブロックされる | .gitignoreに`.env`と`env`（ドットなし）の両方を記載すること |

## 品質改善履歴

| 日付 | 修正内容 | 重要度 |
|---|---|---|
| 2026/05/13 | T-05：禁止事項・情報公開禁止モーダル実装 | ★★★ |
| 2026/05/13 | T-06：故人ペルソナ同意確認モーダル実装 | ★★★ |
| 2026/05/13 | CSS checkbox幅バグ修正（:not([type=checkbox])追加） | ★★ |
| 2026/05/13 | submitAddPersonaのaddSubmittingリセット漏れ修正 | ★★ |
| 2026/05/13 | /api/personas/add に @login_required 追加 | ★★★ |
| 2026/05/14 | コピー・オン・エディット機能実装（デフォルトペルソナをユーザー専用コピーとして複製） | ★★★ |
| 2026/05/14 | source_persona_id / extra_settings カラムをpersonasテーブルに追加 | ★★★ |
| 2026/05/14 | copyPersonaモーダルHTMLをscriptタグ前に移動（DOM null参照バグ修正） | ★★★ |
| 2026/05/14 | .gitignoreにenv（ドットなし）を追加（Secret Scanning対策） | ★★★ |
| 2026/05/14 | チャット/Codeの役割分担・バグ対応フローをCLAUDE.mdに明記 | ★★★ |
| 2026/05/14 | ai-meeting-roomをGoogle Driveに自動同期設定（バックアップ体制確立） | ★★ |

## 次回チャット開始時の注意

- **最優先バグ**: 音声途切れ修正（全員で議論モードで必ず発生）
- **フェーズ2**: デフォルトペルソナ30体追加（カテゴリ構成は智信さんが検討中）
- **次の開発課題**: T-07実装・Docker環境整備・Alembic導入（βテスト前必須）
- **5/15**: 弁護士相談（terms.html・privacy.htmlドラフト持参）→ 相談後に正式版デプロイ

## Roadmap
1. ✅ Stripe課金実装（v0.9.5）
2. ✅ テスト強化・法律対応T-01〜T-04・iPhone修正（v0.9.6）
3. ✅ 法律対応T-05・T-06・コピー・オン・エディット実装（v0.9.9）
4. 利用規約・プライバシーポリシー正式版更新（5/15弁護士相談後）
5. 音声途切れ修正（全員で議論モード）
6. iPhone Safari音声再生問題修正
7. PC版UI残課題（ログイン前ボタン等）
8. 法律対応T-07
9. デフォルトペルソナ30体追加
10. Docker環境整備・Alembic導入
11. Stripe本番環境への切り替え（KYB・銀行口座登録）
12. βテスト（5〜10名）
13. v1.0正式リリース
