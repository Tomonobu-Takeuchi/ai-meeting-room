"""
add_growth_tables.py
persona_growth / persona_feedback テーブルを Railway PostgreSQL に追加するスクリプト
実行方法：
  cd C:\Claude\AI_Project\ai-meeting-room
  python add_growth_tables.py
"""
import os
import sys
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get('DATABASE_URL', '')
if not DATABASE_URL:
    print("ERROR: DATABASE_URL が設定されていません。.env を確認してください。")
    sys.exit(1)

try:
    import pg8000.native
except ImportError:
    print("ERROR: pg8000 がインストールされていません。")
    print("  pip install pg8000")
    sys.exit(1)

url = urlparse(DATABASE_URL)
conn = pg8000.native.Connection(
    host=url.hostname,
    port=url.port or 5432,
    database=url.path.lstrip('/'),
    user=url.username,
    password=url.password,
    ssl_context=True,
)

print("DB接続成功")

# ===== persona_growth テーブル =====
conn.run("""
    CREATE TABLE IF NOT EXISTS persona_growth (
        id              SERIAL PRIMARY KEY,
        persona_id      TEXT NOT NULL,
        user_id         INTEGER REFERENCES users(id) ON DELETE CASCADE,
        app_type        TEXT DEFAULT 'meeting',

        -- 軸A：知識量スコア（0-100）
        score_knowledge     FLOAT DEFAULT 0,
        doc_token_count     INTEGER DEFAULT 0,
        conversation_count  INTEGER DEFAULT 0,
        unique_topic_count  INTEGER DEFAULT 0,

        -- 軸B：応答精度スコア（0-100）
        score_accuracy      FLOAT DEFAULT 0,
        feedback_count      INTEGER DEFAULT 0,
        positive_count      INTEGER DEFAULT 0,
        recent_positive_rate FLOAT DEFAULT 0,

        -- 軸C：個性スコア（0-100）
        score_personality   FLOAT DEFAULT 0,
        profile_completeness FLOAT DEFAULT 0,
        avg_session_length  FLOAT DEFAULT 0,
        tuning_count        INTEGER DEFAULT 0,

        -- 総合スコア
        maturity_score  FLOAT DEFAULT 0,
        maturity_level  INTEGER DEFAULT 1,

        created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

        UNIQUE (persona_id, user_id, app_type)
    )
""")
print("persona_growth テーブル作成（または確認）完了")

# ===== persona_feedback テーブル =====
conn.run("""
    CREATE TABLE IF NOT EXISTS persona_feedback (
        id              SERIAL PRIMARY KEY,
        persona_id      TEXT NOT NULL,
        user_id         INTEGER REFERENCES users(id) ON DELETE CASCADE,
        session_id      TEXT,

        -- Layer1：はい/いいえ
        rating          BOOLEAN NOT NULL,

        -- Layer2：カテゴリ（いいえのとき）
        detail_category TEXT,

        -- Layer3：自由記述
        correct_response TEXT,

        created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
""")
print("persona_feedback テーブル作成（または確認）完了")

# ===== 接続確認：テーブル一覧 =====
tables = conn.run("""
    SELECT tablename FROM pg_tables
    WHERE schemaname = 'public'
    ORDER BY tablename
""")
print("\n現在のテーブル一覧:")
for t in tables:
    print(f"  {t[0]}")

print("\n完了！Railway に persona_growth / persona_feedback が追加されました。")
