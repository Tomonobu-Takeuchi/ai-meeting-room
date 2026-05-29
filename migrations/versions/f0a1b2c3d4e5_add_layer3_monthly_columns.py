"""add_layer3_monthly_columns

Revision ID: f0a1b2c3d4e5
Revises: e1f2a3b4c5d6
Create Date: 2026-05-30 00:00:00

"""
from typing import Sequence, Union
from alembic import op

revision: str = 'f0a1b2c3d4e5'
down_revision: Union[str, None] = 'e1f2a3b4c5d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS layer3_monthly_count INTEGER DEFAULT 0,
        ADD COLUMN IF NOT EXISTS layer3_monthly_reset_at TIMESTAMP DEFAULT NOW()
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE users
        DROP COLUMN IF EXISTS layer3_monthly_count,
        DROP COLUMN IF EXISTS layer3_monthly_reset_at
    """)
