"""
BUG-EMB1 バックフィル: persona_learnのembedding未設定行に対し、
contentを復号してembeddingを生成し、idベースで更新する。
実行方法（本番）: railway run python scripts/backfill_learn_embeddings.py
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database import get_connection, decrypt_value, update_learn_data_embedding


def backfill():
    openai_key = os.environ.get('OPENAI_API_KEY', '')
    if not openai_key:
        print("OPENAI_API_KEY未設定のため中止")
        return
    import openai
    client = openai.OpenAI(api_key=openai_key, timeout=30.0)

    conn = get_connection()
    rows = conn.run("SELECT id, content FROM persona_learn WHERE embedding IS NULL")
    targets = [(r[0], decrypt_value(conn, r[1])) for r in rows]
    conn.close()

    print(f"対象: {len(targets)}件")
    success, failed = 0, 0
    for learn_id, plaintext in targets:
        try:
            res = client.embeddings.create(model="text-embedding-3-small", input=plaintext[:8000])
            update_learn_data_embedding(learn_id, res.data[0].embedding)
            success += 1
        except Exception as e:
            failed += 1
            print(f"失敗 id={learn_id}: {e}")
    print(f"完了: 成功{success}件 / 失敗{failed}件")


if __name__ == '__main__':
    backfill()
