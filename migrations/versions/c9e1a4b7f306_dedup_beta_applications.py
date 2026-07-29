"""dedup_beta_applications

Revision ID: c9e1a4b7f306
Revises: b7d4e8f2a1c9
Create Date: 2026-07-29 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c9e1a4b7f306'
down_revision: Union[str, None] = 'b7d4e8f2a1c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 既存行を全削除する（竹内さん決定・2026/7/29）。
    # 本番DBの beta_applications 20行はすべて promotest@ / promotest2@ /
    # promotest3@ のテストデータであり、status も全件 pending であることを
    # 実データで確認済み（granted・approved は0件）。
    # 本物の申請者は1件も含まれていないため、重複統合ではなく全削除とし、
    # 空の状態で8/1のベータ1一般開放を迎える。
    # これにより「申請1件目＝最初の実利用者」となり、100名カウントが正確になる。
    op.execute("DELETE FROM beta_applications")

    # UNIQUE制約を追加。以後、同一メールアドレスの行は1件しか存在しない。
    op.drop_index('idx_beta_applications_email', table_name='beta_applications')
    op.create_unique_constraint(
        'uq_beta_applications_email', 'beta_applications', ['email']
    )


def downgrade() -> None:
    op.drop_constraint('uq_beta_applications_email', 'beta_applications', type_='unique')
    op.create_index('idx_beta_applications_email', 'beta_applications', ['email'])
