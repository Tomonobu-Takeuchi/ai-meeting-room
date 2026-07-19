"""
BUG-EMB1 デグレ試験（Chat側オラクル検証）。
実行方法: python3 bugemb1_test_sim_db.py
（Chatサンドボックスで実行済み・16項目全PASS。うち2項目は「修正前コードで
実際にバグが再現すること」自体の実証。）
"""
from bugemb1_sim_db import (
    setup_db, save_learn_data_old, update_learn_data_embedding_old,
    save_learn_data_new, update_learn_data_embedding_new,
    backfill_missing_embeddings,
)

def check(cond, label):
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {label}")
    assert cond, label

# --- ①修正前の再現：バグが実際に発生することを示す ---
conn = setup_db()
save_learn_data_old(conn, 'koumei', 220, 'これはテスト発言です', 'src')
rowcount = update_learn_data_embedding_old(conn, 'koumei', 220, 'これはテスト発言です', '[0.1,0.2]')
check(rowcount == 0,
      "再現: pgp_sym_encryptの非決定性により、修正前のcontent一致UPDATEは0件のまま失敗する")
remaining = conn.execute("SELECT embedding FROM persona_learn").fetchall()
check(remaining[0][0] is None, "再現: 実際にembeddingがNULLのまま残る（本番と同じ症状）")

# --- ②修正後：idベースなら必ず一致する ---
conn2 = setup_db()
new_id = save_learn_data_new(conn2, 'koumei', 220, 'これはテスト発言です', 'src')
check(isinstance(new_id, int), "修正: save_learn_dataがINSERTした行のidを返す")
n = update_learn_data_embedding_new(conn2, new_id, '[0.1,0.2]')
check(n == 1, "修正: idベースのUPDATEは1件ヒットする")
row = conn2.execute("SELECT embedding FROM persona_learn WHERE id=?", (new_id,)).fetchone()
check(row[0] == '[0.1,0.2]', "修正: 実際にembeddingが正しく設定される")

# --- ③同一persona・同一contentで2行できても、互いのembeddingを誤って上書きしない ---
conn3 = setup_db()
id_a = save_learn_data_new(conn3, 'koumei', 220, '同じ内容の発言', 'src')
id_b = save_learn_data_new(conn3, 'koumei', 220, '同じ内容の発言', 'src')
check(id_a != id_b, "前提: 重複除外が機能しないため2行できる（既知の別不具合、今回は対象外）")
update_learn_data_embedding_new(conn3, id_a, '[AAA]')
update_learn_data_embedding_new(conn3, id_b, '[BBB]')
row_a = conn3.execute("SELECT embedding FROM persona_learn WHERE id=?", (id_a,)).fetchone()
row_b = conn3.execute("SELECT embedding FROM persona_learn WHERE id=?", (id_b,)).fetchone()
check(row_a[0] == '[AAA]' and row_b[0] == '[BBB]',
      "修正: 同一内容の2行でも、それぞれ自分のidに対応するembeddingのみが設定される（クロス汚染なし）")

# --- ④embedding IS NULL条件により、既に設定済みの行を誤って上書きしない ---
n2 = update_learn_data_embedding_new(conn2, new_id, '[9.9,9.9]')
check(n2 == 0, "修正: 既にembedding設定済みの行はembedding IS NULL条件により再UPDATEされない")
row_final = conn2.execute("SELECT embedding FROM persona_learn WHERE id=?", (new_id,)).fetchone()
check(row_final[0] == '[0.1,0.2]', "修正: 既存のembedding値が意図せず上書きされていない")

# --- ⑤バックフィルスクリプト：本番相当の未設定行を一括救済 ---
conn4 = setup_db()
ids = []
for i in range(5):
    ids.append(save_learn_data_new(conn4, 'hideyoshi', 220, f'発言その{i}', 'src'))
update_learn_data_embedding_new(conn4, ids[0], '[already_set]')

calls = []
def fake_embed(text):
    calls.append(text)
    return f'[embedded:{text}]'

success, failed = backfill_missing_embeddings(conn4, fake_embed)
check(success == 4, f"バックフィル: embedding未設定4件のみ処理される (got {success})")
check(len(calls) == 4, "バックフィル: 既に設定済みの1件はembedding API呼び出し対象に含まれない")
check(all('発言その' in c for c in calls), "バックフィル: 復号済みの平文がembedding関数に渡っている（暗号文のままではない）")
remaining_null = conn4.execute("SELECT COUNT(*) FROM persona_learn WHERE embedding IS NULL").fetchone()[0]
check(remaining_null == 0, "バックフィル: 実行後は未設定行が0件になる")

# --- ⑥冪等性：2回目の実行は対象0件で正常終了 ---
success2, failed2 = backfill_missing_embeddings(conn4, fake_embed)
check(success2 == 0 and failed2 == 0, "バックフィル: 2回目の実行は対象0件（冪等）")

# --- ⑦1件だけ壊れたデータがあっても他の行の処理は止まらない ---
conn5 = setup_db()
ok_id = save_learn_data_new(conn5, 'koumei', 220, '正常な発言', 'src')
bad_id = save_learn_data_new(conn5, 'koumei', 220, '復号できないデータ', 'src')
conn5.execute("UPDATE persona_learn SET content='CORRUPTED_NO_MARKER' WHERE id=?", (bad_id,))
conn5.commit()

def embed_that_fails_on_corrupted(text):
    if 'CORRUPTED' in text:
        raise RuntimeError("simulated embedding failure")
    return f'[embedded:{text}]'

s3, f3 = backfill_missing_embeddings(conn5, embed_that_fails_on_corrupted)
check(s3 == 1 and f3 == 1, f"バックフィル: 1件失敗しても成功1件は処理完了する (success={s3}, failed={f3})")
ok_row = conn5.execute("SELECT embedding FROM persona_learn WHERE id=?", (ok_id,)).fetchone()
check(ok_row[0] is not None, "バックフィル: 失敗した行の影響を受けず、正常な行のembeddingは設定される")

print("\n全項目PASS")
