# -*- coding: utf-8 -*-
"""
DBmigration: payments table
Run: python add_payment_tables.py
"""
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv()
from src.database import get_connection


def migrate():
    conn = get_connection()

    alter_sqls = [
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS credits INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS plan_expires_at TIMESTAMP",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS monthly_meeting_count INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS monthly_reset_at TIMESTAMP DEFAULT NOW()",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS stripe_customer_id TEXT",
    ]
    for sql in alter_sqls:
        try:
            conn.run(sql)
            print(f"[OK] {sql[:70]}")
        except Exception as e:
            print(f"[SKIP] {e}")

    conn.run("""
        CREATE TABLE IF NOT EXISTS payments (
            id                  SERIAL PRIMARY KEY,
            user_id             INTEGER REFERENCES users(id) ON DELETE CASCADE,
            stripe_session_id   TEXT UNIQUE,
            stripe_customer_id  TEXT,
            payment_type        TEXT NOT NULL,
            amount_jpy          INTEGER NOT NULL,
            credits_added       INTEGER DEFAULT 0,
            status              TEXT DEFAULT 'pending',
            created_at          TIMESTAMP DEFAULT NOW(),
            completed_at        TIMESTAMP
        )
    """)
    print("[OK] payments table created")

    conn.close()
    print("\n[DONE] Migration complete")


if __name__ == '__main__':
    migrate()
