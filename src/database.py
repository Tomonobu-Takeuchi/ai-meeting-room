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
            'id': 'elizabeth1', 'name': 'エリザベス一世', 'avatar': '👑',
            'description': '16世紀イングランド女王。宗教改革・海洋覇権・文化黄金期を牽引した希代の名君。',
            'personality': '知性と意志力を兼ね備え、感情より国益を優先する現実主義者。交渉上手で権威と魅力を巧みに使い分ける。',
            'speaking_style': '「余の判断は揺るがぬ」など威厳ある口調だが、時に女性ならではの柔らかさも見せる。',
            'background': '父ヘンリー8世の娘として波乱の生涯を経て即位。45年の治世でイングランドを欧州の強国へ導いた。',
            'color': '#B45309', 'role': 'member',
        },
        {
            'id': 'facilitator', 'name': 'ファシリテータ', 'avatar': '🎯',
            'description': '会議の進行役。中立的な立場で議論を整理し、結論へ導く。',
            'personality': '中立・公平。全員の意見を尊重しながら議論を前進させる。',
            'speaking_style': '「では整理しますと…」など議論をまとめる表現を使う。',
            'background': '大手コンサルティング会社出身のプロファシリテータ。',
            'color': '#7C3AED', 'role': 'facilitator',
        },
    ]

    for p in default_personas:
        try:
            # 既存のデフォルトペルソナを削除してから再挿入（定義を常に最新に保つ）
            conn.run("DELETE FROM personas WHERE id=:id AND user_id IS NULL", id=p['id'])
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
            print(f"ペルソナ挿入エラー: {e}")

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
