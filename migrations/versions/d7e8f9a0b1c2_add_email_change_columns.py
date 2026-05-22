"""add_email_change_columns

Revision ID: d7e8f9a0b1c2
Revises: c1d2e3f4a5b6
Create Date: 2026-05-22 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'd7e8f9a0b1c2'
down_revision: Union[str, None] = 'c1d2e3f4a5b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS email_change_token VARCHAR(255) NULL,
        ADD COLUMN IF NOT EXISTS email_change_new VARCHAR(255) NULL,
        ADD COLUMN IF NOT EXISTS email_change_expires TIMESTAMP NULL
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE users
        DROP COLUMN IF EXISTS email_change_token,
        DROP COLUMN IF EXISTS email_change_new,
        DROP COLUMN IF EXISTS email_change_expires
    """)
