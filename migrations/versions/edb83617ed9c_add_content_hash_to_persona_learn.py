"""add_content_hash_to_persona_learn

Revision ID: edb83617ed9c
Revises: 4c5d6e7f8a9b
Create Date: 2026-07-19 21:57:19.582989

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'edb83617ed9c'
down_revision: Union[str, None] = '4c5d6e7f8a9b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('persona_learn', sa.Column('content_hash', sa.Text(), nullable=True))
    op.create_index(
        'idx_persona_learn_hash',
        'persona_learn',
        ['persona_id', 'user_id', 'content_hash']
    )


def downgrade() -> None:
    op.drop_index('idx_persona_learn_hash', table_name='persona_learn')
    op.drop_column('persona_learn', 'content_hash')
