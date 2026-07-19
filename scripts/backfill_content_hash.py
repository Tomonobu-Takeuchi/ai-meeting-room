"""
DUP-HASH バックフィル: persona_learnのcontent_hash未設定行に対し、
contentを復号してハッシュを計算し設定する。
実行方法（本番）: railway run python scripts/backfill_content_hash.py
"""
import hashlib
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database import get_connection, decrypt_value


def backfill():
    conn = get_connection()
    rows = conn.run("SELECT id, content FROM persona_learn WHERE content_hash IS NULL")
    targets = [(r[0], decrypt_value(conn, r[1])) for r in rows]
    print(f"対象: {len(targets)}件")
    success, failed = 0, 0
    for row_id, plaintext in targets:
        try:
            h = hashlib.sha256(plaintext.encode('utf-8')).hexdigest()
            conn.run(
                "UPDATE persona_learn SET content_hash=:hash WHERE id=:id AND content_hash IS NULL",
                hash=h, id=row_id
            )
            success += 1
        except Exception as e:
            failed += 1
            print(f"失敗 id={row_id}: {e}")
    conn.close()
    print(f"完了: 成功{success}件 / 失敗{failed}件")


if __name__ == '__main__':
    backfill()
