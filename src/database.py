"""
database.py - PostgreSQL接続・テーブル初期化（pg8000 + pgvector RAG対応版）
"""
import os
import json
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
    """テーブル初期化・デフォルトペルソナ投入"""
    conn = get_connection()

    # pgvector拡張を有効化（既にある場合はスキップ）
    try:
        conn.run("CREATE EXTENSION IF NOT EXISTS vector")
    except Exception:
        pass

    # personasテーブル
    conn.run("""
        CREATE TABLE IF NOT EXISTS personas (
            id             TEXT PRIMARY KEY,
            name           TEXT NOT NULL,
            avatar         TEXT DEFAULT '👤',
            description    TEXT DEFAULT '',
            personality    TEXT DEFAULT '',
            speaking_style TEXT DEFAULT '',
            background     TEXT DEFAULT '',
            color          TEXT DEFAULT '#8B5CF6',
            role           TEXT DEFAULT 'member',
            created_at     TIMESTAMP DEFAULT NOW()
        )
    """)

    # persona_learnテーブル（RAG用学習データ）
    conn.run("""
        CREATE TABLE IF NOT EXISTS persona_learn (
            id          SERIAL PRIMARY KEY,
            persona_id  TEXT NOT NULL REFERENCES personas(id) ON DELETE CASCADE,
            content     TEXT NOT NULL,
            source      TEXT DEFAULT '',
            embedding   vector(1536),
            created_at  TIMESTAMP DEFAULT NOW()
        )
    """)

    # ベクトル検索用インデックス
    try:
        conn.run("""
            CREATE INDEX IF NOT EXISTS persona_learn_embedding_idx
            ON persona_learn USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = 10)
        """)
    except Exception:
        pass

    # デフォルトペルソナ投入
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
            'background': '織田信長に仕え、本能寺の変後に天下統一。太閤検地・刀狩りなど革新的な政策を実施。',
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
            'id': 'facilitator', 'name': 'ファシリテータ', 'avatar': '🎯',
            'description': '会議の進行役。中立的な立場で議論を整理し、結論へ導く。',
            'personality': '中立・公平。全員の意見を尊重しながら議論を前進させる。',
            'speaking_style': '「では整理しますと…」など議論をまとめる表現を使う。',
            'background': '大手コンサルティング会社出身のプロファシリテータ。',
            'color': '#7C3AED', 'role': 'facilitator',
        },
    ]

    for p in default_personas:
        conn.run("""
            INSERT INTO personas (id, name, avatar, description, personality,
                speaking_style, background, color, role)
            VALUES (:id, :name, :avatar, :description, :personality,
                :speaking_style, :background, :color, :role)
            ON CONFLICT (id) DO NOTHING
        """,
        id=p['id'], name=p['name'], avatar=p['avatar'],
        description=p['description'], personality=p['personality'],
        speaking_style=p['speaking_style'], background=p['background'],
        color=p['color'], role=p['role'])

    conn.close()
    print("✅ DB初期化完了（pgvector対応）")


# ===== RAG関連関数 =====

def get_embedding(text, client):
    """テキストをベクトル化（OpenAI Embedding API使用）"""
    import anthropic
    # AnthropicはEmbeddingを提供していないためOpenAI互換APIを使用
    # ここでは簡易的にAnthropicのAPIでベクトル化の代替として
    # テキストの特徴をJSONで返すアプローチを使用
    # 本格実装はOpenAI text-embedding-3-smallを推奨
    raise NotImplementedError("Embedding requires OpenAI API key")


def save_learn_data(persona_id, content, source, embedding_vector=None):
    """学習データをDBに保存（ベクトル付き）"""
    conn = get_connection()
    if embedding_vector:
        # ベクトルをpg8000用にJSON配列文字列として渡す
        vec_str = '[' + ','.join(str(v) for v in embedding_vector) + ']'
        conn.run("""
            INSERT INTO persona_learn (persona_id, content, source, embedding)
            VALUES (:persona_id, :content, :source, :embedding::vector)
        """, persona_id=persona_id, content=content,
            source=source, embedding=vec_str)
    else:
        conn.run("""
            INSERT INTO persona_learn (persona_id, content, source)
            VALUES (:persona_id, :content, :source)
        """, persona_id=persona_id, content=content, source=source)
    conn.close()


def search_learn_data(persona_id, query_embedding, limit=3):
    """議題に関連する学習データをベクトル検索で取得"""
    conn = get_connection()
    vec_str = '[' + ','.join(str(v) for v in query_embedding) + ']'
    rows = conn.run("""
        SELECT content, source,
               1 - (embedding <=> :query_vec::vector) AS similarity
        FROM persona_learn
        WHERE persona_id = :persona_id
          AND embedding IS NOT NULL
        ORDER BY embedding <=> :query_vec::vector
        LIMIT :limit
    """, persona_id=persona_id, query_vec=vec_str, limit=limit)
    conn.close()
    return [{'content': r[0], 'source': r[1], 'similarity': float(r[2])} for r in rows]


def get_learn_data_simple(persona_id, limit=5):
    """ベクトルなしで最新の学習データを取得（フォールバック用）"""
    conn = get_connection()
    rows = conn.run("""
        SELECT content, source FROM persona_learn
        WHERE persona_id = :persona_id
        ORDER BY created_at DESC
        LIMIT :limit
    """, persona_id=persona_id, limit=limit)
    conn.close()
    return [{'content': r[0], 'source': r[1]} for r in rows]


def get_learn_data_count(persona_id):
    """ペルソナの学習データ件数を取得"""
    conn = get_connection()
    rows = conn.run("""
        SELECT COUNT(*) FROM persona_learn WHERE persona_id = :persona_id
    """, persona_id=persona_id)
    conn.close()
    return rows[0][0] if rows else 0


def delete_learn_data(persona_id, learn_id):
    """学習データを削除"""
    conn = get_connection()
    conn.run("""
        DELETE FROM persona_learn WHERE id = :id AND persona_id = :persona_id
    """, id=learn_id, persona_id=persona_id)
    conn.close()


def get_all_learn_data(persona_id):
    """ペルソナの全学習データを取得"""
    conn = get_connection()
    rows = conn.run("""
        SELECT id, content, source, created_at FROM persona_learn
        WHERE persona_id = :persona_id
        ORDER BY created_at DESC
    """, persona_id=persona_id)
    conn.close()
    return [{'id': r[0], 'content': r[1][:100]+'...' if len(r[1])>100 else r[1],
             'source': r[2], 'created_at': str(r[3])} for r in rows]
