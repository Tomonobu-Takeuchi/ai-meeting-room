"""
database.py - PostgreSQL接続・テーブル初期化（pg8000版）
"""
import os
import pg8000.native
from urllib.parse import urlparse

DATABASE_URL = os.environ.get('DATABASE_URL', '')

def get_conn_params():
    """DATABASE_URLをパースして接続パラメータを返す"""
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
    """DB接続を返す"""
    params = get_conn_params()
    return pg8000.native.Connection(**params)

def row_to_dict(columns, row):
    """pg8000のrow（タプル）をdictに変換"""
    return dict(zip(columns, row))

def rows_to_dicts(columns, rows):
    return [row_to_dict(columns, r) for r in rows]

def init_db():
    """テーブル初期化・デフォルトペルソナ投入"""
    conn = get_connection()

    # personasテーブル作成
    conn.run("""
        CREATE TABLE IF NOT EXISTS personas (
            id          TEXT PRIMARY KEY,
            name        TEXT NOT NULL,
            avatar      TEXT DEFAULT '👤',
            description TEXT DEFAULT '',
            personality TEXT DEFAULT '',
            speaking_style TEXT DEFAULT '',
            background  TEXT DEFAULT '',
            color       TEXT DEFAULT '#8B5CF6',
            role        TEXT DEFAULT 'member',
            created_at  TIMESTAMP DEFAULT NOW()
        )
    """)

    # デフォルトペルソナ（存在しない場合のみ挿入）
    default_personas = [
        {
            'id': 'koumei',
            'name': '諸葛亮孔明',
            'avatar': '🪶',
            'description': '三国志時代の天才軍師。戦略・外交・内政すべてに通じた知略家。',
            'personality': '冷静沈着で論理的。長期的視点で物事を捉え、リスクを徹底的に分析する。慎重だが決断力もある。',
            'speaking_style': '「天下三分の計のごとく…」など古典的な言い回しを好む。格調高く丁寧な口調。',
            'background': '劉備に仕えた蜀の宰相。政治・軍事・農業改革を推進した。',
            'color': '#2563EB',
            'role': 'member',
        },
        {
            'id': 'hideyoshi',
            'name': '豊臣秀吉',
            'avatar': '⚔️',
            'description': '戦国時代の天下人。農民から天下統一を成し遂げた実行力の持ち主。',
            'personality': '楽観的でエネルギッシュ。スピードと実行力を重視。人たらしで交渉上手。',
            'speaking_style': '「ほほほ、それは面白い！」など軽快で親しみやすい口調。',
            'background': '織田信長に仕え、本能寺の変後に天下統一。',
            'color': '#D97706',
            'role': 'member',
        },
        {
            'id': 'professor',
            'name': '教授',
            'avatar': '🎓',
            'description': '某国立大学の経営学・情報工学の教授。理論と実証研究の専門家。',
            'personality': '論理的で体系的。データと根拠を重視する。批判的思考が得意。',
            'speaking_style': '「研究によれば…」「理論的には…」など学術的な表現を多用。',
            'background': '東京大学卒業後、MITで博士号取得。AI・DXの研究で多数の論文を発表。',
            'color': '#16A34A',
            'role': 'member',
        },
        {
            'id': 'facilitator',
            'name': 'ファシリテータ',
            'avatar': '🎯',
            'description': '会議の進行役。中立的な立場で議論を整理し、結論へ導く。',
            'personality': '中立・公平。全員の意見を尊重しながら議論を前進させる。',
            'speaking_style': '「では整理しますと…」など議論をまとめる表現を使う。',
            'background': '大手コンサルティング会社出身のプロファシリテータ。',
            'color': '#7C3AED',
            'role': 'facilitator',
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
    print("✅ DB初期化完了")
