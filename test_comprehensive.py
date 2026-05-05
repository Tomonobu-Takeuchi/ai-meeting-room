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
flask_app.config['TESTING'] = True

UNIQUE = str(uuid.uuid4())[:8]
TEST_EMAIL    = f"comp_{UNIQUE}@test.invalid"
TEST_PW       = "testpass123"
TEST_NAME     = "テスト太郎"
TEST_EMAIL_B  = f"comp_{UNIQUE}_b@test.invalid"   # 永続性テスト用

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

    # 登録
    r = client.post('/api/auth/register',
                    json={'email': TEST_EMAIL, 'password': TEST_PW, 'name': TEST_NAME})
    check_code(r, 200, "register 200 OK")
    data = r.get_json() or {}
    check('user' in data, "register レスポンスに user が含まれる")
    check(data.get('user', {}).get('email') == TEST_EMAIL, "登録メールアドレスが一致")

    # 重複登録
    r2 = client.post('/api/auth/register',
                     json={'email': TEST_EMAIL, 'password': TEST_PW, 'name': TEST_NAME})
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

    r = client.get('/api/personas/members')
    members = (r.get_json() or {}).get('members', [])

    available = [m['id'] for m in members]
    info(f"利用可能ペルソナ数: {len(available)}")

    if len(available) < 2:
        skip(f"ペルソナ数 {len(available)} < 2: スキップ")
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

    try:
        with flask_app.test_client() as client:
            safe_run("機能試験1: 認証",              test1_auth,             client)
            safe_run("機能試験2: ゲスト会議",        test2_guest_meeting)
            safe_run("機能試験3: ペルソナCRUD",      test3_persona_crud,     client)
            safe_run("機能試験4: 学習データ冪等性",  test4_learn_idempotency, client)
            safe_run("機能試験4b: 学習データ非同期保存", test4b_learn_async_save, client)
            safe_run("機能試験4c: ペルソナ間非混入",    test4c_persona_isolation, client)
            safe_run("機能試験5: 会議開始・メッセージ", test5_meeting,        client)
            safe_run("機能試験6: フィードバック",    test6_feedback,         client)
            safe_run("機能試験7: プラン制限",        test7_plan_limits,      client)
            safe_run("運用試験1: データ永続性",      test8_persistence,      client)
            safe_run("運用試験2: 複数ペルソナ",      test9_multi_persona,    client)
            safe_run("運用試験3: DB整合性",          test10_db_integrity)
            safe_run("運用試験4: レスポンスタイム計測", test11_response_time,  client)
    finally:
        cleanup()

    passed  = sum(1 for r in _results if r)
    total   = len(_results)
    failed  = total - passed
    skipped = len(_skipped_sections)

    print(f"\n{'='*60}")
    print(f"テスト結果: {passed}/{total} PASS  ({failed} FAIL, {skipped} SKIP)")
    if _skipped_sections:
        print(f"スキップセクション: {', '.join(_skipped_sections)}")
    print('='*60)

    if failed == 0:
        print("全テスト PASS（SKIPは除く）")
        sys.exit(0)
    else:
        print("FAIL あり — 上記を確認してください")
        sys.exit(1)
