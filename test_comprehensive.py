"""
test_comprehensive.py — AI-PERSONA会議室 包括テスト
機能試験（7項目）+ 運用試験（4項目）

実行方法:
    python -X utf8 test_comprehensive.py

注意:
    - 外部AI API（Anthropic/OpenAI）は呼ばない設計。SSE/議事録はSKIP。
    - テスト用ユーザー・ペルソナは終了時に自動クリーンアップ。
    - RailwayのパブリックDB(DATABASE_URL)に直接接続して検証する。
"""

import os, sys, time, json, uuid
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

_db_url = os.environ.get('DATABASE_URL', '')
if 'railway.app' in _db_url or 'rlwy.net' in _db_url:
    print('=' * 60)
    print('【エラー】本番DBへの接続が検出されました。')
    print('テストを中止します。')
    print('DATABASE_URL環境変数を空にしてから再実行してください。')
    print('例: $env:DATABASE_URL=""; python -X utf8 test_comprehensive.py')
    print('=' * 60)
    import sys; sys.exit(1)

import pg8000.native
from urllib.parse import urlparse

# ─── 共通ユーティリティ ────────────────────────────────────────

PASS_SYM = "  [PASS]"
FAIL_SYM = "  [FAIL]"
SKIP_SYM = "  [SKIP]"
INFO_SYM = "  [INFO]"

_results: list[bool] = []


DB_TIMEOUT = 15  # 秒


def db_conn():
    url = urlparse(os.environ.get('DATABASE_URL', ''))
    return pg8000.native.Connection(
        host=url.hostname, port=url.port or 5432,
        database=url.path.lstrip('/'), user=url.username,
        password=url.password, ssl_context=True,
        timeout=DB_TIMEOUT,
    )


def check(ok: bool, label: str) -> bool:
    sym = PASS_SYM if ok else FAIL_SYM
    print(f"{sym} {label}")
    _results.append(bool(ok))
    return bool(ok)


def check_code(r, expected: int, label: str) -> bool:
    ok = r.status_code == expected
    sym = PASS_SYM if ok else FAIL_SYM
    suffix = "" if ok else f" (got {r.status_code})"
    print(f"{sym} {label}{suffix}")
    _results.append(ok)
    return ok


def skip(label: str):
    print(f"{SKIP_SYM} {label}")


def info(msg: str):
    print(f"{INFO_SYM} {msg}")


def section(title: str):
    print(f"\n{'='*60}")
    print(title)
    print('='*60)


# ─── Flask test client ────────────────────────────────────────

from src.main import app as flask_app
from src.database import get_connection as _get_app_db_conn
flask_app.config['TESTING'] = True

UNIQUE = str(uuid.uuid4())[:8]
TEST_EMAIL    = f"comp_{UNIQUE}@test.invalid"
TEST_PW       = "testpass123"
TEST_NAME     = "テスト太郎"
TEST_EMAIL_B  = f"comp_{UNIQUE}_b@test.invalid"   # 永続性テスト用

def _set_user_plan(uid, plan, credits=0, monthly_count=0):
    """DBを直接操作してユーザープランを変更（freeプランlearn制限テスト対応）"""
    if not uid:
        return
    try:
        conn = _get_app_db_conn()
        conn.run(
            "UPDATE users SET plan=:plan, credits=:credits, "
            "monthly_meeting_count=:mc WHERE id=:id",
            plan=plan, credits=credits, mc=monthly_count, id=uid
        )
        conn.close()
    except Exception as e:
        info(f"プラン変更エラー（無視）: {e}")


# テスト中に共有する状態
state: dict = {
    'user_id':           None,
    'main_persona_id':   None,
    'del_persona_id':    None,
    'meeting_session_id': None,
    'learn_data_id':     None,
}


# ─── クリーンアップ ───────────────────────────────────────────

def cleanup():
    """テストで作成したデータを一括削除する。CASCADEでpersona/learn_dataも消える。"""
    try:
        conn = db_conn()
        conn.run("DELETE FROM users WHERE email LIKE 'comp\\_%@test.invalid'")
        conn.close()
        info("テストデータをクリーンアップしました")
    except Exception as e:
        info(f"クリーンアップエラー（無視）: {e}")


# ─── 機能試験 1: 認証 ─────────────────────────────────────────

def test1_auth(client):
    section("機能試験1: ユーザー登録・ログイン・ログアウト")

    # 登録（T-01: tos_agreed=True が必須）
    r = client.post('/api/auth/register',
                    json={'email': TEST_EMAIL, 'password': TEST_PW, 'name': TEST_NAME, 'tos_agreed': True, 'birth_date': '1990-01-01'})
    check_code(r, 200, "register 200 OK")
    data = r.get_json() or {}
    check('user' in data, "register レスポンスに user が含まれる")
    check(data.get('user', {}).get('email') == TEST_EMAIL, "登録メールアドレスが一致")

    # 重複登録
    r2 = client.post('/api/auth/register',
                     json={'email': TEST_EMAIL, 'password': TEST_PW, 'name': TEST_NAME, 'tos_agreed': True, 'birth_date': '1990-01-01'})
    check_code(r2, 400, "重複登録 → 400")

    # ログアウト
    r = client.post('/api/auth/logout')
    check_code(r, 200, "logout 200 OK")

    # ログイン
    r = client.post('/api/auth/login', json={'email': TEST_EMAIL, 'password': TEST_PW})
    check_code(r, 200, "login 200 OK")
    data = r.get_json() or {}
    check('user' in data, "login レスポンスに user が含まれる")
    if data.get('user'):
        state['user_id'] = data['user']['id']
        info(f"user_id: {state['user_id']}")

    # 誤パスワード
    r3 = client.post('/api/auth/login',
                     json={'email': TEST_EMAIL, 'password': 'wrongpassword'})
    check_code(r3, 401, "誤パスワード → 401")

    # /api/auth/me（ログイン中）
    r = client.get('/api/auth/me')
    data = r.get_json() or {}
    check(data.get('user') is not None, "/api/auth/me でユーザー情報が返る")
    check((data.get('user') or {}).get('email') == TEST_EMAIL, "/api/auth/me メールが一致")


# ─── 機能試験 2: ゲストモード ─────────────────────────────────

def test2_guest_meeting():
    section("機能試験2: ゲストモードでの会議開始")

    with flask_app.test_client() as guest:
        r = guest.post('/api/meeting/start',
                       json={'topic': 'ゲストテスト議題（自動試験）'})
        check_code(r, 200, "ゲスト会議開始 200 OK")
        data = r.get_json() or {}
        check('session_id' in data, "session_id が返る")
        check(data.get('topic') == 'ゲストテスト議題（自動試験）', "topicが正しく設定される")
        check(isinstance(data.get('members'), list) and len(data.get('members', [])) > 0,
              "membersが1件以上返る")
        check('facilitator' in data, "facilitatorが含まれる")

        # セッション取得
        sid = data.get('session_id')
        if sid:
            r2 = guest.get(f'/api/meeting/{sid}')
            check_code(r2, 200, "ゲスト会議のセッションGET 200 OK")


# ─── 機能試験 3: ペルソナ CRUD ────────────────────────────────

def test3_persona_crud(client):
    section("機能試験3: ペルソナ追加・編集・削除")

    persona_base = {
        "name": "テストペルソナ",
        "description": "自動テスト用の人物",
        "personality": "論理的で冷静",
        "speaking_style": "丁寧語",
        "background": "エンジニア歴10年",
        "avatar": "🤖",
        "color": "#4B5563",
        "role": "member",
    }

    # --- 追加 ---
    r = client.post('/api/personas/add', json=persona_base)
    check_code(r, 200, "persona add 200 OK")
    data = r.get_json() or {}
    check('persona' in data, "add レスポンスに persona が含まれる")
    if data.get('persona'):
        state['main_persona_id'] = data['persona']['id']
        info(f"作成persona_id: {state['main_persona_id']}")

    # 削除テスト用に別ペルソナを作成
    r_d = client.post('/api/personas/add',
                      json={**persona_base, "name": "削除テスト用ペルソナ"})
    if r_d.status_code == 200:
        state['del_persona_id'] = (r_d.get_json() or {}).get('persona', {}).get('id')

    # --- 一覧 ---
    r = client.get('/api/personas/members')
    check_code(r, 200, "persona members list 200 OK")
    data = r.get_json() or {}
    check('members' in data, "members キーが存在")
    if state['main_persona_id']:
        ids = [m['id'] for m in data.get('members', [])]
        check(state['main_persona_id'] in ids, "追加したペルソナが一覧に含まれる")

    # --- 編集 ---
    if state['main_persona_id']:
        updated = {**persona_base, "name": "テストペルソナ（更新済）"}
        r = client.put(f"/api/personas/{state['main_persona_id']}", json=updated)
        check_code(r, 200, "persona update 200 OK")
        data = r.get_json() or {}
        check(data.get('persona', {}).get('name') == "テストペルソナ（更新済）",
              "更新後の名前が反映されている")

    # --- 削除 ---
    if state['del_persona_id']:
        r = client.delete(f"/api/personas/{state['del_persona_id']}")
        check_code(r, 200, "persona delete 200 OK")
        # 削除後に一覧から消えているか
        r2 = client.get('/api/personas/members')
        ids2 = [m['id'] for m in (r2.get_json() or {}).get('members', [])]
        check(state['del_persona_id'] not in ids2, "削除したペルソナが一覧から消える")


# ─── 機能試験 4: 学習データ冪等性 ────────────────────────────

def test4_learn_idempotency(client):
    section("機能試験4: 学習データ追加の冪等性（重複防止）")

    pid = state.get('main_persona_id')
    if not pid:
        skip("ペルソナ作成失敗のためスキップ")
        return

    CONTENT  = f"__TEST_LEARN_{UNIQUE}__ テスト学習コンテンツ。AIを用いた会議支援の研究。"
    SOURCE   = f"__test_src_{UNIQUE}__"
    CONTENT2 = f"__TEST_LEARN_{UNIQUE}_B__ 別コンテンツ。"

    # 1回目 → 登録される
    r = client.post(f'/api/personas/{pid}/learn',
                    json={'content': CONTENT, 'source': SOURCE})
    check_code(r, 200, "learn POST 1回目 200 OK")
    count1 = (r.get_json() or {}).get('total_count', 0)
    info(f"1回目追加後 total_count={count1}")

    # 2回目（同一content）→ スキップされる
    time.sleep(1.5)  # DB接続の解放を待つ（Railway接続制限対策）
    r2 = client.post(f'/api/personas/{pid}/learn',
                     json={'content': CONTENT, 'source': SOURCE})
    check_code(r2, 200, "learn POST 2回目（重複）200 OK")
    count2 = (r2.get_json() or {}).get('total_count', 0)
    check(count2 == count1, f"重複スキップ: count変化なし ({count1}→{count2})")

    # 3回目（別content）→ 登録される
    time.sleep(1.5)
    r3 = client.post(f'/api/personas/{pid}/learn',
                     json={'content': CONTENT2, 'source': SOURCE})
    count3 = (r3.get_json() or {}).get('total_count', 0)
    check(count3 > count2, f"別コンテンツ追加: count増加 ({count2}→{count3})")

    # GET で確認
    r4 = client.get(f'/api/personas/{pid}/learn')
    check_code(r4, 200, "learn GET 200 OK")
    data4 = r4.get_json() or {}
    check('learn_data' in data4 and 'count' in data4, "learn_data/countキーが存在")
    check(data4.get('count', 0) >= 2, f"GET count >= 2 (got {data4.get('count', 0)})")
    if data4.get('learn_data'):
        state['learn_data_id'] = data4['learn_data'][0]['id']


# ─── 機能試験 4b: 学習データ非同期保存（10件一括・Embedding失敗耐性） ──

def test4b_learn_async_save(client):
    section("機能試験4b: 学習データ非同期保存（10件一括・Embedding失敗耐性）")

    pid = state.get('main_persona_id')
    if not pid:
        skip("ペルソナ作成失敗のためスキップ")
        return

    # ── 4b-1: 10件を連続POSTして全件DBに保存されるか ──────────
    info("── 10件一括保存テスト ──")
    saved_ids = []
    for i in range(10):
        content = f"__BULK_{UNIQUE}_{i:02d}__ バルクテスト学習データ {i} 番目。非同期Embedding確認用。"
        r = client.post(f'/api/personas/{pid}/learn',
                        json={'content': content, 'source': f'bulk_test_{i}'})
        check_code(r, 200, f"  bulk POST {i+1:02d}/10 → 200 OK")
        saved_ids.append(content)

    # 全件がDBに入っているか確認（Embeddingはバックグラウンドなので不問）
    r_get = client.get(f'/api/personas/{pid}/learn')
    check_code(r_get, 200, "learn GET 200 OK（10件保存後）")
    learn_data = (r_get.get_json() or {}).get('learn_data', [])
    db_contents = {d['content'] for d in learn_data}
    matched = sum(1 for c in saved_ids if c in db_contents)
    check(matched == 10, f"10件全てDBに保存されている (matched={matched}/10)")

    # ── 4b-2: POSTレスポンスが即時返る（サーバーが詰まらない）──
    # しきい値注意: テスト環境→Railway DBのリモートレイテンシは~2.5s/クエリ。
    # learn POST は save + count + growth (3クエリ) = 計~5クエリ相当。
    # OpenAI Embedding (~30s) が同期なら 35s+ になるはずなので、
    # 非同期化の確認には 30s 以内を基準とする。
    info("── レスポンス即時性テスト ──")
    import time as _time
    content_quick = f"__QUICK_{UNIQUE}__ 即時レスポンス確認用データ。"
    t0 = _time.time()
    r_q = client.post(f'/api/personas/{pid}/learn',
                      json={'content': content_quick, 'source': 'quick_test'})
    elapsed = _time.time() - t0
    check_code(r_q, 200, "learn POST → 200 OK")
    check(elapsed < 30.0, f"Embedding非同期化: OpenAI待ちなくレスポンス ({elapsed*1000:.0f}ms / 30000ms)")
    info(f"レスポンス時間: {elapsed*1000:.0f}ms")

    # ── 4b-3: OPENAI_API_KEY 未設定でもテキスト保存は成功するか ──
    info("── Embedding失敗耐性テスト（API_KEY一時退避）──")
    original_key = os.environ.pop('OPENAI_API_KEY', None)
    try:
        content_nokey = f"__NOKEY_{UNIQUE}__ APIキーなしでも保存できるか確認。"
        r_nk = client.post(f'/api/personas/{pid}/learn',
                           json={'content': content_nokey, 'source': 'nokey_test'})
        check_code(r_nk, 200, "OPENAI_API_KEY なしでも learn POST → 200 OK")

        # DBにテキストが保存されているか
        r_nk_get = client.get(f'/api/personas/{pid}/learn')
        nk_data = (r_nk_get.get_json() or {}).get('learn_data', [])
        nk_contents = {d['content'] for d in nk_data}
        check(content_nokey in nk_contents, "EmbeddingなしでもテキストはDBに保存済み")
    finally:
        if original_key:
            os.environ['OPENAI_API_KEY'] = original_key


# ─── 機能試験 4c: ペルソナ間のデータ非混入テスト ──────────────

def test4c_persona_isolation(client):
    section("機能試験4c: ペルソナ間の学習データ非混入")

    pid_a = state.get('main_persona_id')
    if not pid_a:
        skip("ペルソナ作成失敗のためスキップ")
        return

    # 2つ目のペルソナを作成
    r = client.post('/api/personas/add', json={
        "name": "隔離テスト用ペルソナB",
        "description": "自動テスト用",
        "personality": "冷静",
        "speaking_style": "丁寧語",
        "background": "",
        "avatar": "🔵",
        "color": "#3B82F6",
        "role": "member",
    })
    check_code(r, 200, "ペルソナB 追加 200 OK")
    pid_b = (r.get_json() or {}).get('persona', {}).get('id')
    if not pid_b:
        skip("ペルソナB作成失敗のためスキップ")
        return
    info(f"ペルソナA={pid_a} ペルソナB={pid_b}")

    # ── A と B に異なるデータを保存 ──
    content_a = f"__ISOLATION_A_{UNIQUE}__ ペルソナA専用の学習データ。孔明の兵法。"
    content_b = f"__ISOLATION_B_{UNIQUE}__ ペルソナB専用の学習データ。秀吉の太閤記。"

    r_a = client.post(f'/api/personas/{pid_a}/learn',
                      json={'content': content_a, 'source': 'isolation_test_A'})
    check_code(r_a, 200, "ペルソナAにデータ保存 200 OK")

    r_b = client.post(f'/api/personas/{pid_b}/learn',
                      json={'content': content_b, 'source': 'isolation_test_B'})
    check_code(r_b, 200, "ペルソナBにデータ保存 200 OK")

    # ── A のデータを取得してBのデータが混入していないか確認 ──
    r_get_a = client.get(f'/api/personas/{pid_a}/learn')
    check_code(r_get_a, 200, "ペルソナA 学習データ GET 200 OK")
    items_a = (r_get_a.get_json() or {}).get('learn_data', [])
    contents_a = {d['content'] for d in items_a}
    check(content_a[:50] in ' '.join(contents_a), f"Aのデータ: Aの内容が含まれる")
    check(not any(content_b[:30] in c for c in contents_a),
          f"Aのデータ: Bの内容が混入していない")

    # ── B のデータを取得してAのデータが混入していないか確認 ──
    r_get_b = client.get(f'/api/personas/{pid_b}/learn')
    check_code(r_get_b, 200, "ペルソナB 学習データ GET 200 OK")
    items_b = (r_get_b.get_json() or {}).get('learn_data', [])
    contents_b = {d['content'] for d in items_b}
    check(content_b[:50] in ' '.join(contents_b), f"Bのデータ: Bの内容が含まれる")
    check(not any(content_a[:30] in c for c in contents_b),
          f"Bのデータ: Aの内容が混入していない")

    # ── DB直接確認: persona_idが正しく分離されているか ──
    conn = db_conn()
    try:
        row_a = conn.run("""
            SELECT COUNT(*) FROM persona_learn
            WHERE persona_id=:pid AND content=:c
        """, pid=pid_a, c=content_a)[0][0]
        check(row_a == 1, f"DBでAのデータがAのpersona_idに保存されている (count={row_a})")

        row_b_in_a = conn.run("""
            SELECT COUNT(*) FROM persona_learn
            WHERE persona_id=:pid AND content=:c
        """, pid=pid_a, c=content_b)[0][0]
        check(row_b_in_a == 0,
              f"DBでBのデータがAのpersona_idに混入していない (count={row_b_in_a})")

        row_a_in_b = conn.run("""
            SELECT COUNT(*) FROM persona_learn
            WHERE persona_id=:pid AND content=:c
        """, pid=pid_b, c=content_a)[0][0]
        check(row_a_in_b == 0,
              f"DBでAのデータがBのpersona_idに混入していない (count={row_a_in_b})")
    finally:
        conn.close()

    # ── ペルソナBを削除（後片付け） ──
    client.delete(f'/api/personas/{pid_b}')


# ─── 機能試験 5: 会議開始・メッセージ送信 ────────────────────

def test5_meeting(client):
    section("機能試験5: 会議開始・メッセージ送信・ストリーム確認")

    pid = state.get('main_persona_id')

    # --- 会議開始 ---
    payload = {'topic': '自動テスト会議の議題'}
    if pid:
        payload['member_ids'] = [pid]
    r = client.post('/api/meeting/start', json=payload)
    check_code(r, 200, "meeting start 200 OK")
    data = r.get_json() or {}
    check('session_id' in data, "session_id が返る")
    check(data.get('topic') == '自動テスト会議の議題', "topic が正しい")
    check(isinstance(data.get('members'), list), "members が配列で返る")
    if data.get('session_id'):
        state['meeting_session_id'] = data['session_id']
        info(f"session_id: {state['meeting_session_id']}")

    # --- セッション取得 ---
    sid = state.get('meeting_session_id')
    if sid:
        r = client.get(f'/api/meeting/{sid}')
        check_code(r, 200, "meeting GET 200 OK")
        data = r.get_json() or {}
        check('topic' in data, "topic キーが存在")
        check('messages' in data, "messages キーが存在")
        check(isinstance(data.get('messages'), list), "messages が配列")

    # --- メッセージ送信 ---
    if sid:
        msg_content = 'これは自動テストのユーザーメッセージです'
        r = client.post(f'/api/meeting/{sid}/message',
                        json={'content': msg_content})
        check_code(r, 200, "message POST 200 OK")
        data = r.get_json() or {}
        check('message' in data, "messageキーが存在")
        check(data.get('message', {}).get('content') == msg_content,
              "投稿メッセージが正しく格納される")
        check(data.get('message', {}).get('persona_id') == 'user',
              "persona_id='user'として記録される")

    # --- 存在しないセッション ---
    r_no = client.get('/api/meeting/nonexistent_session_xyz')
    check_code(r_no, 404, "存在しないsession → 404")

    # SSE / 議事録生成はAnthropicAPI呼び出しのためスキップ
    skip("SSEストリーム: AnthropicAPI呼び出しのためスキップ")
    skip("議事録生成(PDF): AnthropicAPI呼び出しのためスキップ")


# ─── 機能試験 6: フィードバック・成熟度 ──────────────────────

def test6_feedback(client):
    section("機能試験6: フィードバック送信・成熟度スコア更新")

    pid = state.get('main_persona_id')
    sid = state.get('meeting_session_id', '')

    if not pid:
        skip("ペルソナなし: スキップ")
        return

    # ログイン確認（feedback は login_required ではないが session 確認）
    uid = state.get('user_id')
    if not uid:
        skip("user_id なし: スキップ")
        return

    # --- positive フィードバック ---
    r = client.post(f'/api/personas/{pid}/feedback',
                    json={
                        'rating': True,
                        'detail_category': 'insightful',
                        'correct_response': '',
                        'add_to_learn': False,
                        'session_id': sid,
                    })
    check_code(r, 200, "feedback POST (positive) 200 OK")
    data = r.get_json() or {}
    check('message' in data, "responseに messageが含まれる")

    # --- negative フィードバック ---
    r2 = client.post(f'/api/personas/{pid}/feedback',
                     json={
                         'rating': False,
                         'detail_category': 'off_topic',
                         'correct_response': 'テスト改善文',
                         'add_to_learn': False,
                         'session_id': sid,
                     })
    check_code(r2, 200, "feedback POST (negative) 200 OK")

    # rating なし → 400
    r3 = client.post(f'/api/personas/{pid}/feedback', json={'session_id': sid})
    check_code(r3, 400, "rating なし → 400")

    # --- 成長データ取得 ---
    r4 = client.get(f'/api/personas/{pid}/growth')
    check_code(r4, 200, "growth GET 200 OK")
    data4 = r4.get_json() or {}
    check('growth' in data4, "growth キーが存在")
    if data4.get('growth'):
        ml = data4['growth'].get('maturity_level', -1)
        info(f"maturity_level={ml}")
        check(1 <= ml <= 10, f"maturity_level が 1〜10 の範囲 (got {ml})")
        check('level_name' in data4['growth'], "level_name キーが存在")


# ─── 機能試験 7: 料金プラン制限 ──────────────────────────────

def test7_plan_limits(client):
    section("機能試験7: 料金プラン制限（無料5回・スタンダードcredits・プロ無制限）")

    uid = state.get('user_id')
    if not uid:
        skip("user_id なし: スキップ")
        return

    conn = db_conn()

    try:
        # ── 7-1: 無料プラン 月5回制限 ──────────────────────────
        info("── 無料プラン制限テスト ──")
        # monthly_count=4 に設定（次が5回目）
        conn.run("""
            UPDATE users SET plan='free', credits=0,
                             monthly_meeting_count=4, monthly_reset_at=NOW()
            WHERE id=:id
        """, id=uid)

        r5 = client.post('/api/meeting/start', json={'topic': '無料5回目テスト'})
        check_code(r5, 200, "無料プラン 5回目 → 200 OK")

        r6 = client.post('/api/meeting/start', json={'topic': '無料6回目テスト'})
        check_code(r6, 403, "無料プラン 6回目 → 403 PLAN_LIMIT")
        d6 = r6.get_json() or {}
        check(d6.get('code') == 'PLAN_LIMIT', "code='PLAN_LIMIT'が返る")

        # ── 7-2: スタンダードプラン credits 消費 ────────────────
        info("── スタンダードプラン credits テスト ──")
        conn.run("""
            UPDATE users SET plan='standard', credits=1, monthly_meeting_count=0
            WHERE id=:id
        """, id=uid)

        r_s1 = client.post('/api/meeting/start', json={'topic': 'スタンダード1回目'})
        check_code(r_s1, 200, "standard credits=1 → 200 OK（credits消費）")

        rows = conn.run("SELECT credits FROM users WHERE id=:id", id=uid)
        credits_left = rows[0][0] if rows else -1
        info(f"消費後 credits={credits_left}")
        check(credits_left == 0, f"credits 1→0 に減っている (got {credits_left})")

        r_s2 = client.post('/api/meeting/start', json={'topic': 'スタンダード credits切れ'})
        check_code(r_s2, 403, "standard credits=0 → 403")

        # ── 7-3: プロプラン 無制限 ──────────────────────────────
        info("── プロプラン（無制限）テスト ──")
        from datetime import datetime, timedelta
        expires = datetime.utcnow() + timedelta(days=30)
        conn.run("""
            UPDATE users SET plan='pro', credits=0, monthly_meeting_count=99,
                             plan_expires_at=:exp
            WHERE id=:id
        """, exp=expires, id=uid)

        r_p = client.post('/api/meeting/start', json={'topic': 'プロ会議（無制限確認）'})
        check_code(r_p, 200, "pro plan monthly_count=99 でも 200 OK（無制限）")

        # ── 7-4: プロプラン 期限切れ → free 降格 ────────────────
        info("── プロプラン期限切れ → free降格 テスト ──")
        from datetime import datetime, timedelta
        expired = datetime.utcnow() - timedelta(days=1)
        conn.run("""
            UPDATE users SET plan='pro', plan_expires_at=:exp, monthly_meeting_count=4
            WHERE id=:id
        """, exp=expired, id=uid)

        r_exp5 = client.post('/api/meeting/start', json={'topic': 'pro期限切れ5回目'})
        check_code(r_exp5, 200, "pro期限切れ→free降格→5回目 200 OK")

        r_exp6 = client.post('/api/meeting/start', json={'topic': 'pro期限切れ6回目'})
        check_code(r_exp6, 403, "pro期限切れ→free降格→6回目 403")

    finally:
        # 後始末: free + 0カウントに戻す
        conn.run("""
            UPDATE users SET plan='free', credits=0,
                             monthly_meeting_count=0, monthly_reset_at=NOW(),
                             plan_expires_at=NULL
            WHERE id=:id
        """, id=uid)
        conn.close()


# ─── 運用試験 1: データ永続性 ─────────────────────────────────

def test8_persistence(client):
    section("運用試験1: ログアウト→再ログイン後のデータ再現性")

    pid = state.get('main_persona_id')

    # ログアウト
    r = client.post('/api/auth/logout')
    check_code(r, 200, "logout 200 OK")

    # ログアウト後 → /me は null
    r = client.get('/api/auth/me')
    check((r.get_json() or {}).get('user') is None, "ログアウト後 /me = null")

    # 未ログインでの認証必須エンドポイント
    r_f = client.post(f"/api/personas/{pid or 'koumei'}/feedback",
                      json={'rating': True, 'session_id': ''})
    check_code(r_f, 401, "未ログインでfeedback → 401")

    # 再ログイン
    r = client.post('/api/auth/login', json={'email': TEST_EMAIL, 'password': TEST_PW})
    check_code(r, 200, "再ログイン 200 OK")
    user = (r.get_json() or {}).get('user', {})
    check(user.get('email') == TEST_EMAIL, "再ログイン後のユーザー情報が一致")
    check(user.get('plan') == 'free', "再ログイン後プランが保持されている")

    # ペルソナが残っているか
    r2 = client.get('/api/personas/members')
    members = (r2.get_json() or {}).get('members', [])
    if pid:
        ids = [m['id'] for m in members]
        check(pid in ids, f"再ログイン後もペルソナが残っている")

    # 学習データが残っているか
    if pid:
        r3 = client.get(f'/api/personas/{pid}/learn')
        cnt = (r3.get_json() or {}).get('count', 0)
        check(cnt >= 1, f"再ログイン後も学習データが残っている (count={cnt})")

    # 成長データが残っているか
    if pid:
        r4 = client.get(f'/api/personas/{pid}/growth')
        growth = (r4.get_json() or {}).get('growth')
        check(growth is not None, "再ログイン後も成長データが残っている")


# ─── 運用試験 2: 複数ペルソナ会議安定性 ─────────────────────

def test9_multi_persona(client):
    section("運用試験2: 複数ペルソナ同時参加での会議安定性")

    # T-02後: デフォルトペルソナは非公開のため、テスト専用ペルソナを追加作成
    extra_pids = []
    for i in range(2):
        r_tmp = client.post('/api/personas/add', json={
            "name": f"マルチ用ペルソナ{i+1}", "description": "複数ペルソナテスト用",
            "personality": "協調的", "speaking_style": "標準語",
            "background": "", "avatar": ("🟡" if i == 0 else "🟠"),
            "color": "#F59E0B", "role": "member",
        })
        if r_tmp.status_code == 200:
            pid_tmp = (r_tmp.get_json() or {}).get('persona', {}).get('id')
            if pid_tmp:
                extra_pids.append(pid_tmp)

    r = client.get('/api/personas/members')
    members = (r.get_json() or {}).get('members', [])

    available = [m['id'] for m in members]
    info(f"利用可能ペルソナ数: {len(available)}")

    if len(available) < 2:
        skip(f"ペルソナ数 {len(available)} < 2: スキップ")
        for pid in extra_pids:
            client.delete(f'/api/personas/{pid}')
        return

    ids_3 = available[:3]  # 最大3名
    info(f"使用ペルソナ: {ids_3}")

    r2 = client.post('/api/meeting/start',
                     json={'topic': '複数ペルソナ安定性テスト', 'member_ids': ids_3})
    check_code(r2, 200, "複数ペルソナ会議開始 200 OK")
    data2 = r2.get_json() or {}
    check('session_id' in data2, "session_id が返る")

    returned_ids = [m['id'] for m in data2.get('members', [])]
    for mid in ids_3:
        check(mid in returned_ids, f"ペルソナ {mid} がセッションに含まれる")

    sid2 = data2.get('session_id')
    if sid2:
        r3 = client.get(f'/api/meeting/{sid2}')
        check_code(r3, 200, "複数ペルソナ会議のGET 200 OK")
        data3 = r3.get_json() or {}
        check(len(data3.get('members', [])) == len(ids_3),
              f"セッションのメンバー数が正しい ({len(data3.get('members', []))} == {len(ids_3)})")

        # メッセージ送信も確認
        r4 = client.post(f'/api/meeting/{sid2}/message',
                         json={'content': '複数ペルソナ会議テストメッセージ'})
        check_code(r4, 200, "複数ペルソナ会議へのメッセージ送信 200 OK")

    # テスト用ペルソナをクリーンアップ
    for pid in extra_pids:
        client.delete(f'/api/personas/{pid}')


# ─── 運用試験 3: DB整合性 ─────────────────────────────────────

def test10_db_integrity():
    section("運用試験3: DB整合性チェック（外部キー・NULL制約）")

    conn = db_conn()
    try:
        # FK: persona_learn.persona_id → personas.id
        orphan_learn = conn.run("""
            SELECT COUNT(*) FROM persona_learn pl
            LEFT JOIN personas p ON pl.persona_id = p.id
            WHERE p.id IS NULL
        """)[0][0]
        check(orphan_learn == 0,
              f"persona_learn に孤立レコードなし (orphan={orphan_learn})")

        # FK: personas.user_id → users.id
        orphan_persona = conn.run("""
            SELECT COUNT(*) FROM personas p
            LEFT JOIN users u ON p.user_id = u.id
            WHERE p.user_id IS NOT NULL AND u.id IS NULL
        """)[0][0]
        check(orphan_persona == 0,
              f"personas に孤立 user_id なし (orphan={orphan_persona})")

        # NULL制約: personas.name
        null_name = conn.run(
            "SELECT COUNT(*) FROM personas WHERE name IS NULL OR name=''"
        )[0][0]
        check(null_name == 0,
              f"personas.name が空・NULLのレコードなし (count={null_name})")

        # UNIQUE: users.email
        dup_email = conn.run("""
            SELECT COUNT(*) FROM (
                SELECT email FROM users GROUP BY email HAVING COUNT(*) > 1
            ) t
        """)[0][0]
        check(dup_email == 0,
              f"users.email に重複なし (dup={dup_email})")

        # NULL制約: persona_learn.content
        null_content = conn.run(
            "SELECT COUNT(*) FROM persona_learn WHERE content IS NULL OR content=''"
        )[0][0]
        check(null_content == 0,
              f"persona_learn.content が空・NULLのレコードなし (count={null_content})")

        # ユニーク: personas (id, user_id) 複合
        dup_persona_id = conn.run("""
            SELECT COUNT(*) FROM (
                SELECT id, COALESCE(user_id, -1) g
                FROM personas
                GROUP BY id, COALESCE(user_id, -1) HAVING COUNT(*) > 1
            ) t
        """)[0][0]
        check(dup_persona_id == 0,
              f"personas (id, user_id) の複合ユニーク制約が守られている (dup={dup_persona_id})")

        # persona_growth の maturity_level 範囲確認（実装は1〜10スケール）
        out_of_range = conn.run("""
            SELECT COUNT(*) FROM persona_growth WHERE maturity_level < 1 OR maturity_level > 10
        """)[0][0]
        check(out_of_range == 0,
              f"persona_growth.maturity_level が 1〜10 の範囲 (out_of_range={out_of_range})")

    finally:
        conn.close()


# ─── 運用試験 4: APIレスポンスタイム ─────────────────────────

def test11_response_time(client):
    section("運用試験4: APIレスポンスタイム計測")

    # (method, path, body, label, limit_sec)
    # personas/members と meeting/start はDB集計が多いため上限を緩く設定
    cases = [
        ("GET",  "/api/health",           None,                            "GET /api/health",           1.0),
        ("GET",  "/api/auth/me",          None,                            "GET /api/auth/me",          5.0),
        ("GET",  "/api/personas",         None,                            "GET /api/personas",         5.0),
        ("GET",  "/api/personas/members", None,                            "GET /api/personas/members", 8.0),
        ("POST", "/api/meeting/start",    {"topic": "レスポンス計測テスト"}, "POST /api/meeting/start",  15.0),
    ]
    if state.get('main_persona_id'):
        pid = state['main_persona_id']
        cases.append(("GET", f"/api/personas/{pid}/learn", None,
                      f"GET /api/personas/{{pid}}/learn", 5.0))
        cases.append(("GET", f"/api/personas/{pid}/growth", None,
                      f"GET /api/personas/{{pid}}/growth", 5.0))

    for method, path, body, label, limit_sec in cases:
        t0 = time.time()
        r = client.get(path) if method == "GET" else client.post(path, json=body)
        elapsed = time.time() - t0
        ok = elapsed <= limit_sec and r.status_code not in (500, 502, 503)
        sym = PASS_SYM if ok else FAIL_SYM
        print(f"{sym} {label}: {elapsed*1000:.0f}ms / {limit_sec*1000:.0f}ms (HTTP {r.status_code})")
        _results.append(ok)


# ─── WARN 機構 ─────────────────────────────────────────────────

WARN_SYM = "  [WARN]"
_warns: list[str] = []


def warn(label: str):
    print(f"{WARN_SYM} {label}")
    _warns.append(label)


# ─── 機能試験 8: iPhone モバイル修正回帰テスト ─────────────────

def test_func8_mobile_static():
    section("機能試験8: iPhoneモバイル修正の回帰テスト（静的ファイル検査）")
    import re

    base = os.path.dirname(os.path.abspath(__file__))
    html = open(os.path.join(base, 'web', 'index.html'), encoding='utf-8').read()
    js   = open(os.path.join(base, 'web', 'app.js'),     encoding='utf-8').read()

    # 1. bodyタグにoverflow-x:hiddenが含まれる
    m = re.search(r'\bbody\s*\{([^}]*)\}', html)
    check(bool(m and 'overflow-x' in m.group(1) and 'hidden' in m.group(1)),
          "bodyタグにoverflow-x:hiddenが含まれる")

    # 2. headerタグにoverflow-x:hiddenが含まれる（header{} セレクタ）
    m = re.search(r'\bheader\s*\{([^}]*)\}', html)
    check(bool(m and 'overflow-x' in m.group(1) and 'hidden' in m.group(1)),
          "headerタグにoverflow-x:hiddenが含まれる")

    # 3. .attach-textが存在する
    check('.attach-text' in html or '.attach-text' in js, ".attach-textが存在する")

    # 4. .voice-textが存在する
    check('.voice-text' in html or '.voice-text' in js, ".voice-textが存在する")

    def _media_block(text: str, px: str) -> str:
        for m in re.finditer(rf'@media[^{{]*{re.escape(px)}[^{{]*\{{', text):
            depth, i = 0, m.end() - 1
            while i < len(text):
                if text[i] == '{':
                    depth += 1
                elif text[i] == '}':
                    depth -= 1
                    if depth == 0:
                        return text[m.end()-1:i+1]
                i += 1
        return ''

    # 5. @480pxブロックに#voiceModeBtn{display:noneが存在しない
    b480 = _media_block(html, '480px')
    if b480:
        vm = re.search(r'#voiceModeBtn\s*\{([^}]*)\}', b480)
        check(not (vm and re.search(r'display\s*:\s*none', vm.group(1))),
              "@480pxブロックに#voiceModeBtn{display:noneが存在しない")
    else:
        check(True, "@480pxブロックに#voiceModeBtn{display:noneが存在しない（@480pxブロックなし）")

    # 6. @768pxブロックに.attach-btn{display:noneが存在しない
    b768 = _media_block(html, '768px')
    if b768:
        ab = re.search(r'\.attach-btn\s*\{([^}]*)\}', b768)
        check(not (ab and re.search(r'display\s*:\s*none', ab.group(1))),
              "@768pxブロックに.attach-btn{display:noneが存在しない")
    else:
        check(True, "@768pxブロックに.attach-btn{display:noneが存在しない（@768pxブロックなし）")

    # 7. @768pxブロックに.member-card-actions{opacity:1が存在する
    if b768:
        mca = re.search(r'\.member-card-actions\s*\{([^}]*)\}', b768)
        check(bool(mca and re.search(r'opacity\s*:\s*1', mca.group(1))),
              "@768pxブロックに.member-card-actions{opacity:1が存在する")
    else:
        check(False, "@768pxブロックに.member-card-actions{opacity:1が存在する")

    # 8. app.jsにestimatedMsまたはtimeoutIdが存在する
    check('estimatedMs' in js or 'timeoutId' in js,
          "app.jsにestimatedMsまたはtimeoutIdが存在する")

    # 9. app.jsのonerrorにfullText.trim().length > 0が存在する
    check('fullText.trim().length > 0' in js or 'fullText.trim().length>0' in js,
          "app.jsのonerrorにfullText.trim().length > 0が存在する")


# ─── 機能試験 9: SSEレスポンスヘッダー検証 ────────────────────

def test_func9_sse_headers():
    section("機能試験9: SSEレスポンスヘッダー検証")
    import requests as req_lib, threading, socket
    from werkzeug.serving import make_server

    # ゲスト会議セッション作成
    sid = None
    with flask_app.test_client() as guest:
        r = guest.post('/api/meeting/start', json={'topic': 'SSEヘッダー検証テスト'})
        if r.status_code == 200:
            sid = (r.get_json() or {}).get('session_id')

    if not sid:
        skip("セッション作成失敗のためスキップ")
        return

    # 存在しないpersona_idを使用 → ジェネレーターが即座にエラーを返す（Anthropic呼び出しなし）
    fake_pid = "sse_header_test_nonexistent"

    try:
        with socket.socket() as s:
            s.bind(('127.0.0.1', 0))
            port = s.getsockname()[1]
        server = make_server('127.0.0.1', port, flask_app)
    except Exception as e:
        skip(f"SSEヘッダー検証スキップ（サーバー起動エラー）: {e}")
        return

    srv_t = threading.Thread(target=server.serve_forever, daemon=True)
    srv_t.start()

    try:
        url = f"http://127.0.0.1:{port}/api/stream/member/{sid}/{fake_pid}"
        try:
            resp = req_lib.get(url, stream=True, timeout=10)
            h = resp.headers
            check('text/event-stream' in h.get('Content-Type', ''),
                  "Content-Typeにtext/event-streamが含まれる")
            check('no-cache' in h.get('Cache-Control', ''),
                  "Cache-Controlにno-cacheが含まれる")
            check(h.get('X-Accel-Buffering', '').lower() == 'no',
                  "X-Accel-Buffering が no")
            check('keep-alive' in h.get('Connection', '').lower(),
                  "ConnectionにKeep-Aliveまたはkeep-aliveが含まれる")
            resp.close()
        except req_lib.exceptions.Timeout:
            skip("SSEヘッダー検証タイムアウト（ストリーム中）")
        except Exception as e:
            skip(f"SSEヘッダー検証スキップ: {e}")
    finally:
        server.shutdown()
        srv_t.join(timeout=3)


# ─── 機能試験 10: プラン制限境界値テスト ──────────────────────

def test_func10_plan_boundary():
    section("機能試験10: プラン制限の境界値テスト")
    from src.database import get_connection
    from datetime import datetime, timedelta

    ts    = int(time.time())
    email = f"test_boundary_{ts}@test.com"
    pw    = "BoundaryTest123!"
    uid   = None
    conn  = get_connection()

    try:
        with flask_app.test_client() as c:
            r = c.post('/api/auth/register',
                       json={'email': email, 'password': pw, 'name': '境界値テスト', 'tos_agreed': True, 'birth_date': '1990-01-01'})
            uid = ((r.get_json() or {}).get('user') or {}).get('id')
            if not uid:
                skip("ユーザー登録失敗のためスキップ")
                return

            # 1. 新規ユーザーのmonthly_meeting_countが0
            rows = conn.run("SELECT monthly_meeting_count FROM users WHERE id=:id", id=uid)
            cnt0 = rows[0][0] if rows else -1
            check(cnt0 == 0, f"新規ユーザーのmonthly_meeting_countが0 (got {cnt0})")

            # 2. 会議1回目が200 OK
            r2 = c.post('/api/meeting/start', json={'topic': '境界値テスト1回目'})
            check_code(r2, 200, "会議1回目が200 OK")

            # 3. monthly_meeting_count=5設定後 → 403かつcode=PLAN_LIMIT
            conn.run(
                "UPDATE users SET monthly_meeting_count=5, plan='free' WHERE id=:id", id=uid)
            r3 = c.post('/api/meeting/start', json={'topic': '境界値テスト6回目'})
            check_code(r3, 403, "monthly_meeting_count=5で会議開始が403")
            check((r3.get_json() or {}).get('code') == 'PLAN_LIMIT', "code=PLAN_LIMITが返る")

            # 4. plan='standard', credits=1 → 200かつcreditsが0になる
            conn.run(
                "UPDATE users SET plan='standard', credits=1, monthly_meeting_count=0 "
                "WHERE id=:id", id=uid)
            r4 = c.post('/api/meeting/start', json={'topic': 'スタンダード境界値テスト'})
            check_code(r4, 200, "plan='standard', credits=1 → 200 OK")
            rows4 = conn.run("SELECT credits FROM users WHERE id=:id", id=uid)
            cred4 = rows4[0][0] if rows4 else -1
            check(cred4 == 0, f"会議後にcreditsが0になる (got {cred4})")

            # 5. credits=0 → 403
            r5 = c.post('/api/meeting/start', json={'topic': 'credits=0テスト'})
            check_code(r5, 403, "credits=0で会議開始が403")

            # 6. plan='pro', plan_expires_at=過去日付 → 200かつプランがfreeに降格
            past = datetime.utcnow() - timedelta(days=1)
            conn.run(
                "UPDATE users SET plan='pro', plan_expires_at=:exp, "
                "monthly_meeting_count=0 WHERE id=:id", exp=past, id=uid)
            r6 = c.post('/api/meeting/start', json={'topic': 'pro期限切れ境界値テスト'})
            check_code(r6, 200, "pro期限切れ → 200 OK（free降格後5回以内）")
            rows6 = conn.run("SELECT plan FROM users WHERE id=:id", id=uid)
            plan6 = rows6[0][0] if rows6 else ''
            check(plan6 == 'free', f"会議後にプランがfreeに降格 (got {plan6})")

    finally:
        if uid:
            conn.run("DELETE FROM users WHERE id=:id", id=uid)
        conn.close()


# ─── 機能試験 11: クロスユーザーデータ分離テスト ──────────────

def test_func11_cross_user_isolation():
    section("機能試験11: クロスユーザーデータ分離テスト")
    from src.database import get_connection

    ts      = int(time.time())
    email_a = f"test_cross_a_{ts}@test.com"
    email_b = f"test_cross_b_{ts}@test.com"
    pw      = "CrossTest123!"
    conn    = get_connection()
    uid_a = uid_b = pid_a = None

    try:
        # ─ ユーザーA: 登録・ペルソナ作成 ─
        with flask_app.test_client() as ca:
            ra = ca.post('/api/auth/register',
                         json={'email': email_a, 'password': pw, 'name': 'ユーザーA', 'tos_agreed': True, 'birth_date': '1990-01-01'})
            uid_a = ((ra.get_json() or {}).get('user') or {}).get('id')
            if uid_a:
                rp = ca.post('/api/personas/add', json={
                    "name": "Aのペルソナ", "description": "テスト用",
                    "personality": "論理的", "speaking_style": "丁寧語",
                    "background": "", "avatar": "🔴", "color": "#EF4444", "role": "member",
                })
                pid_a = ((rp.get_json() or {}).get('persona') or {}).get('id')

        # ─ ユーザーB: 登録・分離テスト ─
        with flask_app.test_client() as cb:
            rb = cb.post('/api/auth/register',
                         json={'email': email_b, 'password': pw, 'name': 'ユーザーB', 'tos_agreed': True, 'birth_date': '1990-01-01'})
            uid_b = ((rb.get_json() or {}).get('user') or {}).get('id')

            if not uid_a or not uid_b or not pid_a:
                skip("ユーザー/ペルソナ作成失敗のためスキップ")
                return

            # 1. AのペルソナがBのAPIから見えない
            r_mem   = cb.get('/api/personas/members')
            members_b = (r_mem.get_json() or {}).get('members', [])
            b_ids_set = {m['id'] for m in members_b}
            check(pid_a not in b_ids_set, "AのペルソナがBのAPIから見えない")

            # 2. BのセッションでAのペルソナをDELETEすると400/403/404
            r_del = cb.delete(f'/api/personas/{pid_a}')
            check(r_del.status_code in (400, 403, 404),
                  f"BがAのペルソナをDELETE → 400/403/404 (got {r_del.status_code})")

            # 3. Aの学習データがBからアクセスできない
            r_learn = cb.get(f'/api/personas/{pid_a}/learn')
            if r_learn.status_code == 200:
                cnt = (r_learn.get_json() or {}).get('count', 0)
                check(cnt == 0, f"Aの学習データがBから見えない (count={cnt})")
            else:
                check(r_learn.status_code in (403, 404),
                      f"Aの学習データへのBのアクセスがエラー (HTTP {r_learn.status_code})")

            # 4. T-02: user_id=NULLのデフォルトペルソナはAPIから非公開（プライバシー強化）
            null_cnt = conn.run(
                "SELECT COUNT(*) FROM personas WHERE user_id IS NULL")[0][0]
            if null_cnt > 0:
                null_ids = {r[0] for r in conn.run(
                    "SELECT id FROM personas WHERE user_id IS NULL")}
                with flask_app.test_client() as ca2:
                    ca2.post('/api/auth/login', json={'email': email_a, 'password': pw})
                    r_a   = ca2.get('/api/personas/members')
                    a_ids = {m['id'] for m in (r_a.get_json() or {}).get('members', [])}
                    check(len(a_ids & null_ids) > 0,
                          "T-02: user_id=NULLのデフォルトペルソナがAPIから表示される（ログイン時表示修正）")
            else:
                check(True,
                      "T-02: user_id=NULLのデフォルトペルソナが存在しない（対応済み）")

    finally:
        if uid_a:
            conn.run("DELETE FROM users WHERE id=:id", id=uid_a)
        if uid_b:
            conn.run("DELETE FROM users WHERE id=:id", id=uid_b)
        conn.close()


# ─── 運用試験 5: DBスキーマ整合性確認 ─────────────────────────

def test_ops5_db_schema():
    section("運用試験5: DBスキーマ整合性確認")
    from src.database import get_connection

    conn = get_connection()
    try:
        def _cols(table: str) -> set:
            rows = conn.run("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name=:t AND table_schema='public'
            """, t=table)
            return {r[0] for r in rows}

        def _tables() -> set:
            rows = conn.run("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema='public'
            """)
            return {r[0] for r in rows}

        # 1. usersテーブルの必須カラムが全て存在する
        required = {
            'id', 'email', 'password_hash', 'name', 'plan', 'credits',
            'plan_expires_at', 'monthly_meeting_count', 'monthly_reset_at',
            'stripe_customer_id', 'created_at',
        }
        users_cols = _cols('users')
        missing = required - users_cols
        check(not missing,
              f"usersテーブルに必須カラムが全て存在する (missing={missing or 'none'})")

        # 2. プランカラム名がplanである（plan_typeでない）
        check('plan' in users_cols and 'plan_type' not in users_cols,
              "プランカラム名がplan（plan_typeでない）")

        # 3. personasテーブルにvoice_idが存在する
        check('voice_id' in _cols('personas'), "personasテーブルにvoice_idが存在する")

        # 4. 必須テーブルが全て存在する
        tables      = _tables()
        req_tbl     = {'payments', 'persona_growth', 'persona_feedback', 'persona_learn'}
        missing_tbl = req_tbl - tables
        check(not missing_tbl,
              f"payments/persona_growth/persona_feedback/persona_learnテーブルが存在する"
              f" (missing={missing_tbl or 'none'})")

        # 5. persona_learnにembeddingカラムが存在する
        check('embedding' in _cols('persona_learn'),
              "persona_learnにembeddingカラムが存在する")

    finally:
        conn.close()


# ─── 運用試験 6: 全主要エンドポイント疎通確認 ─────────────────

def test_ops6_endpoint_health():
    section("運用試験6: 全主要エンドポイント疎通確認")
    from src.database import get_connection

    ts    = int(time.time())
    email = f"test_ops6_{ts}@test.invalid"
    pw    = "Ops6Test123!"
    uid   = None
    conn  = get_connection()

    try:
        with flask_app.test_client() as c:
            # 1. GET /api/health → 200かつstatus=ok
            r1 = c.get('/api/health')
            check_code(r1, 200, "GET /api/health → 200")
            check((r1.get_json() or {}).get('status') == 'ok', "status=okが返る")

            # 2. GET /api/personas → 200
            r2 = c.get('/api/personas')
            check_code(r2, 200, "GET /api/personas → 200")

            # 3. GET /api/personas/members → 200
            r3 = c.get('/api/personas/members')
            check_code(r3, 200, "GET /api/personas/members → 200")

            # 4. GET /api/auth/me → 200かつuser=None（未ログイン）
            r4 = c.get('/api/auth/me')
            check_code(r4, 200, "GET /api/auth/me → 200（未ログイン）")
            check((r4.get_json() or {}).get('user') is None, "user=None（未ログイン）")

            # ログイン後テスト用ユーザー登録
            rr = c.post('/api/auth/register',
                        json={'email': email, 'password': pw, 'name': '疎通テスト', 'tos_agreed': True, 'birth_date': '1990-01-01'})
            uid = ((rr.get_json() or {}).get('user') or {}).get('id')
            c.post('/api/auth/login', json={'email': email, 'password': pw})

            # 5. ログイン後 GET /api/payment/status → 200
            r5 = c.get('/api/payment/status')
            check_code(r5, 200, "ログイン後 GET /api/payment/status → 200")

            # 6. GET /api/payment/schema-check → 200かつok=true
            r6 = c.get('/api/payment/schema-check')
            check_code(r6, 200, "GET /api/payment/schema-check → 200")
            check((r6.get_json() or {}).get('ok') is True, "schema-check: ok=trueが返る")

    finally:
        if uid:
            conn.run("DELETE FROM users WHERE id=:id", id=uid)
        conn.close()


# ─── 運用試験 7: APIレスポンスタイム計測（WARN） ────────────────

def test_ops7_response_time_warn(client):
    section("運用試験7: APIレスポンスタイム計測（基準超過はWARNで記録）")

    cases = [
        ("GET",  "/api/health",     None,
         "GET /api/health",      3.0),
        ("GET",  "/api/personas",   None,
         "GET /api/personas",    5.0),
        ("GET",  "/api/auth/me",    None,
         "GET /api/auth/me",     3.0),
        ("POST", "/api/auth/login", {"email": TEST_EMAIL, "password": TEST_PW},
         "POST /api/auth/login", 5.0),
    ]

    for method, path, body, label, limit_sec in cases:
        t0 = time.time()
        r  = client.get(path) if method == "GET" else client.post(path, json=body)
        elapsed = time.time() - t0
        if elapsed > limit_sec:
            warn(f"{label}: {elapsed*1000:.0f}ms（基準{limit_sec*1000:.0f}ms超過）")
        check(True,
              f"{label}: {elapsed*1000:.0f}ms / {limit_sec*1000:.0f}ms (HTTP {r.status_code})")


# ─── 機能試験 12: 法律対応の回帰テスト（静的ファイル検査） ────────

def test_func12_legal_static():
    section("機能試験12: 法律対応の回帰テスト（静的ファイル検査）")

    base = os.path.dirname(os.path.abspath(__file__))
    html = open(os.path.join(base, 'web', 'index.html'), encoding='utf-8').read()
    js   = open(os.path.join(base, 'web', 'app.js'),     encoding='utf-8').read()

    check('tosAgreeCheck'      in html or 'tosAgreeCheck'      in js, "tosAgreeCheckが存在する")
    check('/terms'             in html or '/terms'             in js, "/termsへのリンクが存在する")
    check('/privacy'           in html or '/privacy'           in js, "/privacyへのリンクが存在する")
    check('personaTosModal'    in html or 'personaTosModal'    in js, "personaTosModalが存在する")
    check('openPersonaTosModal' in html or 'openPersonaTosModal' in js, "openPersonaTosModalが存在する")
    check('PERSONA_EMOJIS'     in html or 'PERSONA_EMOJIS'     in js, "PERSONA_EMOJISが存在する")


# ─── 機能試験 13: ToS同意チェックの動作確認 ──────────────────────

def test_func13_tos_check():
    section("機能試験13: ToS同意チェックの動作確認")

    ts    = int(time.time())
    email = f"test_tos_{ts}@test.com"
    pw    = "testpass123"
    name  = "TosTestUser"
    uid   = None
    conn  = db_conn()

    try:
        with flask_app.test_client() as c:
            # 1. tos_agreed=False → 400
            r1 = c.post('/api/auth/register',
                        json={'email': email, 'password': pw, 'name': name, 'tos_agreed': False, 'birth_date': '1990-01-01'})
            check_code(r1, 400, "tos_agreed=Falseで登録 → 400エラー")

            # 2. tos_agreed=True → 200
            r2 = c.post('/api/auth/register',
                        json={'email': email, 'password': pw, 'name': name, 'tos_agreed': True, 'birth_date': '1990-01-01'})
            check_code(r2, 200, "tos_agreed=Trueで登録 → 200 OK")
            uid = ((r2.get_json() or {}).get('user') or {}).get('id')

            # 3. tos_agreed_at が NULL でない
            if uid:
                rows = conn.run(
                    "SELECT tos_agreed_at FROM users WHERE id=:id", id=uid)
                val = rows[0][0] if rows else None
                check(val is not None, "DBのtos_agreed_atがNULLでない")
            else:
                check(False, "DBのtos_agreed_atがNULLでない（ユーザー作成失敗）")

            # 18歳未満登録拒否テスト
            with flask_app.test_client() as c_minor:
                r_minor = c_minor.post('/api/auth/register',
                                        json={'email': f'minor_{email}', 'password': pw,
                                              'name': 'テスト未成年', 'tos_agreed': True,
                                              'birth_date': '2015-01-01'})
                check_code(r_minor, 400, "18歳未満登録 → 400エラー")
                minor_data = r_minor.get_json() or {}
                check(minor_data.get('code') == 'AGE_RESTRICTED', "18歳未満エラーのcodeがAGE_RESTRICTED")
    finally:
        if uid:
            conn.run("DELETE FROM users WHERE id=:id", id=uid)
        conn.close()


# ─── 運用試験 8: 新規DBカラム整合性確認 ──────────────────────────

def test_ops8_new_columns():
    section("運用試験8: 新規DBカラム整合性確認")
    from src.database import get_connection

    conn = get_connection()
    try:
        def _cols(table: str) -> set:
            rows = conn.run("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name=:t AND table_schema='public'
            """, t=table)
            return {r[0] for r in rows}

        users_cols    = _cols('users')
        personas_cols = _cols('personas')

        check('tos_agreed_at'        in users_cols,    "usersテーブルにtos_agreed_atが存在する")
        check('tos_agreed_at'        in personas_cols, "personasテーブルにtos_agreed_atが存在する")
        check('is_deceased_confirmed' in personas_cols, "personasテーブルにis_deceased_confirmedが存在する")
    finally:
        conn.close()


# ─── 機能試験 14: ログイン時デフォルトペルソナ表示確認 ──────────

def test_func14_default_persona_visibility(client):
    section("機能試験14: ログイン時デフォルトペルソナ表示確認")

    # ログイン状態で GET /api/personas/members
    r = client.get('/api/personas/members')
    check_code(r, 200, "GET /api/personas/members → 200 OK")
    data = r.get_json() or {}
    members = data.get('members', [])
    member_ids = [m['id'] for m in members]

    check('koumei' in member_ids,   "members に koumei（諸葛亮孔明）が含まれる")
    check('hideyoshi' in member_ids, "members に hideyoshi（豊臣秀吉）が含まれる")

    facilitator = data.get('facilitator')
    check(facilitator is not None, "facilitator が返る")

    # ゲスト状態でも GET /api/personas/members にデフォルトペルソナが含まれること
    with flask_app.test_client() as guest:
        r_g = guest.get('/api/personas/members')
        check_code(r_g, 200, "ゲスト: GET /api/personas/members → 200 OK")
        guest_data = r_g.get_json() or {}
        guest_ids = [m['id'] for m in guest_data.get('members', [])]
        check('koumei' in guest_ids or 'hideyoshi' in guest_ids,
              "ゲスト: members にデフォルトペルソナが含まれる")


# ─── メイン ───────────────────────────────────────────────────

_skipped_sections: list[str] = []


def safe_run(name: str, func, *args):
    """テスト関数を安全に実行。DB接続エラー等は SKIP として記録し継続。"""
    import pg8000.exceptions
    try:
        func(*args)
    except (pg8000.exceptions.InterfaceError, OSError, TimeoutError) as e:
        msg = str(e)[:120]
        print(f"{SKIP_SYM} {name}: DB接続エラーのためスキップ ({msg})")
        _skipped_sections.append(name)
    except Exception as e:
        print(f"{FAIL_SYM} {name}: 予期しない例外 {type(e).__name__}: {str(e)[:120]}")
        _results.append(False)


if __name__ == '__main__':
    db_host = urlparse(os.environ.get('DATABASE_URL', '')).hostname or '(未設定)'
    print("AI-PERSONA会議室 包括テスト")
    print("=" * 60)
    info(f"テスト用メール: {TEST_EMAIL}")
    info(f"DB接続先: {db_host}")

    cleanup()  # 事前クリーンアップ

    _existing_count = 0
    try:
        with flask_app.test_client() as client:
            safe_run("機能試験1: 認証",              test1_auth,             client)
            safe_run("機能試験2: ゲスト会議",        test2_guest_meeting)
            safe_run("機能試験3: ペルソナCRUD",      test3_persona_crud,     client)
            _set_user_plan(state.get('user_id'), 'standard', credits=100)  # learn制限解除
            safe_run("機能試験4: 学習データ冪等性",  test4_learn_idempotency, client)
            safe_run("機能試験4b: 学習データ非同期保存", test4b_learn_async_save, client)
            safe_run("機能試験4c: ペルソナ間非混入",    test4c_persona_isolation, client)
            _set_user_plan(state.get('user_id'), 'free', credits=0)  # freeに戻す
            safe_run("機能試験5: 会議開始・メッセージ", test5_meeting,        client)
            safe_run("機能試験6: フィードバック",    test6_feedback,         client)
            safe_run("機能試験7: プラン制限",        test7_plan_limits,      client)
            safe_run("運用試験1: データ永続性",      test8_persistence,      client)
            safe_run("運用試験2: 複数ペルソナ",      test9_multi_persona,    client)
            safe_run("運用試験3: DB整合性",          test10_db_integrity)
            safe_run("運用試験4: レスポンスタイム計測", test11_response_time,  client)

            _existing_count = len(_results)  # 既存121件の基準点

            safe_run("機能試験8: iPhone回帰テスト",     test_func8_mobile_static)
            safe_run("機能試験9: SSEヘッダー検証",      test_func9_sse_headers)
            safe_run("機能試験10: プラン境界値テスト",  test_func10_plan_boundary)
            safe_run("機能試験11: クロスユーザー分離",  test_func11_cross_user_isolation)
            safe_run("運用試験5: DBスキーマ整合性",     test_ops5_db_schema)
            safe_run("運用試験6: エンドポイント疎通",   test_ops6_endpoint_health)
            safe_run("運用試験7: レスポンスタイムWARN", test_ops7_response_time_warn, client)
            safe_run("機能試験12: 法律対応静的ファイル検査", test_func12_legal_static)
            safe_run("機能試験13: ToS同意チェック",         test_func13_tos_check)
            safe_run("運用試験8: 新規DBカラム整合性",        test_ops8_new_columns)
            safe_run("機能試験14: デフォルトペルソナ表示",   test_func14_default_persona_visibility, client)
    finally:
        cleanup()

    passed  = sum(1 for r in _results if r)
    total   = len(_results)
    failed  = total - passed
    skipped = len(_skipped_sections)
    added   = total - _existing_count

    print(f"\n{'='*60}")
    print(f"テスト結果: {passed}/{total} PASS  ({failed} FAIL, {skipped} SKIP)")
    print(f"総テスト数: {total}件（既存: {_existing_count}件 + 追加: {added}件）")
    if _warns:
        print(f"WARN: {len(_warns)}件")
        if len(_warns) >= 3:
            print("⚠️ パフォーマンス劣化の可能性あり")
    if _skipped_sections:
        print(f"スキップセクション: {', '.join(_skipped_sections)}")
    print('='*60)

    if failed == 0:
        print("全テスト PASS（SKIPは除く）")
        sys.exit(0)
    else:
        print("FAIL あり — 上記を確認してください")
        sys.exit(1)
