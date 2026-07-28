"""add_beta_survey_shown_columns

Revision ID: b7d4e8f2a1c9
Revises: a3f8c2e91d4b
Create Date: 2026-07-29 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7d4e8f2a1c9'
down_revision: Union[str, None] = 'a3f8c2e91d4b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 会議終了時アンケートの表示済み日時。NULLなら未表示。
    # survey1=初回会議終了時アンケート、survey2=継続議論終了時アンケート
    op.add_column('users', sa.Column('beta_survey1_shown_at', sa.TIMESTAMP(), nullable=True))
    op.add_column('users', sa.Column('beta_survey2_shown_at', sa.TIMESTAMP(), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'beta_survey2_shown_at')
    op.drop_column('users', 'beta_survey1_shown_at')
