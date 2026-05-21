"""add_columns_phase3

Revision ID: 47f2188a8c65
Revises: 8ccadcd79a68
Create Date: 2026-05-21 19:57:15.443930

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '47f2188a8c65'
down_revision: Union[str, None] = '8ccadcd79a68'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- users テーブル ---
    op.execute("""
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS extra_settings JSONB DEFAULT '{}'::jsonb,
        ADD COLUMN IF NOT EXISTS tos_version TEXT DEFAULT ''
    """)

    # --- personas テーブル ---
    op.execute("""
        ALTER TABLE personas
        ADD COLUMN IF NOT EXISTS app_type TEXT DEFAULT 'meeting_room',
        ADD COLUMN IF NOT EXISTS extra_settings JSONB DEFAULT '{}'::jsonb
    """)

    # --- persona_learn テーブル ---
    op.execute("""
        ALTER TABLE persona_learn
        ADD COLUMN IF NOT EXISTS source_model TEXT DEFAULT 'text-embedding-3-small',
        ADD COLUMN IF NOT EXISTS source_type TEXT DEFAULT ''
    """)

    # --- persona_growth テーブル（本番に手動追加済み・ローカルDBに未反映） ---
    op.execute("""
        ALTER TABLE persona_growth
        ADD COLUMN IF NOT EXISTS doc_token_count INTEGER DEFAULT 0,
        ADD COLUMN IF NOT EXISTS unique_topic_count INTEGER DEFAULT 0,
        ADD COLUMN IF NOT EXISTS feedback_count INTEGER DEFAULT 0,
        ADD COLUMN IF NOT EXISTS positive_count INTEGER DEFAULT 0,
        ADD COLUMN IF NOT EXISTS recent_positive_rate DOUBLE PRECISION DEFAULT 0,
        ADD COLUMN IF NOT EXISTS avg_session_length DOUBLE PRECISION DEFAULT 0
    """)


def downgrade() -> None:
    # --- persona_growth ---
    op.execute("""
        ALTER TABLE persona_growth
        DROP COLUMN IF EXISTS doc_token_count,
        DROP COLUMN IF EXISTS unique_topic_count,
        DROP COLUMN IF EXISTS feedback_count,
        DROP COLUMN IF EXISTS positive_count,
        DROP COLUMN IF EXISTS recent_positive_rate,
        DROP COLUMN IF EXISTS avg_session_length
    """)

    # --- persona_learn ---
    op.execute("""
        ALTER TABLE persona_learn
        DROP COLUMN IF EXISTS source_model,
        DROP COLUMN IF EXISTS source_type
    """)

    # --- personas ---
    op.execute("""
        ALTER TABLE personas
        DROP COLUMN IF EXISTS app_type,
        DROP COLUMN IF EXISTS extra_settings
    """)

    # --- users ---
    op.execute("""
        ALTER TABLE users
        DROP COLUMN IF EXISTS extra_settings,
        DROP COLUMN IF EXISTS tos_version
    """)
