# AI-PERSONA会議室

AI（人工知能）ペルソナが会議を開催し、ユーザー指定のテーマについてリアルタイムで議論するWebアプリケーション。

---

## v1.0.0 リリース（2026年5月）

### 主要機能一覧

| カテゴリ | 機能 |
|----------|------|
| **ペルソナ管理** | ペルソナ作成・編集・削除、役割設定（ファシリテーター/メンバー）、システムデフォルトペルソナ |
| **成熟度システム** | 10段階成熟度（初回〜達人）、会議参加によるスコア蓄積、バッジ表示 |
| **RAG学習機能** | PDFアップロード、URLスクレイピング、YouTube文字起こし、音声/動画ファイル（Whisper） |
| **会議機能** | リアルタイムストリーミング（SSE）、ファシリテーター進行、自動ラウンド、議事録PDF出力 |
| **音声モード** | OpenAI TTS読み上げ、Whisper音声入力 |
| **課金システム** | 無料プラン（月5回）、スタンダード（¥480/50チケット）、プロ（¥980/月・無制限） |
| **UI/UX** | ダークモード、使い方ガイド（8章構成）、レスポンシブ対応 |
| **規約整備** | 利用規約・プライバシーポリシー |

---

## 技術スタック

- **Backend:** Python 3.12 + Flask
- **Frontend:** Vanilla JS + HTML5（ビルドステップなし）
- **Database:** PostgreSQL + pgvector（RAG埋め込み）
- **AI:** Claude API（会議生成・議事録）、OpenAI Whisper（音声認識）、OpenAI TTS（読み上げ）
- **Payments:** Stripe
- **Deployment:** Railway

## セットアップ

```bash
pip install -r requirements.txt
python src/main.py  # http://localhost:8765
```

必要な環境変数は `CLAUDE.md` を参照。
