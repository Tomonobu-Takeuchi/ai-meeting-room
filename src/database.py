"""
database.py - PostgreSQL接続・テーブル初期化
"""
import os
import psycopg2
from psycopg2.extras import RealDictCursor
import json

DATABASE_URL = os.environ.get('DATABASE_URL', '')

# RailwayのDATABASE_URLは postgres:// だが psycopg2 は postgresql:// が必要
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)


def get_connection():
    """DB接続を返す"""
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)


def init_db():
    """テーブル初期化・デフォルトペルソナ投入"""
    conn = get_connection()
    cur = conn.cursor()

    # personasテーブル作成
    cur.execute("""
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
            'background': '劉備に仕えた蜀の宰相。隆中対をはじめ数多くの戦略を立案。政治・軍事・農業改革を推進した。',
            'color': '#2563EB',
            'role': 'member',
        },
        {
            'id': 'hideyoshi',
            'name': '豊臣秀吉',
            'avatar': '⚔️',
            'description': '戦国時代の天下人。農民から天下統一を成し遂げた実行力の持ち主。',
            'personality': '楽観的でエネルギッシュ。スピードと実行力を重視。人たらしで交渉上手。リスクより機会を見る。',
            'speaking_style': '「ほほほ、それは面白い！」など軽快で親しみやすい口調。庶民的な言葉遣い。',
            'background': '織田信長に仕え、本能寺の変後に天下統一。太閤検地・刀狩りなど革新的な政策を実施。',
            'color': '#D97706',
            'role': 'member',
        },
        {
            'id': 'professor',
            'name': '教授',
            'avatar': '🎓',
            'description': '某国立大学の経営学・情報工学の教授。理論と実証研究の専門家。',
            'personality': '論理的で体系的。データと根拠を重視する。批判的思考が得意。感情より理論を優先。',
            'speaking_style': '「研究によれば…」「理論的には…」など学術的な表現を多用。丁寧で明確な説明。',
            'background': '東京大学卒業後、MITで博士号取得。経営情報システム、AI・DXの研究で多数の論文を発表。',
            'color': '#16A34A',
            'role': 'member',
        },
        {
            'id': 'facilitator',
            'name': 'ファシリテータ',
            'avatar': '🎯',
            'description': '会議の進行役。中立的な立場で議論を整理し、結論へ導く。',
            'personality': '中立・公平。全員の意見を尊重しながら議論を前進させる。要点整理が得意。',
            'speaking_style': '「では整理しますと…」「皆さんの意見を踏まえると…」など議論をまとめる表現を使う。',
            'background': '大手コンサルティング会社出身のプロファシリテータ。経営会議・ワークショップの進行経験豊富。',
            'color': '#7C3AED',
            'role': 'facilitator',
        },
    ]

    for p in default_personas:
        cur.execute("""
            INSERT INTO personas (id, name, avatar, description, personality,
                speaking_style, background, color, role)
            VALUES (%(id)s, %(name)s, %(avatar)s, %(description)s, %(personality)s,
                %(speaking_style)s, %(background)s, %(color)s, %(role)s)
            ON CONFLICT (id) DO NOTHING
        """, p)

    conn.commit()
    cur.close()
    conn.close()
    print("✅ DB初期化完了")
