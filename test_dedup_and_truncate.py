"""
実行方法: python3 test_dedup_and_truncate.py
（Chatサンドボックスで実行済み・12項目全PASS）
"""
from dedup_and_truncate import (
    content_hash, setup_db, save_learn_data_hashfix,
    truncate_to_tokens, mock_encode_2_tokens_per_char, mock_decode_2_tokens_per_char,
)

def check(cond, label):
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {label}")
    assert cond, label

# --- content_hashは決定的（暗号化と違い、同じ平文なら常に同じ値） ---
check(content_hash('テスト発言') == content_hash('テスト発言'),
      "content_hash: 同じ平文なら常に同じハッシュ値になる（決定的）")
check(content_hash('テスト発言A') != content_hash('テスト発言B'),
      "content_hash: 異なる平文なら異なるハッシュ値になる")

# --- 重複チェック修正: 同一persona・同一内容の2回目は新規行を作らずidを返す ---
conn = setup_db()
id1, dup1 = save_learn_data_hashfix(conn, 'koumei', 220, '同じ会議ログ内容', 'src')
check(dup1 is False, "1回目の保存は新規行として扱われる")
id2, dup2 = save_learn_data_hashfix(conn, 'koumei', 220, '同じ会議ログ内容', 'src')
check(dup2 is True, "2回目（同一persona・同一内容）は重複として検出される")
check(id1 == id2, "重複時は新規行を作らず既存のidを返す")
count = conn.execute("SELECT COUNT(*) FROM persona_learn").fetchone()[0]
check(count == 1, "実際にDB上の行数は1件のまま増えない")

# --- 別personaや別ユーザーなら重複扱いしない ---
id3, dup3 = save_learn_data_hashfix(conn, 'hideyoshi', 220, '同じ会議ログ内容', 'src')
check(dup3 is False, "別ペルソナなら同じ内容でも重複扱いしない")
id4, dup4 = save_learn_data_hashfix(conn, 'koumei', 999, '同じ会議ログ内容', 'src')
check(dup4 is False, "別ユーザーなら同じ内容でも重複扱いしない")

# --- トークン超過対応: 境界ロジック ---
short_text = 'あ' * 100
result_short = truncate_to_tokens(short_text, mock_encode_2_tokens_per_char, mock_decode_2_tokens_per_char, max_tokens=8000)
check(result_short == short_text, "短いテキスト（上限未満）は切り詰められずそのまま返る")

long_text = 'あ' * 5000  # mock換算で10000トークン相当 > 8000
result_long = truncate_to_tokens(long_text, mock_encode_2_tokens_per_char, mock_decode_2_tokens_per_char, max_tokens=8000)
result_tokens = mock_encode_2_tokens_per_char(result_long)
check(len(result_tokens) <= 8000, f"長いテキストはmax_tokens以下に切り詰められる (got {len(result_tokens)})")
check(len(result_long) < len(long_text), "実際に元より短くなっている")

boundary_text = 'あ' * 4000  # ちょうど8000トークン相当（境界値）
result_boundary = truncate_to_tokens(boundary_text, mock_encode_2_tokens_per_char, mock_decode_2_tokens_per_char, max_tokens=8000)
check(result_boundary == boundary_text, "ちょうど境界値のテキストは切り詰められない（off-by-oneがない）")

print("\n全項目PASS")
