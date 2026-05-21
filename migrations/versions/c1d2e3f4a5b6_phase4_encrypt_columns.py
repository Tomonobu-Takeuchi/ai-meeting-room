"""phase4_encrypt_columns

Revision ID: c1d2e3f4a5b6
Revises: 47f2188a8c65
Create Date: 2026-05-22 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import os

revision: str = 'c1d2e3f4a5b6'
down_revision: Union[str, None] = '47f2188a8c65'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    key = os.environ.get('SECRET_MODE_KEY', '')
    if not key:
        raise Exception("SECRET_MODE_KEY が未設定です。Railwayの環境変数を確認してください。")

    # pgcrypto（冪等）
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    # users.name（空文字・NULL除く・未暗号化のみ）
    op.execute(f"""
        UPDATE users
        SET name = pgp_sym_encrypt(name, '{key}')
        WHERE name IS NOT NULL AND name != ''
          AND name NOT LIKE '\\xc0%'
    """)

    # personas（コピーペルソナのみ）
    for col in ['name', 'avatar', 'description', 'personality', 'speaking_style', 'background']:
        op.execute(f"""
            UPDATE personas
            SET {col} = pgp_sym_encrypt({col}, '{key}')
            WHERE user_id IS NOT NULL
              AND {col} IS NOT NULL AND {col} != ''
              AND {col} NOT LIKE '\\xc0%'
        """)

    # persona_learn.content / source
    for col in ['content', 'source']:
        op.execute(f"""
            UPDATE persona_learn
            SET {col} = pgp_sym_encrypt({col}, '{key}')
            WHERE {col} IS NOT NULL AND {col} != ''
              AND {col} NOT LIKE '\\xc0%'
        """)

    # persona_feedback.correct_response
    op.execute(f"""
        UPDATE persona_feedback
        SET correct_response = pgp_sym_encrypt(correct_response, '{key}')
        WHERE correct_response IS NOT NULL AND correct_response != ''
          AND correct_response NOT LIKE '\\xc0%'
    """)


def downgrade() -> None:
    key = os.environ.get('SECRET_MODE_KEY', '')
    if not key:
        return

    op.execute(f"UPDATE users SET name = pgp_sym_decrypt(name::bytea, '{key}') WHERE name LIKE '\\xc0%'")

    for col in ['name', 'avatar', 'description', 'personality', 'speaking_style', 'background']:
        op.execute(f"UPDATE personas SET {col} = pgp_sym_decrypt({col}::bytea, '{key}') WHERE user_id IS NOT NULL AND {col} LIKE '\\xc0%'")

    for col in ['content', 'source']:
        op.execute(f"UPDATE persona_learn SET {col} = pgp_sym_decrypt({col}::bytea, '{key}') WHERE {col} LIKE '\\xc0%'")

    op.execute(f"UPDATE persona_feedback SET correct_response = pgp_sym_decrypt(correct_response::bytea, '{key}') WHERE correct_response LIKE '\\xc0%'")
