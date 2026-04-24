"""
check_db.py - 既存テーブル構造の確認スクリプト
database.py と同じ接続方式（DATABASE_URL）を使用
"""
import os
import pg8000.native
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get('DATABASE_URL', '')

if not DATABASE_URL:
    print("[ERROR] .envにDATABASE_URLが設定されていません")
    exit(1)

def get_connection():
    url = urlparse(DATABASE_URL)
    return pg8000.native.Connection(
        host=url.hostname,
        port=url.port or 5432,
        database=url.path.lstrip('/'),
        user=url.username,
        password=url.password,
        ssl_context=True,
    )

print("接続中...")
conn = get_connection()
print("[OK] 接続成功!\n")

# テーブル一覧
rows = conn.run("""
    SELECT table_name 
    FROM information_schema.tables 
    WHERE table_schema = 'public'
    ORDER BY table_name
""")

print("=== テーブル一覧 ===")
tables = [row[0] for row in rows]
for t in tables:
    print(f"  {t}")

# 各テーブルのカラム情報
print("\n=== 各テーブルのカラム ===")
for table in tables:
    cols = conn.run("""
        SELECT column_name, data_type, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = :table
        ORDER BY ordinal_position
    """, table=table)
    print(f"\n[{table}]")
    for col in cols:
        nullable = "NULL可" if col[2] == "YES" else "NOT NULL"
        default = f"  default={col[3]}" if col[3] else ""
        print(f"  {str(col[0]):<30} {str(col[1]):<20} {nullable}{default}")

conn.close()
print("\n[OK] 完了")
