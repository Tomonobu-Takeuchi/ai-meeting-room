"""
DUP-HASH（重複チェック修正）＋ TRUNC-TOK（トークン超過対応）のオラクルロジック。
"""
import hashlib
import sqlite3
import os
import base64


def content_hash(plaintext):
    """content_hash列に格納する決定的ハッシュ（暗号化とは独立に、常に同じ平文なら同じ値）"""
    return hashlib.sha256(plaintext.encode('utf-8')).hexdigest()


# ---- 重複チェック（sqlite代替DB + 非決定的暗号化モックで検証） ----

def mock_pgp_sym_encrypt(plaintext):
    salt = base64.b64encode(os.urandom(8)).decode()
    return f"ENC[{salt}]{plaintext}"


def setup_db():
    conn = sqlite3.connect(':memory:')
    conn.execute("""
        CREATE TABLE persona_learn (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            persona_id TEXT, user_id INTEGER,
            content TEXT, content_hash TEXT, source TEXT, embedding TEXT
        )
    """)
    return conn


def save_learn_data_hashfix(conn, persona_id, user_id, content, source):
    """修正後: content_hash（決定的）で重複チェックする"""
    h = content_hash(content)
    existing = conn.execute(
        "SELECT id FROM persona_learn WHERE persona_id=? AND user_id=? AND content_hash=?",
        (persona_id, user_id, h)
    ).fetchone()
    if existing:
        return existing[0], True  # (id, was_duplicate)
    enc_content = mock_pgp_sym_encrypt(content)
    cur = conn.execute(
        "INSERT INTO persona_learn (persona_id, user_id, content, content_hash, source, embedding) VALUES (?,?,?,?,?,NULL)",
        (persona_id, user_id, enc_content, h, source)
    )
    conn.commit()
    return cur.lastrowid, False


# ---- トークン超過対応（実tiktokenはCode環境で最終確認。ここでは境界ロジックのみ検証） ----

def truncate_to_tokens(text, encode_fn, decode_fn, max_tokens=8000):
    """encode_fn/decode_fnを外から渡すことで、実tiktokenでもモックでも同じロジックを検証できる"""
    tokens = encode_fn(text)
    if len(tokens) <= max_tokens:
        return text
    return decode_fn(tokens[:max_tokens])


def mock_encode_2_tokens_per_char(text):
    """日本語想定のワースト系モック: 1文字=2トークンとして扱う"""
    return list(text) * 2


def mock_decode_2_tokens_per_char(tokens):
    return ''.join(tokens[0::2])
