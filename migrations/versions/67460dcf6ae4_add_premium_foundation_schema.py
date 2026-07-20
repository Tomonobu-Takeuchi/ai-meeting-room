"""add_premium_foundation_schema

Revision ID: 67460dcf6ae4
Revises: edb83617ed9c
Create Date: 2026-07-21 07:48:24.170351

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '67460dcf6ae4'
down_revision: Union[str, None] = 'edb83617ed9c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # meetingsテーブルへの列追加
    op.add_column('meetings', sa.Column('category', sa.Text(), nullable=True))
    op.add_column('meetings', sa.Column('parent_meeting_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'fk_meetings_parent_meeting_id',
        'meetings', 'meetings',
        ['parent_meeting_id'], ['id'],
        ondelete='SET NULL'
    )

    # layer3_reportsテーブル新設
    op.create_table(
        'layer3_reports',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('meeting_id', sa.Integer(), sa.ForeignKey('meetings.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=True),
        sa.Column('category', sa.Text(), nullable=False),
        sa.Column('report_json', postgresql.JSONB(), nullable=False),
        sa.Column('checklist_items', postgresql.JSONB(), nullable=True),
        sa.Column('checked_flags', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('NOW()')),
    )
    op.create_index('idx_layer3_reports_meeting_id', 'layer3_reports', ['meeting_id'])
    op.create_index('idx_layer3_reports_user_id', 'layer3_reports', ['user_id'])


def downgrade() -> None:
    op.drop_index('idx_layer3_reports_user_id', table_name='layer3_reports')
    op.drop_index('idx_layer3_reports_meeting_id', table_name='layer3_reports')
    op.drop_table('layer3_reports')
    op.drop_constraint('fk_meetings_parent_meeting_id', 'meetings', type_='foreignkey')
    op.drop_column('meetings', 'parent_meeting_id')
    op.drop_column('meetings', 'category')
