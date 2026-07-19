"""
BUG-EMB1 Chat側オラクル検証（本体）。
実PostgreSQL/pgcryptoはChatのサンドボックスで用意できない（root権限なし、Docker不可）ため、
sqlite3を「関係DB」の代替として使い、pgp_sym_encryptの本質的性質
（同じ平文でも呼ぶたびに異なる暗号文になる＝非決定的）を模したモック暗号化関数を使って、
WHERE句によるマッチングロジックが同一構造で壊れる／直ることを実証する。
「content文字列でUPDATEを絞り込む」 vs 「idでUPDATEを絞り込む」というWHERE句の
一致・不一致の性質はDBエンジンに依存しない普遍的な挙動であり、sqlite3で検証しても結論は変わらない。
Codeは2節（Docker+実pgcrypto）で同じ結論を実DBでも再現させること。
"""
import sqlite3
import os
import base64


def mock_pgp_sym_encrypt(plaintext, key):
    """pgp_sym_encryptの非決定性（呼ぶたびに異なる暗号文になる）を再現するモック"""
    salt = base64.b64encode(os.urandom(8)).decode()
    return f"ENC[{salt}]{plaintext}"


def mock_pgp_sym_decrypt(ciphertext, key):
    marker = ciphertext.find(']')
    return ciphertext[marker + 1:]


def setup_db():
    conn = sqlite3.connect(':memory:')
    conn.execute("""
        CREATE TABLE persona_learn (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            persona_id TEXT, user_id INTEGER,
            content TEXT, source TEXT, embedding TEXT
        )
    """)
    return conn


# ===== 修正前（バグを再現する版） =====

def save_learn_data_old(conn, persona_id, user_id, content, source):
    enc_content = mock_pgp_sym_encrypt(content, 'key')
    enc_source = mock_pgp_sym_encrypt(source, 'key')
    conn.execute(
        "INSERT INTO persona_learn (persona_id, user_id, content, source, embedding) VALUES (?,?,?,?,NULL)",
        (persona_id, user_id, enc_content, enc_source)
    )
    conn.commit()


def update_learn_data_embedding_old(conn, persona_id, user_id, content, embedding):
    """修正前：contentの平文でUPDATEを絞り込む（バグ）"""
    cur = conn.execute(
        "UPDATE persona_learn SET embedding=? WHERE persona_id=? AND user_id=? AND content=? AND embedding IS NULL",
        (embedding, persona_id, user_id, content)
    )
    conn.commit()
    return cur.rowcount


# ===== 修正後 =====

def save_learn_data_new(conn, persona_id, user_id, content, source):
    """修正後：INSERT時にidを返す"""
    enc_content = mock_pgp_sym_encrypt(content, 'key')
    enc_source = mock_pgp_sym_encrypt(source, 'key')
    cur = conn.execute(
        "INSERT INTO persona_learn (persona_id, user_id, content, source, embedding) VALUES (?,?,?,?,NULL)",
        (persona_id, user_id, enc_content, enc_source)
    )
    conn.commit()
    return cur.lastrowid


def update_learn_data_embedding_new(conn, learn_id, embedding):
    """修正後：idでUPDATEを絞り込む"""
    cur = conn.execute(
        "UPDATE persona_learn SET embedding=? WHERE id=? AND embedding IS NULL",
        (embedding, learn_id)
    )
    conn.commit()
    return cur.rowcount


# ===== バックフィルスクリプトのロジック =====

def backfill_missing_embeddings(conn, embed_fn):
    """embedding IS NULLの行を全件取得→復号→embed_fnで生成→idでUPDATE。冪等。"""
    rows = conn.execute("SELECT id, content FROM persona_learn WHERE embedding IS NULL").fetchall()
    success, failed = 0, 0
    for row_id, enc_content in rows:
        try:
            plaintext = mock_pgp_sym_decrypt(enc_content, 'key')
            embedding = embed_fn(plaintext)
            n = update_learn_data_embedding_new(conn, row_id, embedding)
            if n == 1:
                success += 1
            else:
                failed += 1
        except Exception:
            failed += 1
    return success, failed
