"""add_meeting_transcript_tables

Revision ID: 3e162323a16a
Revises: 67460dcf6ae4
Create Date: 2026-07-21 22:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '3e162323a16a'
down_revision: Union[str, None] = '67460dcf6ae4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'meeting_messages',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('meeting_id', sa.Integer(), sa.ForeignKey('meetings.id', ondelete='CASCADE'), nullable=False),
        sa.Column('message_id', sa.String(length=16), nullable=True),  # session内のmsg["id"]（uuid[:8]）
        sa.Column('role', sa.Text(), nullable=False),                  # 'member' | 'facilitator' | 'user'
        sa.Column('persona_id', sa.Text(), nullable=True),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('sequence', sa.Integer(), nullable=False),           # 会議内の発言順
        sa.Column('message_created_at', sa.TIMESTAMP(), nullable=True), # session内msg["timestamp"]
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('NOW()')),
    )
    op.create_index('idx_meeting_messages_meeting_id', 'meeting_messages', ['meeting_id'])

    op.create_table(
        'meeting_decisions',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('meeting_id', sa.Integer(), sa.ForeignKey('meetings.id', ondelete='CASCADE'), nullable=False),
        sa.Column('item', sa.Text(), nullable=True),
        sa.Column('value', sa.Text(), nullable=True),
        sa.Column('status', sa.Text(), nullable=True),   # 'confirmed' | 'tentative'
        sa.Column('basis', sa.Text(), nullable=True),
        sa.Column('changed_from', sa.Text(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('NOW()')),
    )
    op.create_index('idx_meeting_decisions_meeting_id', 'meeting_decisions', ['meeting_id'])

    op.add_column('meetings', sa.Column('unresolved_issues', postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column('meetings', 'unresolved_issues')
    op.drop_index('idx_meeting_decisions_meeting_id', table_name='meeting_decisions')
    op.drop_table('meeting_decisions')
    op.drop_index('idx_meeting_messages_meeting_id', table_name='meeting_messages')
    op.drop_table('meeting_messages')
