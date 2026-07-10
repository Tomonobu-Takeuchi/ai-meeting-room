"""
database.py - PostgreSQL接続・テーブル初期化（ユーザー認証 + pgvector RAG対応版）
"""
import os
import pg8000.native
from urllib.parse import urlparse

DATABASE_URL = os.environ.get('DATABASE_URL', '')
SECRET_MODE_KEY = os.environ.get('SECRET_MODE_KEY', '')

def get_conn_params():
    url = urlparse(DATABASE_URL)
    params = {
        'host': url.hostname,
        'port': url.port or 5432,
        'database': url.path.lstrip('/'),
        'user': url.username,
        'password': url.password,
    }
    # ローカル開発環境（localhost/127.0.0.1）はSSL不要
    if url.hostname not in ('localhost', '127.0.0.1'):
        params['ssl_context'] = True
    return params

def get_connection():
    return pg8000.native.Connection(**get_conn_params())

def row_to_dict(columns, row):
    return dict(zip(columns, row))

def rows_to_dicts(columns, rows):
    return [row_to_dict(columns, r) for r in rows]


def encrypt_value(conn, value):
    """平文 → 暗号文。空文字・Noneはそのまま返す"""
    if not value or not SECRET_MODE_KEY:
        return value
    rows = conn.run(
        "SELECT pgp_sym_encrypt(:val, :key)",
        val=str(value), key=SECRET_MODE_KEY
    )
    return rows[0][0] if rows else value


def decrypt_value(conn, value):
    """暗号文 → 平文。空文字・None・復号失敗はそのまま返す"""
    if not value or not SECRET_MODE_KEY:
        return value
    try:
        rows = conn.run(
            "SELECT pgp_sym_decrypt(:val::bytea, :key)",
            val=value, key=SECRET_MODE_KEY
        )
        return rows[0][0] if rows else value
    except Exception:
        return value  # 移行期の平文データはそのまま返す


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
            trial_layer2_used BOOLEAN DEFAULT FALSE,
            trial_layer3_used BOOLEAN DEFAULT FALSE,
            created_at          TIMESTAMP DEFAULT NOW(),
            is_earlybird        BOOLEAN DEFAULT FALSE NOT NULL,
            billing_anchor_day  INTEGER
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
    try:
        conn.run("ALTER TABLE users ADD COLUMN IF NOT EXISTS tos_agreed_at TIMESTAMP")
    except Exception:
        pass
    try:
        conn.run("ALTER TABLE personas ADD COLUMN IF NOT EXISTS tos_agreed_at TIMESTAMP")
    except Exception:
        pass
    try:
        conn.run("ALTER TABLE personas ADD COLUMN IF NOT EXISTS is_deceased_confirmed BOOLEAN DEFAULT FALSE")
    except Exception:
        pass
    try:
        conn.run("ALTER TABLE users ADD COLUMN IF NOT EXISTS trial_layer2_used BOOLEAN DEFAULT FALSE")
    except Exception:
        pass
    try:
        conn.run("ALTER TABLE users ADD COLUMN IF NOT EXISTS trial_layer3_used BOOLEAN DEFAULT FALSE")
    except Exception:
        pass
    try:
        conn.run("ALTER TABLE users ADD COLUMN IF NOT EXISTS birth_date DATE")
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

    # Phase 1-3テーブル初期化
    init_phase_tables(conn)
    # 課金テーブル初期化
    init_payment_tables(conn)
    conn.close()
    print("✅ DB初期化完了（ユーザー認証対応）")


# ===== ユーザー認証関連 =====

def create_user(email, password_hash, name='', birth_date=None):
    conn = get_connection()
    try:
        conn.run("""
            INSERT INTO users (email, password_hash, name, birth_date)
            VALUES (:email, :password_hash, :name, :birth_date)
        """, email=email, password_hash=password_hash,
           name=encrypt_value(conn, name), birth_date=birth_date)
        rows = conn.run("SELECT id, email, name, plan FROM users WHERE email=:email", email=email)
        if not rows:
            conn.close()
            return None
        d = row_to_dict(['id','email','name','plan'], rows[0])
        d['name'] = decrypt_value(conn, d['name'])
        conn.close()
        return d
    except Exception as e:
        conn.close()
        raise e

def get_user_by_email(email):
    conn = get_connection()
    rows = conn.run("""
        SELECT id, email, name, plan, password_hash, avatar,
               credits, plan_expires_at, monthly_meeting_count,
               trial_layer2_used, trial_layer3_used,
               is_earlybird, billing_anchor_day
        FROM users WHERE email=:email
    """, email=email)
    if not rows:
        conn.close()
        return None
    d = row_to_dict(['id','email','name','plan','password_hash','avatar',
                     'credits','plan_expires_at','monthly_meeting_count',
                     'trial_layer2_used','trial_layer3_used',
                     'is_earlybird','billing_anchor_day'], rows[0])
    d['name'] = decrypt_value(conn, d['name'])
    conn.close()
    return d

def get_user_by_id(user_id):
    conn = get_connection()
    try:
        rows = conn.run("""
            SELECT id, email, name, plan, credits, plan_expires_at,
                   monthly_meeting_count, monthly_reset_at, avatar, password_hash,
                   trial_layer2_used, trial_layer3_used,
                   layer3_monthly_count, layer3_monthly_reset_at,
                   is_earlybird, billing_anchor_day
            FROM users WHERE id=:id
        """, id=user_id)
        if not rows:
            conn.close()
            return None
        r = rows[0]
        d = row_to_dict(['id','email','name','plan','credits','plan_expires_at',
                         'monthly_meeting_count','monthly_reset_at','avatar','password_hash',
                         'trial_layer2_used','trial_layer3_used',
                         'layer3_monthly_count','layer3_monthly_reset_at',
                         'is_earlybird','billing_anchor_day'], r)
        d['name'] = decrypt_value(conn, d['name'])
        conn.close()
        d['credits'] = d['credits'] or 0
        d['monthly_meeting_count'] = d['monthly_meeting_count'] or 0
        if d['plan_expires_at']:
            d['plan_expires_at'] = d['plan_expires_at'].isoformat()
        return d
    except Exception:
        try:
            conn.close()
        except Exception:
            pass
        conn2 = get_connection()
        rows = conn2.run("SELECT id, email, name, plan, avatar FROM users WHERE id=:id", id=user_id)
        if not rows:
            conn2.close()
            return None
        d = row_to_dict(['id','email','name','plan','avatar'], rows[0])
        d['name'] = decrypt_value(conn2, d['name'])
        conn2.close()
        return d

def update_user_avatar(user_id, avatar):
    conn = get_connection()
    conn.run("UPDATE users SET avatar=:avatar WHERE id=:id", avatar=avatar, id=user_id)
    conn.close()


# ===== 課金関連 =====

def get_user_payment_status(user_id):
    conn = get_connection()
    rows = conn.run("""
        SELECT plan, credits, plan_expires_at, monthly_meeting_count, monthly_reset_at, is_earlybird
        FROM users WHERE id=:id
    """, id=user_id)
    conn.close()
    if not rows:
        return None
    plan, credits, expires_at, monthly_count, reset_at, is_earlybird = rows[0]
    return {
        'plan': plan or 'free',
        'credits': credits or 0,
        'plan_expires_at': expires_at.isoformat() if expires_at else None,
        'monthly_meeting_count': monthly_count or 0,
        'monthly_reset_at': reset_at.isoformat() if reset_at else None,
        'is_earlybird': bool(is_earlybird),
    }


def check_and_use_meeting(user_id):
    """会議開始時のプラン制限チェック＆消費。Returns (ok, reason)"""
    from datetime import datetime, timezone
    conn = get_connection()
    try:
        rows = conn.run("""
            SELECT plan, credits, plan_expires_at, monthly_meeting_count, monthly_reset_at
            FROM users WHERE id=:id
        """, id=user_id)
        if not rows:
            conn.close()
            return False, "ユーザーが見つかりません"

        plan, credits, plan_expires_at, monthly_count, monthly_reset_at = rows[0]
        plan = plan or 'free'
        monthly_count = monthly_count or 0

        now = datetime.now(timezone.utc)

        if plan_expires_at is not None and plan_expires_at.tzinfo is None:
            plan_expires_at = plan_expires_at.replace(tzinfo=timezone.utc)

        # スタンダードプラン（月15回・billing_anchor_day基準リセットはWebhook側
        # reset_monthly_meeting_count が担当。ここではカレンダー月リセットを
        # 適用しない＝二重リセット防止のため、needs_reset計算より前に分岐する）
        if plan == 'standard':
            STANDARD_LIMIT = 15
            if monthly_count >= STANDARD_LIMIT:
                conn.close()
                return False, f"スタンダードプランの月{STANDARD_LIMIT}回の制限に達しました。プロプランへのアップグレードをご検討ください。"
            conn.run("UPDATE users SET monthly_meeting_count=monthly_meeting_count+1 WHERE id=:id", id=user_id)
            conn.close()
            return True, "ok"

        # monthly_reset_atをtimezone-awareに統一（free/pro用）
        if monthly_reset_at is not None and monthly_reset_at.tzinfo is None:
            monthly_reset_at = monthly_reset_at.replace(tzinfo=timezone.utc)

        # 月初リセット判定（free・pro共通：カレンダー月変化基準）
        needs_reset = (
            monthly_reset_at is None or
            monthly_reset_at.year < now.year or
            (monthly_reset_at.year == now.year and monthly_reset_at.month < now.month)
        )
        if needs_reset:
            monthly_count = 0

        # プロプラン（変更なし）
        if plan == 'pro':
            if plan_expires_at and plan_expires_at < now:
                # 期限切れ → free に降格
                conn.run("UPDATE users SET plan='free', plan_expires_at=NULL WHERE id=:id", id=user_id)
                plan = 'free'
            else:
                if needs_reset:
                    conn.run("UPDATE users SET monthly_meeting_count=1, monthly_reset_at=NOW() WHERE id=:id", id=user_id)
                else:
                    conn.run("UPDATE users SET monthly_meeting_count=monthly_meeting_count+1 WHERE id=:id", id=user_id)
                conn.close()
                return True, "ok"

        # 無料プラン（月3回）
        FREE_LIMIT = 3
        if monthly_count >= FREE_LIMIT:
            conn.close()
            return False, f"無料プランの月{FREE_LIMIT}回の制限に達しました。プランをアップグレードしてください。"

        if needs_reset:
            conn.run("UPDATE users SET monthly_meeting_count=1, monthly_reset_at=NOW() WHERE id=:id", id=user_id)
        else:
            conn.run("UPDATE users SET monthly_meeting_count=monthly_meeting_count+1 WHERE id=:id", id=user_id)
        conn.close()
        return True, "ok"
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        print(f"check_and_use_meeting エラー: {e}")
        return False, "会議の開始に失敗しました。しばらく後に再度お試しください。"


def check_and_use_layer3(user_id):
    """proプランのLayer3月次チェック＆カウントアップ。Returns (ok, reason)"""
    from datetime import datetime, timezone
    conn = get_connection()
    try:
        rows = conn.run("""
            SELECT plan, plan_expires_at, layer3_monthly_count, layer3_monthly_reset_at
            FROM users WHERE id=:id
        """, id=user_id)
        if not rows:
            conn.close()
            return False, "ユーザーが見つかりません"

        plan, plan_expires_at, layer3_count, layer3_reset_at = rows[0]
        plan = plan or 'free'
        layer3_count = layer3_count or 0

        now = datetime.now(timezone.utc)

        if plan_expires_at is not None and plan_expires_at.tzinfo is None:
            plan_expires_at = plan_expires_at.replace(tzinfo=timezone.utc)
        if layer3_reset_at is not None and layer3_reset_at.tzinfo is None:
            layer3_reset_at = layer3_reset_at.replace(tzinfo=timezone.utc)

        # pro以外・期限切れはLayer3側で別途制御済みのためスルー
        if plan != 'pro' or (plan_expires_at and plan_expires_at < now):
            conn.close()
            return True, "ok"

        # 月次リセット判定
        needs_reset = (
            layer3_reset_at is None or
            layer3_reset_at.year < now.year or
            (layer3_reset_at.year == now.year and layer3_reset_at.month < now.month)
        )
        if needs_reset:
            layer3_count = 0

        # 30回上限チェック
        LAYER3_LIMIT = 30
        if layer3_count >= LAYER3_LIMIT:
            conn.close()
            return False, f"proプランのLayer3レポートは月{LAYER3_LIMIT}回までです。"

        # カウントアップ
        if needs_reset:
            conn.run("""UPDATE users SET layer3_monthly_count=1,
                layer3_monthly_reset_at=NOW() WHERE id=:id""", id=user_id)
        else:
            conn.run("""UPDATE users SET layer3_monthly_count=layer3_monthly_count+1
                WHERE id=:id""", id=user_id)
        conn.close()
        return True, "ok"
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        print(f"check_and_use_layer3 エラー: {e}")
        return False, "Layer3チェックエラー"


def add_user_credits(user_id, amount):
    print(f"[DB][add_credits] 開始 user_id={user_id!r} (type={type(user_id).__name__}) amount={amount}")
    conn = get_connection()
    try:
        conn.run(
            "UPDATE users SET credits=COALESCE(credits,0)+:amount, plan='standard' WHERE id=:uid",
            amount=amount, uid=user_id
        )
        affected = conn.row_count
        print(f"[DB][add_credits] UPDATE完了 rows_affected={affected} user_id={user_id}")
        if affected == 0:
            # user存在確認
            rows = conn.run("SELECT id, credits FROM users WHERE id=:uid", uid=user_id)
            print(f"[DB][add_credits] 警告: 0行更新 user検索結果={rows}")
    except Exception as e:
        conn.close()
        raise RuntimeError(f"add_user_credits failed (user={user_id} amount={amount}): {e}") from e
    conn.close()


def update_user_plan(user_id, plan_type, expires_at=None, stripe_customer_id=None):
    print(f"[DB][update_plan] 開始 user_id={user_id!r} (type={type(user_id).__name__}) "
          f"plan={plan_type!r} expires_at={expires_at} cid={stripe_customer_id!r}")
    if expires_at and stripe_customer_id:
        # stripe_customer_id カラムを含む UPDATE を試みる
        conn = get_connection()
        try:
            conn.run(
                "UPDATE users SET plan=:plan, plan_expires_at=:exp, stripe_customer_id=:cid WHERE id=:uid",
                plan=plan_type, exp=expires_at, cid=stripe_customer_id, uid=user_id
            )
            affected = conn.row_count
            print(f"[DB][update_plan] UPDATE完了(with_cid) rows_affected={affected} user_id={user_id}")
            if affected == 0:
                rows = conn.run("SELECT id, plan FROM users WHERE id=:uid", uid=user_id)
                print(f"[DB][update_plan] 警告: 0行更新 user検索結果={rows}")
            conn.close()
            return
        except Exception as ex:
            print(f"[DB][update_plan] with_cid失敗 → fallback: {type(ex).__name__}: {ex}")
            conn.close()  # abort 状態のコネクションを破棄
        # フォールバック: stripe_customer_id なしで更新（新コネクション）
        conn = get_connection()
        try:
            conn.run(
                "UPDATE users SET plan=:plan, plan_expires_at=:exp WHERE id=:uid",
                plan=plan_type, exp=expires_at, uid=user_id
            )
            affected = conn.row_count
            print(f"[DB][update_plan] UPDATE完了(fallback) rows_affected={affected} user_id={user_id}")
            if affected == 0:
                rows = conn.run("SELECT id, plan FROM users WHERE id=:uid", uid=user_id)
                print(f"[DB][update_plan] 警告: 0行更新(fallback) user検索結果={rows}")
        except Exception as e:
            conn.close()
            raise RuntimeError(f"update_user_plan fallback failed (user={user_id}): {e}") from e
        conn.close()
    elif expires_at:
        conn = get_connection()
        try:
            conn.run(
                "UPDATE users SET plan=:plan, plan_expires_at=:exp WHERE id=:uid",
                plan=plan_type, exp=expires_at, uid=user_id
            )
            affected = conn.row_count
            print(f"[DB][update_plan] UPDATE完了(expires) rows_affected={affected} user_id={user_id}")
            if affected == 0:
                rows = conn.run("SELECT id, plan FROM users WHERE id=:uid", uid=user_id)
                print(f"[DB][update_plan] 警告: 0行更新(expires) user検索結果={rows}")
        except Exception as e:
            conn.close()
            raise RuntimeError(f"update_user_plan failed (user={user_id}): {e}") from e
        conn.close()
    else:
        conn = get_connection()
        try:
            conn.run(
                "UPDATE users SET plan=:plan WHERE id=:uid",
                plan=plan_type, uid=user_id
            )
            affected = conn.row_count
            print(f"[DB][update_plan] UPDATE完了(plan_only) rows_affected={affected} user_id={user_id}")
            if affected == 0:
                rows = conn.run("SELECT id, plan FROM users WHERE id=:uid", uid=user_id)
                print(f"[DB][update_plan] 警告: 0行更新(plan_only) user検索結果={rows}")
        except Exception as e:
            conn.close()
            raise RuntimeError(f"update_user_plan failed (user={user_id}): {e}") from e
        conn.close()


def save_payment(user_id, stripe_session_id, payment_type, amount_jpy, credits_added=0, stripe_customer_id=None):
    conn = get_connection()
    try:
        conn.run("""
            INSERT INTO payments
                (user_id, stripe_session_id, stripe_customer_id, payment_type, amount_jpy, credits_added)
            VALUES (:user_id, :session_id, :cid, :payment_type, :amount_jpy, :credits_added)
            ON CONFLICT (stripe_session_id) DO NOTHING
        """, user_id=user_id, session_id=stripe_session_id, cid=stripe_customer_id,
            payment_type=payment_type, amount_jpy=amount_jpy, credits_added=credits_added)
    except Exception as e:
        conn.close()
        raise RuntimeError(f"save_payment failed (session={stripe_session_id}): {e}") from e
    conn.close()


def complete_payment(stripe_session_id):
    conn = get_connection()
    try:
        conn.run("""
            UPDATE payments SET status='completed', completed_at=NOW()
            WHERE stripe_session_id=:session_id
        """, session_id=stripe_session_id)
    except Exception as e:
        conn.close()
        raise RuntimeError(f"complete_payment failed (session={stripe_session_id}): {e}") from e
    conn.close()


def get_user_by_stripe_customer(stripe_customer_id):
    conn = get_connection()
    rows = conn.run("SELECT id FROM users WHERE stripe_customer_id=:cid", cid=stripe_customer_id)
    conn.close()
    return rows[0][0] if rows else None


# ===== RAG関連 =====

def save_learn_data(persona_id, user_id, content, source, embedding_vector=None):
    conn = get_connection()
    existing = conn.run("""
        SELECT 1 FROM persona_learn
        WHERE persona_id=:pid AND user_id IS NOT DISTINCT FROM :uid AND content=:content
        LIMIT 1
    """, pid=persona_id, uid=user_id, content=content)
    if existing:
        conn.close()
        return
    enc_content = encrypt_value(conn, content)
    enc_source = encrypt_value(conn, source)
    if embedding_vector:
        vec_str = '[' + ','.join(str(v) for v in embedding_vector) + ']'
        conn.run("""
            INSERT INTO persona_learn (persona_id, user_id, content, source, embedding)
            VALUES (:persona_id, :user_id, :content, :source, :embedding::vector)
        """, persona_id=persona_id, user_id=user_id, content=enc_content,
            source=enc_source, embedding=vec_str)
    else:
        conn.run("""
            INSERT INTO persona_learn (persona_id, user_id, content, source)
            VALUES (:persona_id, :user_id, :content, :source)
        """, persona_id=persona_id, user_id=user_id, content=enc_content, source=enc_source)
    conn.close()

def update_learn_data_embedding(persona_id, user_id, content, embedding_vector):
    """バックグラウンドスレッドから呼ばれる: 既存レコードのembeddingを更新"""
    conn = get_connection()
    vec_str = '[' + ','.join(str(v) for v in embedding_vector) + ']'
    conn.run("""
        UPDATE persona_learn SET embedding = :emb::vector
        WHERE persona_id = :pid
          AND user_id IS NOT DISTINCT FROM :uid
          AND content = :content
          AND embedding IS NULL
    """, emb=vec_str, pid=persona_id, uid=user_id, content=content)
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
    result = []
    for r in rows:
        result.append({
            'content': decrypt_value(conn, r[0]),
            'source': decrypt_value(conn, r[1]),
            'similarity': float(r[2])
        })
    conn.close()
    return result

def get_learn_data_simple(persona_id, user_id, limit=5):
    conn = get_connection()
    rows = conn.run("""
        SELECT content, source FROM persona_learn
        WHERE persona_id = :persona_id
          AND (user_id = :user_id OR user_id IS NULL)
        ORDER BY created_at DESC LIMIT :limit
    """, persona_id=persona_id, user_id=user_id, limit=limit)
    result = [{'content': decrypt_value(conn, r[0]),
               'source': decrypt_value(conn, r[1])} for r in rows]
    conn.close()
    return result

def get_learn_data_count(persona_id, user_id=None):
    conn = get_connection()
    if user_id is not None:
        rows = conn.run("""
            SELECT COUNT(*) FROM persona_learn
            WHERE persona_id=:persona_id AND (user_id=:user_id OR user_id IS NULL)
        """, persona_id=persona_id, user_id=user_id)
    else:
        rows = conn.run("""
            SELECT COUNT(*) FROM persona_learn
            WHERE persona_id=:persona_id AND user_id IS NULL
        """, persona_id=persona_id)
    conn.close()
    return rows[0][0] if rows else 0


def get_learn_data_counts_batch(persona_ids, user_id=None):
    """複数ペルソナのlearn_data件数を1クエリで取得（N+1解消）"""
    if not persona_ids:
        return {}
    conn = get_connection()
    if user_id is not None:
        rows = conn.run("""
            SELECT persona_id, COUNT(*)
            FROM persona_learn
            WHERE persona_id = ANY(:pids)
              AND (user_id=:user_id OR user_id IS NULL)
            GROUP BY persona_id
        """, pids=list(persona_ids), user_id=user_id)
    else:
        rows = conn.run("""
            SELECT persona_id, COUNT(*)
            FROM persona_learn
            WHERE persona_id = ANY(:pids)
              AND user_id IS NULL
            GROUP BY persona_id
        """, pids=list(persona_ids))
    conn.close()
    return {r[0]: r[1] for r in rows}

def get_all_learn_data(persona_id, user_id):
    conn = get_connection()
    if user_id is not None:
        rows = conn.run("""
            SELECT DISTINCT ON (content, source) id, content, source, created_at
            FROM persona_learn
            WHERE persona_id=:persona_id AND (user_id=:user_id OR user_id IS NULL)
            ORDER BY content, source, created_at DESC
            LIMIT 100
        """, persona_id=persona_id, user_id=user_id)
    else:
        rows = conn.run("""
            SELECT DISTINCT ON (content, source) id, content, source, created_at
            FROM persona_learn
            WHERE persona_id=:persona_id AND user_id IS NULL
            ORDER BY content, source, created_at DESC
            LIMIT 100
        """, persona_id=persona_id)
    result = []
    for r in rows:
        dec = decrypt_value(conn, r[1])
        dec_src = decrypt_value(conn, r[2])
        result.append({
            'id': r[0],
            'content': dec[:100]+'...' if dec and len(dec)>100 else dec,
            'source': dec_src,
            'created_at': str(r[3])
        })
    conn.close()
    return result

def delete_learn_data(persona_id, user_id, learn_id):
    conn = get_connection()
    conn.run("""
        DELETE FROM persona_learn
        WHERE id=:id AND persona_id=:persona_id AND user_id=:user_id
    """, id=learn_id, persona_id=persona_id, user_id=user_id)
    conn.close()


# ===== Phase 2: 発言パターンテーブル =====

def init_payment_tables(conn):
    """課金用テーブル・カラム初期化"""
    for sql in [
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS credits INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS plan_expires_at TIMESTAMP",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS monthly_meeting_count INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS monthly_reset_at TIMESTAMP DEFAULT NOW()",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS stripe_customer_id TEXT",
    ]:
        try:
            conn.run(sql)
        except Exception:
            pass

    conn.run("""
        CREATE TABLE IF NOT EXISTS payments (
            id                  SERIAL PRIMARY KEY,
            user_id             INTEGER REFERENCES users(id) ON DELETE CASCADE,
            stripe_session_id   TEXT UNIQUE,
            stripe_customer_id  TEXT,
            payment_type        TEXT NOT NULL,
            amount_jpy          INTEGER NOT NULL,
            credits_added       INTEGER DEFAULT 0,
            status              TEXT DEFAULT 'pending',
            created_at          TIMESTAMP DEFAULT NOW(),
            completed_at        TIMESTAMP
        )
    """)


def init_phase_tables(conn):
    """Phase 1-3用テーブル初期化"""

    # Phase 2: 発言パターン蓄積テーブル
    conn.run("""
        CREATE TABLE IF NOT EXISTS persona_patterns (
            id          SERIAL PRIMARY KEY,
            persona_id  TEXT NOT NULL,
            user_id     INTEGER REFERENCES users(id) ON DELETE CASCADE,
            pattern_type TEXT NOT NULL,
            pattern_text TEXT NOT NULL,
            topic_category TEXT DEFAULT 'general',
            usage_count INTEGER DEFAULT 1,
            created_at  TIMESTAMP DEFAULT NOW()
        )
    """)

    # Phase 3: 会議統計テーブル
    conn.run("""
        CREATE TABLE IF NOT EXISTS persona_meeting_stats (
            persona_id  TEXT NOT NULL,
            user_id     INTEGER NOT NULL,
            meeting_count INTEGER DEFAULT 0,
            last_meeting_at TIMESTAMP DEFAULT NOW(),
            PRIMARY KEY (persona_id, user_id)
        )
    """)

    # ===== meetingsテーブル（会議メタデータ。発言内容はJSONファイル保存のまま） =====
    conn.run("""
        CREATE TABLE IF NOT EXISTS meetings (
            id          SERIAL PRIMARY KEY,
            session_id  TEXT UNIQUE NOT NULL,
            user_id     INTEGER REFERENCES users(id) ON DELETE CASCADE,
            topic       TEXT,
            created_at  TIMESTAMP DEFAULT NOW(),
            ended_at    TIMESTAMP
        )
    """)

    # ===== crisis_keywordsテーブル =====
    conn.run("""
        CREATE TABLE IF NOT EXISTS crisis_keywords (
            id         SERIAL PRIMARY KEY,
            keyword    VARCHAR(100) NOT NULL UNIQUE,
            is_active  BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    initial_keywords = [
        '死にたい', '消えたい', '自殺', '自傷', '死ぬ方法',
        '生きていたくない', 'もう終わりにしたい', '消えてしまいたい'
    ]
    for kw in initial_keywords:
        conn.run("""
            INSERT INTO crisis_keywords (keyword)
            VALUES (:kw)
            ON CONFLICT (keyword) DO NOTHING
        """, kw=kw)

    print("✅ Phase 1-3テーブル初期化完了")


# ===== Phase 2: パターン保存・取得 =====

def save_persona_pattern(persona_id, user_id, pattern_type, pattern_text, topic_category='general'):
    conn = get_connection()
    try:
        # 同一パターンが既にあればusage_countを増やす
        existing = conn.run("""
            SELECT id FROM persona_patterns
            WHERE persona_id=:persona_id AND user_id=:user_id
              AND pattern_type=:pattern_type AND pattern_text=:pattern_text
        """, persona_id=persona_id, user_id=user_id,
            pattern_type=pattern_type, pattern_text=pattern_text)
        if existing:
            conn.run("""
                UPDATE persona_patterns SET usage_count=usage_count+1
                WHERE id=:id
            """, id=existing[0][0])
        else:
            conn.run("""
                INSERT INTO persona_patterns
                    (persona_id, user_id, pattern_type, pattern_text, topic_category)
                VALUES (:persona_id, :user_id, :pattern_type, :pattern_text, :topic_category)
            """, persona_id=persona_id, user_id=user_id,
                pattern_type=pattern_type, pattern_text=pattern_text,
                topic_category=topic_category)
    finally:
        conn.close()

def get_persona_patterns(persona_id, user_id, pattern_type=None, limit=5):
    conn = get_connection()
    try:
        if pattern_type:
            rows = conn.run("""
                SELECT pattern_type, pattern_text, usage_count
                FROM persona_patterns
                WHERE persona_id=:persona_id AND user_id=:user_id
                  AND pattern_type=:pattern_type
                ORDER BY usage_count DESC LIMIT :limit
            """, persona_id=persona_id, user_id=user_id,
                pattern_type=pattern_type, limit=limit)
        else:
            rows = conn.run("""
                SELECT pattern_type, pattern_text, usage_count
                FROM persona_patterns
                WHERE persona_id=:persona_id AND user_id=:user_id
                ORDER BY usage_count DESC LIMIT :limit
            """, persona_id=persona_id, user_id=user_id, limit=limit)
        return [{'pattern_type': r[0], 'pattern_text': r[1], 'usage_count': r[2]} for r in rows]
    finally:
        conn.close()


# ===== meetingsテーブル =====

def create_meeting_record(session_id, user_id, topic):
    """会議開始時にmeetingsテーブルへ行を作成（ゲスト会議はuser_id=NULL）"""
    conn = get_connection()
    try:
        conn.run("""
            INSERT INTO meetings (session_id, user_id, topic)
            VALUES (:session_id, :user_id, :topic)
            ON CONFLICT (session_id) DO NOTHING
        """, session_id=session_id, user_id=user_id, topic=topic)
    finally:
        conn.close()

def end_meeting_record(session_id):
    """会議終了時にended_atを記録"""
    conn = get_connection()
    try:
        conn.run("""
            UPDATE meetings SET ended_at=NOW() WHERE session_id=:session_id
        """, session_id=session_id)
    finally:
        conn.close()


# ===== Phase 3: 会議統計 =====

def increment_meeting_count(persona_id, user_id):
    conn = get_connection()
    try:
        existing = conn.run("""
            SELECT meeting_count FROM persona_meeting_stats
            WHERE persona_id=:persona_id AND user_id=:user_id
        """, persona_id=persona_id, user_id=user_id)
        if existing:
            conn.run("""
                UPDATE persona_meeting_stats
                SET meeting_count=meeting_count+1, last_meeting_at=NOW()
                WHERE persona_id=:persona_id AND user_id=:user_id
            """, persona_id=persona_id, user_id=user_id)
            return existing[0][0] + 1
        else:
            conn.run("""
                INSERT INTO persona_meeting_stats (persona_id, user_id, meeting_count)
                VALUES (:persona_id, :user_id, 1)
            """, persona_id=persona_id, user_id=user_id)
            return 1
    finally:
        conn.close()

def get_meeting_count(persona_id, user_id):
    conn = get_connection()
    try:
        rows = conn.run("""
            SELECT meeting_count FROM persona_meeting_stats
            WHERE persona_id=:persona_id AND user_id=:user_id
        """, persona_id=persona_id, user_id=user_id)
        return rows[0][0] if rows else 0
    finally:
        conn.close()


# ===== Growth: 成熟度スコア管理 =====

def ensure_growth_record(persona_id, user_id, app_type='meeting'):
    """persona_growthの初期レコードを作成（なければ）"""
    conn = get_connection()
    try:
        existing = conn.run("""
            SELECT id FROM persona_growth
            WHERE persona_id=:persona_id AND user_id=:user_id AND app_type=:app_type
        """, persona_id=persona_id, user_id=user_id, app_type=app_type)
        if not existing:
            conn.run("""
                INSERT INTO persona_growth
                    (persona_id, user_id, app_type)
                VALUES (:persona_id, :user_id, :app_type)
            """, persona_id=persona_id, user_id=user_id, app_type=app_type)
            print(f"Growth初期レコード作成: {persona_id} / user:{user_id}")
    finally:
        conn.close()


def update_growth_conversation(persona_id, user_id, topic, app_type='meeting'):
    """会話終了時にconversation_countとunique_topic_countを更新"""
    conn = get_connection()
    try:
        # 既存トピック一覧を取得してユニーク数を計算
        rows = conn.run("""
            SELECT unique_topic_count, conversation_count FROM persona_growth
            WHERE persona_id=:persona_id AND user_id=:user_id AND app_type=:app_type
        """, persona_id=persona_id, user_id=user_id, app_type=app_type)
        if not rows:
            return
        current_unique = rows[0][0] or 0
        current_conv = rows[0][1] or 0
        # トピックログをpersona_learnから取得してユニーク数を推定
        topic_rows = conn.run("""
            SELECT COUNT(DISTINCT source) FROM persona_learn
            WHERE persona_id=:persona_id AND user_id=:user_id
        """, persona_id=persona_id, user_id=user_id)
        unique_topics = topic_rows[0][0] if topic_rows else current_unique
        conn.run("""
            UPDATE persona_growth
            SET conversation_count = conversation_count + 1,
                unique_topic_count = :unique_topics,
                updated_at = NOW()
            WHERE persona_id=:persona_id AND user_id=:user_id AND app_type=:app_type
        """, persona_id=persona_id, user_id=user_id, app_type=app_type,
             unique_topics=unique_topics)
    finally:
        conn.close()


def update_growth_knowledge(persona_id, user_id, token_count, app_type='meeting'):
    """学習データ追加時にdoc_token_countを更新"""
    conn = get_connection()
    try:
        conn.run("""
            UPDATE persona_growth
            SET doc_token_count = doc_token_count + :token_count,
                updated_at = NOW()
            WHERE persona_id=:persona_id AND user_id=:user_id AND app_type=:app_type
        """, persona_id=persona_id, user_id=user_id, app_type=app_type,
             token_count=token_count)
    finally:
        conn.close()


def calculate_and_save_maturity(persona_id, user_id, app_type='meeting'):
    """
    成熟度スコアを計算してDBに保存
    score = A*0.5 + B*0.3 + C*0.2
    """
    conn = get_connection()
    try:
        rows = conn.run("""
            SELECT doc_token_count, conversation_count, unique_topic_count,
                   feedback_count, positive_count, recent_positive_rate,
                   profile_completeness, avg_session_length, tuning_count
            FROM persona_growth
            WHERE persona_id=:persona_id AND user_id=:user_id AND app_type=:app_type
        """, persona_id=persona_id, user_id=user_id, app_type=app_type)
        if not rows:
            return
        r = rows[0]
        doc_tokens, conv_count, unique_topics = r[0] or 0, r[1] or 0, r[2] or 0
        feedback_count, positive_count, recent_positive = r[3] or 0, r[4] or 0, r[5] or 0.0
        profile_comp, avg_session, tuning = r[6] or 0.0, r[7] or 0.0, r[8] or 0

        # 軸A：知識量スコア（0-100）
        a_doc = min(doc_tokens / 5000 * 40, 40)        # 最大40点（5000トークンで満点）
        a_conv = min(conv_count / 20 * 40, 40)          # 最大40点（20回で満点）
        a_topic = min(unique_topics / 10 * 20, 20)      # 最大20点（10トピックで満点）
        score_knowledge = a_doc + a_conv + a_topic      # 0-100

        # 軸B：応答精度スコア（0-100）
        if feedback_count > 0:
            positive_rate = positive_count / feedback_count
            score_accuracy = (positive_rate * 0.7 + recent_positive * 0.3) * 100
        else:
            score_accuracy = 50.0  # フィードバックなし → 中立50点

        # 軸C：個性スコア（0-100）
        c_profile = min(profile_comp, 40)               # 最大40点
        c_session = min(avg_session / 10 * 30, 30)      # 最大30点（10分で満点）
        c_tuning = min(tuning / 5 * 30, 30)             # 最大30点（5回で満点）
        score_personality = c_profile + c_session + c_tuning

        # 総合スコア（0-100）
        maturity_score = (
            score_knowledge * 0.5 +
            score_accuracy * 0.3 +
            score_personality * 0.2
        )

        # レベル変換（1-10）
        if maturity_score < 10:
            level = 1
        elif maturity_score < 20:
            level = 2
        elif maturity_score < 30:
            level = 3
        elif maturity_score < 40:
            level = 4
        elif maturity_score < 50:
            level = 5
        elif maturity_score < 60:
            level = 6
        elif maturity_score < 70:
            level = 7
        elif maturity_score < 80:
            level = 8
        elif maturity_score < 90:
            level = 9
        else:
            level = 10

        conn.run("""
            UPDATE persona_growth
            SET score_knowledge=:sk, score_accuracy=:sa, score_personality=:sp,
                maturity_score=:ms, maturity_level=:ml,
                updated_at=NOW()
            WHERE persona_id=:persona_id AND user_id=:user_id AND app_type=:app_type
        """, persona_id=persona_id, user_id=user_id, app_type=app_type,
             sk=round(score_knowledge, 2), sa=round(score_accuracy, 2),
             sp=round(score_personality, 2), ms=round(maturity_score, 2), ml=level)

        return {"maturity_score": maturity_score, "maturity_level": level}
    finally:
        conn.close()


def get_growth_record(persona_id, user_id, app_type='meeting'):
    """成熟度レコードを取得"""
    conn = get_connection()
    try:
        rows = conn.run("""
            SELECT persona_id, user_id, app_type,
                   score_knowledge, score_accuracy, score_personality,
                   maturity_score, maturity_level,
                   doc_token_count, conversation_count, unique_topic_count,
                   feedback_count, positive_count, recent_positive_rate,
                   profile_completeness, avg_session_length, tuning_count,
                   updated_at
            FROM persona_growth
            WHERE persona_id=:persona_id AND user_id=:user_id AND app_type=:app_type
        """, persona_id=persona_id, user_id=user_id, app_type=app_type)
        if not rows:
            return None
        r = rows[0]
        return {
            "persona_id": r[0], "user_id": r[1], "app_type": r[2],
            "score_knowledge": r[3], "score_accuracy": r[4], "score_personality": r[5],
            "maturity_score": r[6], "maturity_level": r[7],
            "doc_token_count": r[8], "conversation_count": r[9], "unique_topic_count": r[10],
            "feedback_count": r[11], "positive_count": r[12], "recent_positive_rate": r[13],
            "profile_completeness": r[14], "avg_session_length": r[15], "tuning_count": r[16],
            "updated_at": str(r[17]) if r[17] else None
        }
    finally:
        conn.close()


def update_growth_c_axis(persona_id, user_id, profile_completeness=None,
                          avg_session_minutes=None, increment_tuning=False,
                          app_type='meeting'):
    """C軸（個性スコア）の各要素を更新する"""
    conn = get_connection()
    try:
        parts = []
        params = dict(persona_id=persona_id, user_id=user_id, app_type=app_type)
        if profile_completeness is not None:
            parts.append("profile_completeness = :pc")
            params['pc'] = round(profile_completeness, 2)
        if avg_session_minutes is not None:
            rows = conn.run("""
                SELECT avg_session_length, conversation_count FROM persona_growth
                WHERE persona_id=:persona_id AND user_id=:user_id AND app_type=:app_type
            """, persona_id=persona_id, user_id=user_id, app_type=app_type)
            if rows:
                old_avg = rows[0][0] or 0.0
                old_count = max(rows[0][1] or 1, 1)
                new_avg = (old_avg * (old_count - 1) + avg_session_minutes) / old_count
                parts.append("avg_session_length = :asl")
                params['asl'] = round(new_avg, 2)
        if increment_tuning:
            parts.append("tuning_count = tuning_count + 1")
        if not parts:
            return
        parts.append("updated_at = NOW()")
        conn.run(
            f"UPDATE persona_growth SET {', '.join(parts)} "
            f"WHERE persona_id=:persona_id AND user_id=:user_id AND app_type=:app_type",
            **params
        )
    finally:
        conn.close()


# ===== フィードバック保存 =====

def save_feedback_record(persona_id, user_id, session_id, rating, detail_category, correct_response, app_type='meeting'):
    """フィードバックをpersona_feedbackに保存し、growthのスコアを更新"""
    conn = get_connection()
    try:
        conn.run("""
            INSERT INTO persona_feedback
                (persona_id, user_id, session_id, rating, detail_category, correct_response)
            VALUES
                (:persona_id, :user_id, :session_id, :rating, :detail_category, :correct_response)
        """, persona_id=persona_id, user_id=user_id, session_id=session_id,
             rating=rating, detail_category=detail_category,
             correct_response=encrypt_value(conn, correct_response))

        # persona_growthのfeedback_count・positive_countを更新
        conn.run("""
            INSERT INTO persona_growth (persona_id, user_id, app_type, feedback_count, positive_count)
            VALUES (:persona_id, :user_id, :app_type, 1, :pos)
            ON CONFLICT (persona_id, user_id, app_type)
            DO UPDATE SET
                feedback_count = persona_growth.feedback_count + 1,
                positive_count = persona_growth.positive_count + :pos,
                updated_at = NOW()
        """, persona_id=persona_id, user_id=user_id, app_type=app_type,
             pos=1 if rating else 0)

        # 直近20件のpositive_rateを計算して更新
        rows = conn.run("""
            SELECT rating FROM persona_feedback
            WHERE persona_id=:persona_id AND user_id=:user_id
            ORDER BY created_at DESC LIMIT 20
        """, persona_id=persona_id, user_id=user_id)
        if rows:
            recent_positive = sum(1 for r in rows if r[0]) / len(rows)
            conn.run("""
                UPDATE persona_growth SET recent_positive_rate=:rate, updated_at=NOW()
                WHERE persona_id=:persona_id AND user_id=:user_id AND app_type=:app_type
            """, persona_id=persona_id, user_id=user_id, app_type=app_type,
                 rate=round(recent_positive, 3))
    finally:
        conn.close()


# ===== 危機キーワード取得（5分キャッシュ）=====

def get_crisis_keywords():
    """アクティブな危機キーワード一覧を取得（5分キャッシュ）"""
    import time
    now = time.time()
    cache = get_crisis_keywords._cache
    if cache['data'] is not None and now - cache['ts'] < 300:
        return cache['data']
    conn = get_connection()
    try:
        rows = conn.run(
            "SELECT keyword FROM crisis_keywords WHERE is_active = TRUE"
        )
        result = [r[0] for r in rows]
        cache['data'] = result
        cache['ts'] = now
        return result
    finally:
        conn.close()

get_crisis_keywords._cache = {'data': None, 'ts': 0}


def set_earlybird_and_billing_anchor(user_id, is_earlybird, billing_anchor_day):
    """Checkout完了時にis_earlybird・billing_anchor_dayをセットする（初回登録時のみ呼び出す）"""
    conn = get_connection()
    try:
        conn.run(
            "UPDATE users SET is_earlybird=:eb, billing_anchor_day=:bad WHERE id=:uid",
            eb=is_earlybird, bad=billing_anchor_day, uid=user_id
        )
        affected = conn.row_count
        print(f"[DB][set_earlybird] UPDATE完了 rows_affected={affected} user_id={user_id} is_earlybird={is_earlybird} billing_anchor_day={billing_anchor_day}")
    except Exception as e:
        conn.close()
        raise RuntimeError(f"set_earlybird_and_billing_anchor failed (user={user_id}): {e}") from e
    conn.close()


def count_earlybird_users():
    """先着100名判定用：現在のアーリーバード会員数（standard/pro）をカウント"""
    conn = get_connection()
    try:
        rows = conn.run(
            "SELECT COUNT(*) FROM users WHERE is_earlybird=TRUE AND plan IN ('standard','pro')"
        )
        return rows[0][0] if rows else 0
    finally:
        conn.close()


def reset_monthly_meeting_count(user_id):
    """standardプラン：Stripe請求日基準でmonthly_meeting_countを0にリセットする"""
    conn = get_connection()
    try:
        conn.run(
            "UPDATE users SET monthly_meeting_count=0 WHERE id=:uid",
            uid=user_id
        )
        affected = conn.row_count
        print(f"[DB][reset_monthly] UPDATE完了 rows_affected={affected} user_id={user_id}")
    except Exception as e:
        conn.close()
        raise RuntimeError(f"reset_monthly_meeting_count failed (user={user_id}): {e}") from e
    conn.close()


def set_standard_plan(user_id, stripe_customer_id):
    """standardプラン契約完了時にplan・stripe_customer_idをセットする"""
    conn = get_connection()
    try:
        conn.run(
            "UPDATE users SET plan=:plan, stripe_customer_id=:cid WHERE id=:uid",
            plan='standard', cid=stripe_customer_id, uid=user_id
        )
        affected = conn.row_count
        print(f"[DB][set_standard_plan] UPDATE完了 rows_affected={affected} user_id={user_id} cid={stripe_customer_id!r}")
    except Exception as e:
        conn.close()
        raise RuntimeError(f"set_standard_plan failed (user={user_id}): {e}") from e
    conn.close()
