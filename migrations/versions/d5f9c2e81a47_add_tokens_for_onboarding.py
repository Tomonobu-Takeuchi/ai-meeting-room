"""add_tokens_for_onboarding

Revision ID: d5f9c2e81a47
Revises: c9e1a4b7f306
Create Date: 2026-07-30 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd5f9c2e81a47'
down_revision: Union[str, None] = 'c9e1a4b7f306'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 改修⑰: ベータ申請ごとの本人確認トークン。
    # 案内メールのリンクに埋め込み、リンクを踏めた＝そのアドレスを
    # 受信できる、という事実をもってメール到達性の確認に代える。
    op.add_column('beta_applications',
                  sa.Column('access_token', sa.Text(), nullable=True))
    op.create_index('idx_beta_applications_access_token',
                    'beta_applications', ['access_token'], unique=True)

    # 改修⑯: パスワード再設定用トークン。email_change_token と同じ方式。
    op.add_column('users',
                  sa.Column('password_reset_token', sa.Text(), nullable=True))
    op.add_column('users',
                  sa.Column('password_reset_expires', sa.TIMESTAMP(), nullable=True))
    op.create_index('idx_users_password_reset_token',
                    'users', ['password_reset_token'])


def downgrade() -> None:
    op.drop_index('idx_users_password_reset_token', table_name='users')
    op.drop_column('users', 'password_reset_expires')
    op.drop_column('users', 'password_reset_token')
    op.drop_index('idx_beta_applications_access_token', table_name='beta_applications')
    op.drop_column('beta_applications', 'access_token')
