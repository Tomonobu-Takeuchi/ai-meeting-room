"""add_beta_applications

Revision ID: a3f8c2e91d4b
Revises: 3e162323a16a
Create Date: 2026-07-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3f8c2e91d4b'
down_revision: Union[str, None] = '3e162323a16a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # is_beta_comp: ベータ協力・無償提供アカウントを示すフラグ。
    # 立っているアカウントは、退会時のStripe API呼び出しをスキップする
    # （テストモード時代のstripe_customer_idが本番Live環境で無効なため）。
    op.add_column('users', sa.Column('is_beta_comp', sa.Boolean(), nullable=False, server_default=sa.false()))

    op.create_table(
        'beta_applications',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('email', sa.Text(), nullable=False),
        sa.Column('applied_at', sa.TIMESTAMP(), server_default=sa.func.now(), nullable=False),
        sa.Column('status', sa.Text(), nullable=False, server_default='pending'),
        sa.Column('premium_expires_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('approved_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('granted_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
    )
    op.create_index('idx_beta_applications_email', 'beta_applications', ['email'])


def downgrade() -> None:
    op.drop_index('idx_beta_applications_email', table_name='beta_applications')
    op.drop_table('beta_applications')
    op.drop_column('users', 'is_beta_comp')
