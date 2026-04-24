"""
DBマイグレーション: personas テーブルに voice_id カラムを追加
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv()
from src.database import get_connection


def migrate():
    conn = get_connection()
    try:
        conn.run("""
            ALTER TABLE personas
            ADD COLUMN IF NOT EXISTS voice_id TEXT DEFAULT NULL
        """)
        print("OK: personas.voice_id column added")
    except Exception as e:
        print(f"ERROR: {e}")
    finally:
        conn.close()


if __name__ == '__main__':
    migrate()
