"""add_edition_support

Revision ID: 4c5d6e7f8a9b
Revises: 3a4b5c6d7e8f
Create Date: 2026-07-11 00:00:00.000000

海外版（global）・カジュアル版（casual）派生アプリのためのスキーマ追加。
DB共有・アプリのみ複製する方針のため、既存usersテーブルで共通ユーザーIDを
共有しつつ、版ごとの課金状態はedition_subscriptionsテーブルに分離する。
本マイグレーションはスキーマ追加のみで、現行アプリのロジックには一切影響しない。
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '4c5d6e7f8a9b'
down_revision: Union[str, None] = '3a4b5c6d7e8f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # meetings: 版・言語
    op.execute("""
        ALTER TABLE meetings
        ADD COLUMN IF NOT EXISTS edition TEXT DEFAULT 'main'
    """)
    op.execute("""
        ALTER TABLE meetings
        ADD COLUMN IF NOT EXISTS language TEXT DEFAULT 'ja'
    """)
    # personas: 版（既存のapp_typeとは別概念。app_typeは会議室/相談室、editionはmain/global/casual）
    op.execute("""
        ALTER TABLE personas
        ADD COLUMN IF NOT EXISTS edition TEXT DEFAULT 'main'
    """)
    # payments: 版ごとの決済記録の区別用
    op.execute("""
        ALTER TABLE payments
        ADD COLUMN IF NOT EXISTS edition TEXT DEFAULT 'main'
    """)
    # edition_subscriptions: 版ごとの課金・プラン状態（usersのplan等はmain版専用のまま変更しない）
    op.execute("""
        CREATE TABLE IF NOT EXISTS edition_subscriptions (
            id                       SERIAL PRIMARY KEY,
            user_id                  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            edition                  TEXT NOT NULL,
            plan                     TEXT DEFAULT 'free',
            credits                  INTEGER DEFAULT 0,
            plan_expires_at          TIMESTAMP,
            monthly_meeting_count    INTEGER DEFAULT 0,
            monthly_reset_at         TIMESTAMP DEFAULT NOW(),
            stripe_customer_id       TEXT,
            is_earlybird             BOOLEAN DEFAULT FALSE,
            billing_anchor_day       INTEGER,
            trial_layer2_used        BOOLEAN DEFAULT FALSE,
            trial_layer3_used        BOOLEAN DEFAULT FALSE,
            layer3_monthly_count     INTEGER DEFAULT 0,
            layer3_monthly_reset_at  TIMESTAMP DEFAULT NOW(),
            created_at               TIMESTAMP DEFAULT NOW(),
            UNIQUE(user_id, edition)
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS edition_subscriptions")
    op.execute("ALTER TABLE payments DROP COLUMN IF EXISTS edition")
    op.execute("ALTER TABLE personas DROP COLUMN IF EXISTS edition")
    op.execute("ALTER TABLE meetings DROP COLUMN IF EXISTS language")
    op.execute("ALTER TABLE meetings DROP COLUMN IF EXISTS edition")
