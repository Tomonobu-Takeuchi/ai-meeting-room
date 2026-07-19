"""
CONT-1 デグレ試験（Chat側オラクル検証）
DB/Docker不要でロジックのみを検証。Codeはこのテストと同じ入力パターンを実DB経由の
関数（save_meeting_log / search_learn_data / get_persona_patterns 等）にも与え、
同じ結果になることを2.5節の統合テストで別途確認すること。

実行方法: python3 cont1_test_reference_logic.py
（Chat側サンドボックスで実行済み・全15項目PASS確認済み）
"""
from cont1_reference_logic import (
    fifo_pick_oldest_meeting_log, aggregate_speeches_by_persona,
    build_summary_log, diversify_candidates, category_fallback_query,
)

def check(cond, label):
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {label}")
    assert cond, label

# --- ①FIFO: 手動データは保護、会議ログ由来の最古のみ削除対象 ---
rows = [
    (1, '手動アップロード'),          # 最古・手動データ→保護
    (2, '会議ログ_議題A'),           # 2番目に古い・会議ログ由来→削除対象はコレ
    (3, '会議ログ_議題B'),
]
check(fifo_pick_oldest_meeting_log(rows) == 2, "FIFO: 最古が手動データの場合はスキップし次の会議ログ由来を返す")
check(fifo_pick_oldest_meeting_log([(1, '手動のみ')]) is None, "FIFO: 会議ログ由来が1件もなければNone")
check(fifo_pick_oldest_meeting_log([(1, '会議ログ_X')]) == 1, "FIFO: 最古がそのまま会議ログ由来ならそれを返す")

# --- ②1会議1件要約: user/facilitator除外、30字未満除外、ペルソナ単位で集約 ---
messages = [
    {'persona_id': 'koumei', 'content': '短い'},  # 30字未満→除外
    {'persona_id': 'koumei', 'content': 'これはCONT-1テスト用の発言その1です（30字以上の本文）'},
    {'persona_id': 'koumei', 'content': 'これはCONT-1テスト用の発言その2です（30字以上の本文）'},
    {'persona_id': 'user', 'content': 'ユーザー発言は対象外のはず（30字以上のダミー文字列です）'},
    {'persona_id': 'facilitator', 'content': 'ファシリテータ発言も対象外のはず（30字以上のダミー）'},
    {'persona_id': 'hideyoshi', 'content': 'これはCONT-1テスト用の発言その3です（30字以上の本文）'},
]
agg = aggregate_speeches_by_persona(messages)
check(set(agg.keys()) == {'koumei', 'hideyoshi'}, "要約集約: user/facilitatorは除外され対象ペルソナのみ残る")
check(len(agg['koumei']) == 2, "要約集約: 30字未満は除外され30字以上の発言のみ集約される")
log = build_summary_log('議題X', agg['koumei'])
check(log.count('[発言要約]') == 1 and 'その1' in log and 'その2' in log,
      "要約ログ: 複数発言が1件のログ本文に結合される")
long_speech = ['あ' * 1000]
check(len(build_summary_log('議題X', long_speech)) < 550, "要約ログ: 500字でtruncateされ肥大化しない")

# --- ③-B 多様性確保: 資料由来・会議ログ由来が両方ヒットしていれば両方含める ---
candidates = [
    {'content': 'm1', 'source': '会議ログ_議題A', 'similarity': 0.95},
    {'content': 'm2', 'source': '会議ログ_議題B', 'similarity': 0.90},
    {'content': 'm3', 'source': '会議ログ_議題C', 'similarity': 0.85},
    {'content': 'r1', 'source': 'PDF資料', 'similarity': 0.40},
]
picked = diversify_candidates(candidates, limit=3)
sources = [c['source'] for c in picked]
check(any(s == 'PDF資料' for s in sources),
      "多様性確保: 類似度最下位でも資料由来を最低1件含める（純類似度順だと落ちるはずのr1が入る）")
check(len(picked) == 3, "多様性確保: limit件数を超えない")
only_resource = [
    {'content': 'r1', 'source': 'PDF資料', 'similarity': 0.9},
    {'content': 'r2', 'source': 'URL資料', 'similarity': 0.8},
]
check(diversify_candidates(only_resource, limit=3) == sorted(only_resource, key=lambda c: -c['similarity']),
      "多様性確保: 一方の由来が存在しない場合は従来通り類似度順で欠落なく返る")

# --- ③-C カテゴリフィルタ+フォールバック ---
calls = []
def fake_query(use_category):
    calls.append(use_category)
    if use_category:
        return []
    return ['fallback_pattern']
result = category_fallback_query(fake_query, topic_category='business')
check(result == ['fallback_pattern'], "カテゴリフィルタ: 0件ならフォールバックで無条件取得した結果が返る")
check(calls == [True, False], "カテゴリフィルタ: まずカテゴリ指定で問い合わせ、0件の場合のみ無条件で再問い合わせする")

calls2 = []
def fake_query2(use_category):
    calls2.append(use_category)
    return ['hit'] if use_category else ['should_not_be_called']
result2 = category_fallback_query(fake_query2, topic_category='business')
check(result2 == ['hit'], "カテゴリフィルタ: カテゴリ一致がヒットすればそれを返す")
check(calls2 == [True], "カテゴリフィルタ: ヒットした場合はフォールバッククエリを発行しない")

result3 = category_fallback_query(lambda use_category: ['no_category_result'], topic_category=None)
check(result3 == ['no_category_result'], "カテゴリフィルタ: topic_category未指定時は最初から無条件取得")

print("\n全項目PASS")
