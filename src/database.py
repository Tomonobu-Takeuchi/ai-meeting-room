"""
database.py - PostgreSQL接続・テーブル初期化（ユーザー認証 + pgvector RAG対応版）
"""
import os
import pg8000.native
from urllib.parse import urlparse

DATABASE_URL = os.environ.get('DATABASE_URL', '')

def get_conn_params():
    url = urlparse(DATABASE_URL)
    return {
        'host': url.hostname,
        'port': url.port or 5432,
        'database': url.path.lstrip('/'),
        'user': url.username,
        'password': url.password,
        'ssl_context': True,
    }

def get_connection():
    return pg8000.native.Connection(**get_conn_params())

def row_to_dict(columns, row):
    return dict(zip(columns, row))

def rows_to_dicts(columns, rows):
    return [row_to_dict(columns, r) for r in rows]

def init_db():
    """テーブル初期化"""
    conn = get_connection()

    # pgvector拡張
    try:
        conn.run("CREATE EXTENSION IF NOT EXISTS vector")
    except Exception:
        pass

    # ===== usersテーブル =====
    conn.run("""
        CREATE TABLE IF NOT EXISTS users (
            id          SERIAL PRIMARY KEY,
            email       TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            name        TEXT DEFAULT '',
            plan        TEXT DEFAULT 'free',
            created_at  TIMESTAMP DEFAULT NOW()
        )
    """)

    # ===== personasテーブル（user_id追加） =====
    conn.run("""
        CREATE TABLE IF NOT EXISTS personas (
            id             TEXT NOT NULL,
            user_id        INTEGER REFERENCES users(id) ON DELETE CASCADE,
            name           TEXT NOT NULL,
            avatar         TEXT DEFAULT '👤',
            description    TEXT DEFAULT '',
            personality    TEXT DEFAULT '',
            speaking_style TEXT DEFAULT '',
            background     TEXT DEFAULT '',
            color          TEXT DEFAULT '#8B5CF6',
            role           TEXT DEFAULT 'member',
            is_default     BOOLEAN DEFAULT FALSE,
            created_at     TIMESTAMP DEFAULT NOW()
        )
    """)

    # ユニーク制約を追加（id + user_idの組み合わせ）
    try:
        conn.run("""
            CREATE UNIQUE INDEX IF NOT EXISTS personas_id_user_idx
            ON personas (id, COALESCE(user_id, -1))
        """)
    except Exception:
        pass

    # user_idカラムがない場合は追加（既存テーブルへの対応）
    try:
        conn.run("ALTER TABLE personas ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id) ON DELETE CASCADE")
    except Exception:
        pass
    try:
        conn.run("ALTER TABLE personas ADD COLUMN IF NOT EXISTS is_default BOOLEAN DEFAULT FALSE")
    except Exception:
        pass

    # ===== persona_learnテーブル（user_id追加） =====
    conn.run("""
        CREATE TABLE IF NOT EXISTS persona_learn (
            id          SERIAL PRIMARY KEY,
            persona_id  TEXT NOT NULL,
            user_id     INTEGER REFERENCES users(id) ON DELETE CASCADE,
            content     TEXT NOT NULL,
            source      TEXT DEFAULT '',
            embedding   vector(1536),
            created_at  TIMESTAMP DEFAULT NOW()
        )
    """)

    try:
        conn.run("ALTER TABLE persona_learn ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id) ON DELETE CASCADE")
    except Exception:
        pass

    # ベクトル検索インデックス
    try:
        conn.run("""
            CREATE INDEX IF NOT EXISTS persona_learn_embedding_idx
            ON persona_learn USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = 10)
        """)
    except Exception:
        pass

    # デフォルトペルソナ（user_id=NULL = 全ユーザー共通）
    default_personas = [
        {
            'id': 'koumei', 'name': '諸葛亮孔明', 'avatar': '🪶',
            'description': '三国志時代の天才軍師。戦略・外交・内政すべてに通じた知略家。',
            'personality': '冷静沈着で論理的。長期的視点で物事を捉え、リスクを徹底的に分析する。慎重だが決断力もある。',
            'speaking_style': '「天下三分の計のごとく…」など古典的な言い回しを好む。格調高く丁寧な口調。',
            'background': '劉備に仕えた蜀の宰相。政治・軍事・農業改革を推進した。',
            'color': '#2563EB', 'role': 'member',
        },
        {
            'id': 'hideyoshi', 'name': '豊臣秀吉', 'avatar': '⚔️',
            'description': '戦国時代の天下人。農民から天下統一を成し遂げた実行力の持ち主。',
            'personality': '楽観的でエネルギッシュ。スピードと実行力を重視。人たらしで交渉上手。',
            'speaking_style': '「ほほほ、それは面白い！」など軽快で親しみやすい口調。',
            'background': '織田信長に仕え、本能寺の変後に天下統一。',
            'color': '#D97706', 'role': 'member',
        },
        {
            'id': 'professor', 'name': '教授', 'avatar': '🎓',
            'description': '某国立大学の経営学・情報工学の教授。理論と実証研究の専門家。',
            'personality': '論理的で体系的。データと根拠を重視する。批判的思考が得意。',
            'speaking_style': '「研究によれば…」「理論的には…」など学術的な表現を多用。',
            'background': '東京大学卒業後、MITで博士号取得。AI・DXの研究で多数の論文を発表。',
            'color': '#16A34A', 'role': 'member',
        },
        {
            'id': 'facilitator', 'name': 'ファシリテータ', 'avatar': 'data:image/png;base64,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',
            'description': '会議の進行役。中立的な立場で議論を整理し、結論へ導く。',
            'personality': '中立・公平。全員の意見を尊重しながら議論を前進させる。',
            'speaking_style': '「では整理しますと…」など議論をまとめる表現を使う。',
            'background': '大手コンサルティング会社出身のプロファシリテータ。',
            'color': '#7C3AED', 'role': 'facilitator',
        },
    ]

    for p in default_personas:
        try:
            # すでに存在するか確認
            existing = conn.run("""
                SELECT id FROM personas WHERE id=:id AND user_id IS NULL
            """, id=p['id'])
            if not existing:
                conn.run("""
                    INSERT INTO personas (id, user_id, name, avatar, description, personality,
                        speaking_style, background, color, role, is_default)
                    VALUES (:id, NULL, :name, :avatar, :description, :personality,
                        :speaking_style, :background, :color, :role, TRUE)
                """,
                id=p['id'], name=p['name'], avatar=p['avatar'],
                description=p['description'], personality=p['personality'],
                speaking_style=p['speaking_style'], background=p['background'],
                color=p['color'], role=p['role'])
        except Exception as e:
            print(f"ペルソナ挿入スキップ: {e}")

    conn.close()
    print("✅ DB初期化完了（ユーザー認証対応）")


# ===== ユーザー認証関連 =====

def create_user(email, password_hash, name=''):
    conn = get_connection()
    try:
        conn.run("""
            INSERT INTO users (email, password_hash, name)
            VALUES (:email, :password_hash, :name)
        """, email=email, password_hash=password_hash, name=name)
        rows = conn.run("SELECT id, email, name, plan FROM users WHERE email=:email", email=email)
        conn.close()
        return row_to_dict(['id','email','name','plan'], rows[0]) if rows else None
    except Exception as e:
        conn.close()
        raise e

def get_user_by_email(email):
    conn = get_connection()
    rows = conn.run("""
        SELECT id, email, name, plan, password_hash FROM users WHERE email=:email
    """, email=email)
    conn.close()
    return row_to_dict(['id','email','name','plan','password_hash'], rows[0]) if rows else None

def get_user_by_id(user_id):
    conn = get_connection()
    rows = conn.run("""
        SELECT id, email, name, plan FROM users WHERE id=:id
    """, id=user_id)
    conn.close()
    return row_to_dict(['id','email','name','plan'], rows[0]) if rows else None


# ===== RAG関連 =====

def save_learn_data(persona_id, user_id, content, source, embedding_vector=None):
    conn = get_connection()
    if embedding_vector:
        vec_str = '[' + ','.join(str(v) for v in embedding_vector) + ']'
        conn.run("""
            INSERT INTO persona_learn (persona_id, user_id, content, source, embedding)
            VALUES (:persona_id, :user_id, :content, :source, :embedding::vector)
        """, persona_id=persona_id, user_id=user_id, content=content,
            source=source, embedding=vec_str)
    else:
        conn.run("""
            INSERT INTO persona_learn (persona_id, user_id, content, source)
            VALUES (:persona_id, :user_id, :content, :source)
        """, persona_id=persona_id, user_id=user_id, content=content, source=source)
    conn.close()

def search_learn_data(persona_id, user_id, query_embedding, limit=3):
    conn = get_connection()
    vec_str = '[' + ','.join(str(v) for v in query_embedding) + ']'
    rows = conn.run("""
        SELECT content, source,
               1 - (embedding <=> :query_vec::vector) AS similarity
        FROM persona_learn
        WHERE persona_id = :persona_id
          AND (user_id = :user_id OR user_id IS NULL)
          AND embedding IS NOT NULL
        ORDER BY embedding <=> :query_vec::vector
        LIMIT :limit
    """, persona_id=persona_id, user_id=user_id, query_vec=vec_str, limit=limit)
    conn.close()
    return [{'content': r[0], 'source': r[1], 'similarity': float(r[2])} for r in rows]

def get_learn_data_simple(persona_id, user_id, limit=5):
    conn = get_connection()
    rows = conn.run("""
        SELECT content, source FROM persona_learn
        WHERE persona_id = :persona_id
          AND (user_id = :user_id OR user_id IS NULL)
        ORDER BY created_at DESC LIMIT :limit
    """, persona_id=persona_id, user_id=user_id, limit=limit)
    conn.close()
    return [{'content': r[0], 'source': r[1]} for r in rows]

def get_learn_data_count(persona_id, user_id=None):
    conn = get_connection()
    if user_id:
        rows = conn.run("""
            SELECT COUNT(*) FROM persona_learn
            WHERE persona_id=:persona_id AND (user_id=:user_id OR user_id IS NULL)
        """, persona_id=persona_id, user_id=user_id)
    else:
        rows = conn.run("""
            SELECT COUNT(*) FROM persona_learn WHERE persona_id=:persona_id
        """, persona_id=persona_id)
    conn.close()
    return rows[0][0] if rows else 0

def get_all_learn_data(persona_id, user_id):
    conn = get_connection()
    rows = conn.run("""
        SELECT id, content, source, created_at FROM persona_learn
        WHERE persona_id=:persona_id AND (user_id=:user_id OR user_id IS NULL)
        ORDER BY created_at DESC
    """, persona_id=persona_id, user_id=user_id)
    conn.close()
    return [{'id': r[0],
             'content': r[1][:100]+'...' if len(r[1])>100 else r[1],
             'source': r[2], 'created_at': str(r[3])} for r in rows]

def delete_learn_data(persona_id, user_id, learn_id):
    conn = get_connection()
    conn.run("""
        DELETE FROM persona_learn
        WHERE id=:id AND persona_id=:persona_id AND user_id=:user_id
    """, id=learn_id, persona_id=persona_id, user_id=user_id)
    conn.close()
