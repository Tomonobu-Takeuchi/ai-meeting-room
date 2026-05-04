"""
test_learn_data.py — 学習データ修正の検証スクリプト

Test 1: 修正前の現状確認（DB調査済み記録との照合）
Test 2: 修正後の動作確認（実際にDB操作して検証）
Test 3: 4修正すべての静的コード確認
"""

import os, sys
from dotenv import load_dotenv
load_dotenv()
from urllib.parse import urlparse
import pg8000.native

# ===== DB接続 =====

def get_connection():
    url = urlparse(os.environ.get('DATABASE_URL', ''))
    return pg8000.native.Connection(
        host=url.hostname, port=url.port or 5432,
        database=url.path.lstrip('/'), user=url.username,
        password=url.password, ssl_context=True,
    )

# ===== 修正したコードを直接インポート =====

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))
from database import save_learn_data, get_all_learn_data, get_learn_data_count

PASS = '  [PASS]'
FAIL = '  [FAIL]'
INFO = '  [INFO]'

# テスト用の定数（既存ペルソナIDを使用、FK制約を満たすため）
TEST_PERSONA_ID  = 'hideyoshi'   # personas.id に存在、学習データなし
TEST_PERSONA_ID2 = 'professor'   # 別ペルソナでの確認用
TEST_USER_ID     = 1             # users.id=1（test@example.com）
TEST_CONTENT_A   = '__TEST_CONTENT_AAA_IDEMPOTENCY__'
TEST_CONTENT_B   = '__TEST_CONTENT_BBB_DIFFERENT__'
TEST_SOURCE      = '__test_source__'


def cleanup_test_data():
    """テストデータを削除する"""
    conn = get_connection()
    conn.run(
        "DELETE FROM persona_learn WHERE source = :src",
        src=TEST_SOURCE
    )
    conn.close()


# =============================================================
# Test 1: 修正前の現状確認（調査時点の記録との照合）
# =============================================================

def test1_pre_fix_record():
    print('\n' + '='*60)
    print('Test 1: 修正前の現状確認（前回調査記録との照合）')
    print('='*60)

    conn = get_connection()
    total  = conn.run("SELECT COUNT(*) FROM persona_learn WHERE persona_id='koumei'")[0][0]
    unique = conn.run("SELECT COUNT(DISTINCT content) FROM persona_learn WHERE persona_id='koumei'")[0][0]
    uid_rows = conn.run("SELECT DISTINCT user_id FROM persona_learn WHERE persona_id='koumei'")
    conn.close()

    print(f'{INFO} koumei 現在の総件数: {total}')
    print(f'{INFO} koumei 現在のuniqueコンテンツ数: {unique}')
    print(f'{INFO} koumei のuser_id分布: {[r[0] for r in uid_rows]}')
    print()
    print('--- 前回調査記録（2026-05-04 修正前）---')
    print(f'{INFO} 調査時の総件数:           1,138件')
    print(f'{INFO} 調査時のuniqueコンテンツ: 17件')
    print(f'{INFO} 調査時のuser_id:           [1]（全件 user_id=1）')
    print(f'{INFO} 重複パターン:              各ファイルが67回ずつ重複')
    print(f'{INFO} 発生期間:                 2026-05-04 21:54〜22:06（12分）')
    print(f'{INFO} 原因:                     実行ガードなし→並行クリック→concurrent save')

    ok_total  = (total == 17)
    ok_unique = (unique == 17)

    print()
    print(f'{PASS if ok_total  else FAIL} DBクリーンアップ済み: {total}件（期待: 17）')
    print(f'{PASS if ok_unique else FAIL} 重複なし: unique={unique}件（期待: 17）')

    return [ok_total, ok_unique]


# =============================================================
# Test 2: 修正後の動作確認
# =============================================================

def test2_post_fix():
    print('\n' + '='*60)
    print('Test 2: 修正後の動作確認')
    print('='*60)

    results = []
    cleanup_test_data()  # 事前クリーンアップ

    # -------- Test 2-1: 冪等性チェック（save_learn_data） --------
    print('\n--- Test 2-1: save_learn_data の冪等性チェック ---')

    conn = get_connection()
    before = conn.run(
        "SELECT COUNT(*) FROM persona_learn WHERE persona_id=:pid AND source=:src",
        pid=TEST_PERSONA_ID, src=TEST_SOURCE
    )[0][0]
    conn.close()

    # 1回目の登録
    save_learn_data(TEST_PERSONA_ID, TEST_USER_ID, TEST_CONTENT_A, TEST_SOURCE)
    conn = get_connection()
    after1 = conn.run(
        "SELECT COUNT(*) FROM persona_learn WHERE persona_id=:pid AND source=:src",
        pid=TEST_PERSONA_ID, src=TEST_SOURCE
    )[0][0]
    conn.close()

    # 2回目（完全同一content・同一user_id）→ スキップされるはず
    save_learn_data(TEST_PERSONA_ID, TEST_USER_ID, TEST_CONTENT_A, TEST_SOURCE)
    conn = get_connection()
    after2 = conn.run(
        "SELECT COUNT(*) FROM persona_learn WHERE persona_id=:pid AND source=:src",
        pid=TEST_PERSONA_ID, src=TEST_SOURCE
    )[0][0]
    conn.close()

    # 3回目（別content）→ 登録されるはず
    save_learn_data(TEST_PERSONA_ID, TEST_USER_ID, TEST_CONTENT_B, TEST_SOURCE)
    conn = get_connection()
    after3 = conn.run(
        "SELECT COUNT(*) FROM persona_learn WHERE persona_id=:pid AND source=:src",
        pid=TEST_PERSONA_ID, src=TEST_SOURCE
    )[0][0]
    conn.close()

    # 4回目（同一content、user_id=None）→ user_id が違うので登録される
    save_learn_data(TEST_PERSONA_ID, None, TEST_CONTENT_A, TEST_SOURCE)
    conn = get_connection()
    after4 = conn.run(
        "SELECT COUNT(*) FROM persona_learn WHERE persona_id=:pid AND source=:src",
        pid=TEST_PERSONA_ID, src=TEST_SOURCE
    )[0][0]
    conn.close()

    ok1 = (after1 - before == 1)    # 新規登録
    ok2 = (after2 - after1 == 0)    # 重複スキップ
    ok3 = (after3 - after2 == 1)    # 別content → 登録
    ok4 = (after4 - after3 == 1)    # user_id違い → 登録

    print(f'{PASS if ok1 else FAIL} 1回目 新規登録: +{after1 - before}件（期待: +1）')
    print(f'{PASS if ok2 else FAIL} 2回目 同content同user_id: +{after2 - after1}件（期待: +0、重複スキップ）')
    print(f'{PASS if ok3 else FAIL} 3回目 別content同user_id: +{after3 - after2}件（期待: +1）')
    print(f'{PASS if ok4 else FAIL} 4回目 同content別user_id(None): +{after4 - after3}件（期待: +1、user_id違いは別レコード）')
    results += [ok1, ok2, ok3, ok4]

    # -------- Test 2-2: get_all_learn_data の user_id=None/0/値 の挙動 --------
    print('\n--- Test 2-2: get_all_learn_data の user_id 処理確認 ---')

    # user_id=TEST_USER_ID（=1）→ user_id=1 OR NULL の両方を取得するはず
    data_uid1 = get_all_learn_data(TEST_PERSONA_ID, TEST_USER_ID)
    # user_id=None → NULL レコードのみ
    data_none = get_all_learn_data(TEST_PERSONA_ID, None)
    # user_id=0 → user_id=0 のレコードを検索（存在しない）
    data_zero = get_all_learn_data(TEST_PERSONA_ID, 0)

    # TEST_PERSONA_ID に登録したデータ：
    #   (CONTENT_A, user_id=1), (CONTENT_B, user_id=1), (CONTENT_A, user_id=None)
    # DISTINCT ON (content, source) が効いているため:
    #   user_id=1 クエリ → (user_id=1 OR IS NULL) → CONTENT_A, CONTENT_B → 2件以上
    #   user_id=None クエリ → IS NULL → CONTENT_A(NULL) → 1件以上
    #   user_id=0 クエリ → (user_id=0 OR IS NULL) → NULLレコードが返る → 1件以上
    #   ※ user_id=0 は存在しないユーザーだが OR IS NULL でNULLレコードは取得できる

    uid1_contents = set(d['source'] for d in data_uid1)
    none_contents = set(d['source'] for d in data_none)

    ok_uid1 = len(data_uid1) >= 2          # CONTENT_A と CONTENT_B が取れる
    ok_none = len(data_none) >= 1           # NULL レコードの CONTENT_A が取れる
    ok_zero = (len(data_zero) >= 1)         # (user_id=0 OR IS NULL) → NULLレコードが返る

    print(f'{INFO} get_all_learn_data(user_id=1) 返却件数: {len(data_uid1)}件')
    print(f'{INFO} get_all_learn_data(user_id=None) 返却件数: {len(data_none)}件')
    print(f'{INFO} get_all_learn_data(user_id=0) 返却件数: {len(data_zero)}件')
    print(f'{PASS if ok_uid1 else FAIL} user_id=1 で自分のデータ（user_id=1 OR NULL）が取得できる')
    print(f'{PASS if ok_none else FAIL} user_id=None でNULLレコードが取得できる（旧バグ: 0件になっていた）')
    print(f'{PASS if ok_zero else FAIL} user_id=0 で (user_id=0 OR IS NULL) → NULLレコード取得（>= 1件）')
    results += [ok_uid1, ok_none, ok_zero]

    # -------- Test 2-3: get_learn_data_count の user_id=None 修正確認 --------
    print('\n--- Test 2-3: get_learn_data_count の user_id is not None 修正確認 ---')

    count_uid1 = get_learn_data_count(TEST_PERSONA_ID, TEST_USER_ID)
    count_none = get_learn_data_count(TEST_PERSONA_ID, None)
    count_zero = get_learn_data_count(TEST_PERSONA_ID, 0)

    # TEST_PERSONA_ID に: (CONTENT_A, uid=1), (CONTENT_B, uid=1), (CONTENT_A, uid=None) の3件
    ok_count_uid1 = (count_uid1 >= 3)    # 1 OR NULL → 3件以上
    ok_count_none = (count_none >= 1)    # IS NULL → 1件以上
    ok_count_zero = (count_zero >= 1)    # (user_id=0 OR IS NULL) → NULLレコードがある → 1件以上

    print(f'{INFO} count({TEST_PERSONA_ID}, user_id=1)   = {count_uid1}（期待: >=3）')
    print(f'{INFO} count({TEST_PERSONA_ID}, user_id=None)= {count_none}（期待: >=1）')
    print(f'{INFO} count({TEST_PERSONA_ID}, user_id=0)   = {count_zero}（期待: >=1、OR IS NULL でNULLレコード取得）')
    print(f'{PASS if ok_count_uid1 else FAIL} user_id=1 で自分のデータ件数が取れる（{count_uid1}件）')
    print(f'{PASS if ok_count_none else FAIL} user_id=None で IS NULL クエリが正しく動く（旧バグ修正）')
    print(f'{PASS if ok_count_zero else FAIL} user_id=0 で (user_id=0 OR IS NULL) → {count_zero}件（NULLレコード含む）')
    results += [ok_count_uid1, ok_count_none, ok_count_zero]

    # -------- Test 2-4: koumei の DISTINCT ON + LIMIT 確認 --------
    print('\n--- Test 2-4: koumei の DISTINCT ON + LIMIT 100 確認 ---')

    data_koumei = get_all_learn_data('koumei', TEST_USER_ID)
    sources     = [d['source'] for d in data_koumei]
    unique_src  = set(sources)

    ok_limit    = (len(data_koumei) <= 100)
    ok_count17  = (len(data_koumei) == 17)
    ok_distinct = (len(sources) == len(unique_src))  # source が重複していない

    print(f'{INFO} koumei のget_all_learn_data返却件数: {len(data_koumei)}件')
    print(f'{INFO} koumei のユニークsource数: {len(unique_src)}件')
    print(f'{PASS if ok_limit    else FAIL} LIMIT 100 が効いている（{len(data_koumei)} <= 100）')
    print(f'{PASS if ok_count17  else FAIL} 本来の17件が返る（{len(data_koumei)} == 17）')
    print(f'{PASS if ok_distinct else FAIL} DISTINCT ON が効いている（重複なし）')
    results += [ok_limit, ok_count17, ok_distinct]

    cleanup_test_data()
    print(f'\n{INFO} テストデータ(source={TEST_SOURCE})をクリーンアップしました')

    return results


# =============================================================
# Test 3: 4修正の静的コード確認
# =============================================================

def test3_static_code():
    print('\n' + '='*60)
    print('Test 3: 4修正のコード静的確認')
    print('='*60)

    results = []

    appjs_path = os.path.join(os.path.dirname(__file__), 'web', 'app.js')
    db_path    = os.path.join(os.path.dirname(__file__), 'src', 'database.py')
    pm_path    = os.path.join(os.path.dirname(__file__), 'src', 'persona', 'persona_manager.py')

    with open(appjs_path, encoding='utf-8') as f:
        appjs = f.read()
    with open(db_path, encoding='utf-8') as f:
        dbpy = f.read()
    with open(pm_path, encoding='utf-8') as f:
        pmpy = f.read()

    # --- 修正1: app.js 実行ガード ---
    print('\n--- Test 3-1: app.js 実行ガード（修正1）---')
    checks = [
        ('editSubmitting: false', 'State.editSubmitting フラグ定義'),
        ('addSubmitting: false',  'State.addSubmitting フラグ定義'),
        ('if (State.editSubmitting) return;', 'editPersona 実行ガード'),
        ('if (State.addSubmitting) return;',  'addPersona 実行ガード'),
        ('DOM.confirmEditPersona.disabled = true', 'editPersona ボタン disabled'),
        ('DOM.confirmAddPersona.disabled = true',  'addPersona ボタン disabled'),
        ('State.editSubmitting = false;\n    DOM.confirmEditPersona.disabled = false', 'finally でリセット'),
    ]
    for pattern, label in checks:
        ok = pattern in appjs
        print(f'{PASS if ok else FAIL} {label}')
        results.append(ok)

    # --- 修正2: database.py 冪等性チェック ---
    print('\n--- Test 3-2: database.py 冪等性チェック（修正2）---')
    checks2 = [
        ('IS NOT DISTINCT FROM :uid', 'NULL対応の重複チェック条件'),
        ('if existing:\n        conn.close()\n        return', '重複時の早期return'),
    ]
    for pattern, label in checks2:
        ok = pattern in dbpy
        print(f'{PASS if ok else FAIL} {label}')
        results.append(ok)

    # --- 修正3: DISTINCT ON + LIMIT 100 ---
    print('\n--- Test 3-3: DISTINCT ON + LIMIT 100（修正3）---')
    checks3 = [
        ('DISTINCT ON (content, source)', 'DISTINCT ON による重複排除'),
        ('LIMIT 100',                     'LIMIT 100（承認済み値）'),
    ]
    for pattern, label in checks3:
        ok = pattern in dbpy
        print(f'{PASS if ok else FAIL} {label}')
        results.append(ok)

    # --- 修正4: user_id is not None ---
    print('\n--- Test 3-4: user_id is not None 修正（修正4）---')
    # database.py
    ok_is_not_none = dbpy.count('if user_id is not None:') >= 2  # count, get_all の両方
    ok_no_if_uid   = 'if user_id:\n' not in dbpy  # 旧パターンが消えているか
    # persona_manager.py
    ok_no_or0_get  = 'user_id or 0' not in pmpy
    ok_del_ref     = 'get_all_learn_data(persona_id, user_id)' in pmpy  # or 0 を除去した後の形

    print(f'{PASS if ok_is_not_none else FAIL} database.py に if user_id is not None: が2箇所ある（count+get_all）')
    print(f'{PASS if ok_no_if_uid   else FAIL} database.py から旧 if user_id: パターンが除去されている')
    print(f'{PASS if ok_no_or0_get  else FAIL} persona_manager.py から user_id or 0 が除去されている')
    print(f'{PASS if ok_del_ref     else FAIL} persona_manager.py で get_all_learn_data(persona_id, user_id) を呼んでいる')
    results += [ok_is_not_none, ok_no_if_uid, ok_no_or0_get, ok_del_ref]

    return results


# =============================================================
# メイン
# =============================================================

if __name__ == '__main__':
    print('学習データ修正 検証スクリプト')
    print('=' * 60)

    t1_res = test1_pre_fix_record()
    t2_res = test2_post_fix()
    t3_res = test3_static_code()

    all_results = t1_res + t2_res + t3_res
    passed       = sum(1 for r in all_results if r)
    total        = len(all_results)
    failed_count = total - passed

    print('\n' + '='*60)
    print(f'テスト結果: {passed}/{total} PASS  ({failed_count} FAIL)')
    print('='*60)

    if failed_count == 0:
        print('全テスト PASS — 修正は正常に適用されています')
        sys.exit(0)
    else:
        print('FAIL あり — 詳細を上記で確認してください')
        sys.exit(1)
