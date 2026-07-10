"""add_scheduler_tables

Revision ID: 3a4b5c6d7e8f
Revises: a1b2c3d4e5f6
Create Date: 2026-07-10 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '3a4b5c6d7e8f'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS pending_deletion_at TIMESTAMP NULL
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS access_logs (
            id           SERIAL PRIMARY KEY,
            user_id      INTEGER NULL,
            ip_address   TEXT,
            user_agent   TEXT,
            method       TEXT,
            path         TEXT,
            status_code  INTEGER,
            created_at   TIMESTAMP DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_access_logs_created_at
        ON access_logs (created_at)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS access_logs")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS pending_deletion_at")
