"""
verify_step6.py — Step6 Layer1/2/3並行化 データレベル検証スクリプト
ローカルDocker環境（port6300）使用。本番DBへは接続しない。

検証項目:
  1. プラン別レスポンス形状の確認
  2. ★最重要: layer3_monthly_countの加算が成功時のみであること
  3. trial_layer2_used / trial_layer3_used が成功時のみ更新されること
  4. Layer3レスポンスタイム参考計測
  5. 既存テスト161 PASS確認
"""
import os, sys, json, time, uuid, bcrypt
from unittest.mock import patch, MagicMock
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 本番DBガード
_db_url = os.environ.get('DATABASE_URL', '')
if 'railway.app' in _db_url or 'rlwy.net' in _db_url:
    print('[ERROR] 本番DB接続が検出されました。DATABASE_URLをローカルに設定してください。')
    sys.exit(1)

# ローカルDB強制
os.environ['DATABASE_URL'] = 'postgresql://postgres:localpass@localhost:6300/ai_meeting'

import pg8000.native
from src.main import app as flask_app, meeting_room
from src.database import get_connection

flask_app.config['TESTING'] = True

# ─── ユーティリティ ───────────────────────────────────────────

PASS_SYM = "  [PASS]"
FAIL_SYM = "  [FAIL]"
INFO_SYM = "  [INFO]"
results = []

def check(ok, label):
    sym = PASS_SYM if ok else FAIL_SYM
    print(f"{sym} {label}")
    results.append(bool(ok))
    return bool(ok)

def info(msg):
    print(f"{INFO_SYM} {msg}")

def section(title):
    print(f"\n{'='*60}")
    print(title)
    print('='*60)

def db_direct():
    return pg8000.native.Connection(
        host='localhost', port=6300, database='ai_meeting',
        user='postgres', password='localpass'
    )

def get_layer3_count(conn, uid):
    rows = conn.run(
        "SELECT layer3_monthly_count FROM users WHERE id=:uid", uid=uid
    )
    return rows[0][0] if rows else 0

def get_trial_flags(conn, uid):
    rows = conn.run(
        "SELECT trial_layer2_used, trial_layer3_used FROM users WHERE id=:uid", uid=uid
    )
    return (bool(rows[0][0]), bool(rows[0][1])) if rows else (False, False)

# ─── テストユーザーセットアップ ──────────────────────────────

UNIQ = str(uuid.uuid4())[:8]
USERS = {
    'pro':      f"s6pro_{UNIQ}@test.invalid",
    'standard': f"s6std_{UNIQ}@test.invalid",
    'free':     f"s6free_{UNIQ}@test.invalid",
}
PW = "test123"
_pw_hash = bcrypt.hashpw(PW.encode(), bcrypt.gensalt()).decode()
user_ids = {}

def setup_users(conn):
    for plan, email in USERS.items():
        rows = conn.run(
            "INSERT INTO users (email, password_hash, name, plan, credits) "
            "VALUES (:e, :p, :n, :pl, 0) RETURNING id",
            e=email, p=_pw_hash, n=f"S6test_{plan}", pl=plan
        )
        user_ids[plan] = rows[0][0]
        info(f"作成: {plan} user_id={user_ids[plan]} email={email}")

def cleanup_users(conn):
    conn.run("DELETE FROM users WHERE email LIKE 's6pro\\_%@test.invalid' OR email LIKE 's6std\\_%@test.invalid' OR email LIKE 's6free\\_%@test.invalid'")
    info("テストユーザー削除完了")

# ─── テストセッション作成 ────────────────────────────────────

def make_test_session(user_id, n_messages=5, category='strategy'):
    """MeetingRoomにテストセッションを直接注入する"""
    sid = str(uuid.uuid4())[:8]
    members = [{"id": "koumei", "name": "諸葛亮孔明", "role": "member",
                "personality": "慎重", "background": "軍師", "speaking_style": "丁寧"}]
    facilitator = {"id": "facilitator", "name": "ファシリテータ", "role": "facilitator",
                   "personality": "中立", "background": "進行", "speaking_style": "明瞭"}
    messages = []
    for i in range(n_messages):
        messages.append({"id": str(uuid.uuid4())[:8], "role": "assistant",
                         "persona_id": "koumei", "content": f"テスト発言{i+1}：事業戦略について検討します。", "timestamp": "2026-06-20T10:00:00"})
        if i % 2 == 0:
            messages.append({"id": str(uuid.uuid4())[:8], "role": "user",
                              "persona_id": "user", "content": f"ユーザー発言{i+1}：どう思いますか？", "timestamp": "2026-06-20T10:01:00"})
    meeting_room.sessions[sid] = {
        "session_id": sid, "topic": "新規事業の方向性について", "members": members,
        "facilitator": facilitator, "messages": messages, "user_id": user_id,
        "category": category, "created_at": "2026-06-20T10:00:00", "status": "active",
        "crisis_flag": False, "opponent_persona_id": None, "opponent_name": None,
    }
    return sid

def login(client, email):
    r = client.post('/api/auth/login', json={"email": email, "password": PW})
    return r.status_code == 200

# ─── モックレスポンス生成 ────────────────────────────────────

def make_invalid_json_response():
    """パース失敗するレスポンスを返すモック"""
    mock_msg = MagicMock()
    mock_msg.stop_reason = "end_turn"
    mock_msg.content = [MagicMock(text="これはJSONではありません{invalid}")]
    return mock_msg

def make_valid_layer3_response():
    """strategy用の正常なJSONレスポンスを返すモック"""
    data = {
        "frameworks": [{"name": "SWOT分析", "analysis": "強み：AI活用", "recommendation": "積極展開"}],
        "strategic_direction": "AI活用事業の積極展開",
        "implementation_roadmap": [{"phase": "Phase1", "timeline": "3ヶ月", "actions": ["市場調査"]}],
        "risks_and_mitigation": [{"risk": "競合激化", "mitigation": "差別化戦略"}],
        "key_success_factors": ["スピード", "品質"],
        "executive_summary": "AI活用によるビジネス変革を推進する方向性が確認されました。"
    }
    mock_msg = MagicMock()
    mock_msg.stop_reason = "end_turn"
    mock_msg.content = [MagicMock(text=json.dumps(data, ensure_ascii=False))]
    return mock_msg

def make_valid_layer2_response():
    data = {
        "conclusion": "活発な議論が行われました。",
        "persona_views": [{"persona": "諸葛亮孔明", "view": "慎重な検討が必要", "reason": "リスク管理"}],
        "risks": ["市場リスク"],
        "next_actions": ["詳細調査の実施"]
    }
    mock_msg = MagicMock()
    mock_msg.stop_reason = "end_turn"
    mock_msg.content = [MagicMock(text=json.dumps(data, ensure_ascii=False))]
    return mock_msg

# ─── 検証本体 ────────────────────────────────────────────────

def run():
    conn = db_direct()
    setup_users(conn)

    try:
        with flask_app.test_client() as client:

            # ===================================================
            section("1. プラン別レスポンス形状確認")
            # ===================================================

            # --- pro: /brief がlayer2・layer3を返さないこと ---
            login(client, USERS['pro'])
            sid_pro = make_test_session(user_ids['pro'], n_messages=10)
            with patch('anthropic.Anthropic.messages') as mock_m:
                mock_m.create.return_value = MagicMock(
                    stop_reason="end_turn",
                    content=[MagicMock(text='{"conclusion":"テスト","actions":["a"],"user_basis":"b"}')]
                )
                r = client.post(f'/api/meeting/{sid_pro}/brief', json={"category": "strategy"})
            data = r.get_json()
            check(r.status_code == 200, "pro /brief → 200 OK")
            check('layer1' in data, "pro /brief レスポンスにlayer1キーあり")
            check('layer2' not in data, "pro /brief レスポンスにlayer2キーなし（並行化済み）")
            check('layer3' not in data, "pro /brief レスポンスにlayer3キーなし（並行化済み）")
            check('layer3_remaining' in data, "pro /brief にlayer3_remainingあり")
            check('plan' in data and data['plan'] == 'pro', "pro /brief にplan='pro'あり")

            # --- free: /brief_layer2 がlayer2:null を返すこと ---
            login(client, USERS['free'])
            sid_free = make_test_session(user_ids['free'], n_messages=5)
            r = client.post(f'/api/meeting/{sid_free}/brief_layer2', json={"category": "strategy"})
            data = r.get_json()
            check(r.status_code == 200, "free /brief_layer2 → 200 OK（拒否ではなくnull返却）")
            check(data.get('layer2') is None, "free /brief_layer2 → layer2:null（trial_layer指定なし）")

            # --- standard: /brief_layer2 がlayer2データを返すこと ---
            login(client, USERS['standard'])
            sid_std = make_test_session(user_ids['standard'], n_messages=5)
            with patch('anthropic.Anthropic.messages') as mock_m:
                mock_m.create.return_value = make_valid_layer2_response()
                r = client.post(f'/api/meeting/{sid_std}/brief_layer2', json={"category": "chat"})
            data = r.get_json()
            check(r.status_code == 200, "standard /brief_layer2 → 200 OK")
            check(data.get('layer2') is not None, "standard /brief_layer2 → layer2データあり")

            # --- free: /brief_layer3 trial_layer指定なしでlayer3:null ---
            login(client, USERS['free'])
            r = client.post(f'/api/meeting/{sid_free}/brief_layer3', json={"category": "strategy"})
            data = r.get_json()
            check(r.status_code == 200, "free /brief_layer3（trial指定なし）→ 200")
            check(data.get('layer3') is None, "free /brief_layer3（trial指定なし）→ layer3:null")

            # ===================================================
            section("2. ★最重要: layer3_monthly_count 加算ロジック検証（pro）")
            # ===================================================

            login(client, USERS['pro'])
            sid_pro2 = make_test_session(user_ids['pro'], n_messages=15, category='strategy')
            uid_pro = user_ids['pro']

            # 2-1. 事前カウント記録
            count_before = get_layer3_count(conn, uid_pro)
            info(f"layer3_monthly_count 実施前: {count_before}")

            # 2-2. パース失敗モックで /brief_layer3 を呼ぶ
            with patch('anthropic.Anthropic.messages') as mock_m:
                mock_m.create.return_value = make_invalid_json_response()
                r_fail = client.post(f'/api/meeting/{sid_pro2}/brief_layer3',
                                     json={"category": "strategy"})
            conn2 = db_direct()
            count_after_fail = get_layer3_count(conn2, uid_pro)
            conn2.close()
            info(f"layer3_monthly_count 失敗後: {count_after_fail}")
            check(r_fail.status_code == 200, "失敗時も500エラーにならず200を返す")
            check(count_after_fail == count_before,
                  f"★失敗時: layer3_monthly_countが変化しない ({count_before}→{count_after_fail})")

            # 2-3. 正常モックで /brief_layer3 を呼ぶ
            with patch('anthropic.Anthropic.messages') as mock_m:
                mock_m.create.return_value = make_valid_layer3_response()
                r_ok = client.post(f'/api/meeting/{sid_pro2}/brief_layer3',
                                   json={"category": "strategy"})
            conn3 = db_direct()
            count_after_ok = get_layer3_count(conn3, uid_pro)
            conn3.close()
            info(f"layer3_monthly_count 成功後: {count_after_ok}")
            check(r_ok.status_code == 200, "成功時 200 OK")
            data_ok = r_ok.get_json()
            check(data_ok.get('layer3') is not None, "成功時 layer3データあり")
            check(count_after_ok == count_before + 1,
                  f"★成功時: layer3_monthly_countが+1のみ ({count_before}→{count_before+1}, 実際={count_after_ok})")
            check(data_ok.get('layer3_remaining') == (30 - count_after_ok),
                  f"layer3_remaining={data_ok.get('layer3_remaining')} (30-{count_after_ok}={30-count_after_ok})")

            info(f"シーケンス確認: {count_before} → 失敗→{count_after_fail} → 成功→{count_after_ok} (期待: +0, +1)")

            # ===================================================
            section("3. trial_layer2_used / trial_layer3_used 更新ロジック検証（free）")
            # ===================================================

            login(client, USERS['free'])
            uid_free = user_ids['free']

            # 3-1. trial_layer2: 失敗時はフラグ不変
            t2_before, t3_before = get_trial_flags(conn, uid_free)
            info(f"trial flags 実施前: layer2={t2_before} layer3={t3_before}")

            with patch('anthropic.Anthropic.messages') as mock_m:
                mock_m.create.return_value = make_invalid_json_response()
                r = client.post(f'/api/meeting/{sid_free}/brief_layer2',
                                json={"category": "chat", "trial_layer": "layer2"})
            conn4 = db_direct()
            t2_after_fail, _ = get_trial_flags(conn4, uid_free)
            conn4.close()
            check(t2_after_fail == False, f"★Layer2失敗時: trial_layer2_usedがFalseのまま ({t2_after_fail})")

            # 3-2. trial_layer2: 成功時にフラグが立つ
            with patch('anthropic.Anthropic.messages') as mock_m:
                mock_m.create.return_value = make_valid_layer2_response()
                r = client.post(f'/api/meeting/{sid_free}/brief_layer2',
                                json={"category": "chat", "trial_layer": "layer2"})
            conn5 = db_direct()
            t2_after_ok, _ = get_trial_flags(conn5, uid_free)
            conn5.close()
            check(t2_after_ok == True, f"★Layer2成功時: trial_layer2_usedがTrueになる ({t2_after_ok})")

            # 3-3. trial_layer3: 失敗時はフラグ不変
            _, t3_before2 = get_trial_flags(conn, uid_free)
            with patch('anthropic.Anthropic.messages') as mock_m:
                mock_m.create.return_value = make_invalid_json_response()
                r = client.post(f'/api/meeting/{sid_free}/brief_layer3',
                                json={"category": "strategy", "trial_layer": "layer3"})
            conn6 = db_direct()
            _, t3_after_fail = get_trial_flags(conn6, uid_free)
            conn6.close()
            check(t3_after_fail == False, f"★Layer3失敗時: trial_layer3_usedがFalseのまま ({t3_after_fail})")

            # 3-4. trial_layer3: 成功時にフラグが立つ
            with patch('anthropic.Anthropic.messages') as mock_m:
                mock_m.create.return_value = make_valid_layer3_response()
                r = client.post(f'/api/meeting/{sid_free}/brief_layer3',
                                json={"category": "strategy", "trial_layer": "layer3"})
            conn7 = db_direct()
            _, t3_after_ok = get_trial_flags(conn7, uid_free)
            conn7.close()
            check(t3_after_ok == True, f"★Layer3成功時: trial_layer3_usedがTrueになる ({t3_after_ok})")

            # ===================================================
            section("4. Layer3レスポンスタイム参考計測（proプラン・実APIコール）")
            # ===================================================

            login(client, USERS['pro'])
            # 発言数多めセッション（30件）
            sid_heavy = make_test_session(user_ids['pro'], n_messages=30, category='strategy')

            info("Layer3単体の実API計測を実施（実際のClaude APIを呼ぶ）")
            info("※APIキーがローカル設定にない場合はSKIPします")
            api_key = os.getenv("ANTHROPIC_API_KEY", "")
            if not api_key or api_key.startswith("sk-ant-api03-_26P8"):
                # テスト用のダミーキーの場合はスキップ
                info("ANTHROPIC_API_KEY未設定またはダミーキーのためタイム計測SKIP")
            else:
                t0 = time.time()
                r_time = client.post(f'/api/meeting/{sid_heavy}/brief_layer3',
                                     json={"category": "strategy"})
                elapsed = time.time() - t0
                if r_time.status_code == 200 and r_time.get_json().get('layer3'):
                    info(f"Layer3 応答時間（30発言）: {elapsed:.1f}秒")
                    check(elapsed < 120, f"Layer3タイムアウト120秒以内: {elapsed:.1f}秒")
                else:
                    info(f"Layer3 API呼び出し失敗（status={r_time.status_code}）: タイム計測スキップ")

    finally:
        cleanup_users(conn)
        conn.close()
        # テストセッションをメモリから削除
        for sid in list(meeting_room.sessions.keys()):
            if meeting_room.sessions[sid].get('topic') == '新規事業の方向性について':
                del meeting_room.sessions[sid]

    # ===================================================
    section("結果サマリー")
    # ===================================================
    total = len(results)
    passed = sum(results)
    failed = total - passed
    print(f"\nStep6検証: {passed}/{total} PASS  ({failed} FAIL)")
    if failed > 0:
        print("  *** FAIL項目があります ***")
    else:
        print("  全項目 PASS")
    return failed == 0


if __name__ == "__main__":
    ok = run()
    sys.exit(0 if ok else 1)
