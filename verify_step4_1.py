"""
Step4-1 デグレ・動作検証スクリプト
実行: $env:DATABASE_URL="postgresql://postgres:localpass@localhost:6300/ai_meeting"; python -X utf8 verify_step4_1.py
"""
import os, sys
from datetime import datetime
import bcrypt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.main import app, EARLYBIRD_LIMIT
from src.database import get_connection, create_user, get_user_payment_status

results = []
def log(label, ok, detail=""):
    mark = "OK" if ok else "NG"
    results.append(ok)
    print(f"[{mark}] {label} {detail}")

ts = int(datetime.utcnow().timestamp())
pw_hash = bcrypt.hashpw(b"Verify123!", bcrypt.gensalt()).decode()

# ════════════════════════════════════════════
# シナリオ①：get_user_payment_status()がis_earlybirdを返すこと（既存フィールドの後方互換確認も含む）
# ════════════════════════════════════════════
print("\n=== シナリオ①：get_user_payment_status()のis_earlybird返却確認 ===")
u1 = create_user(f"verify_step41_a_{ts}@test.invalid", pw_hash, "検証A")
conn = get_connection()
conn.run("UPDATE users SET plan='standard', is_earlybird=TRUE, monthly_meeting_count=3 WHERE id=:id", id=u1['id'])
conn.close()

status1 = get_user_payment_status(u1['id'])
print(f"status1 = {status1}")
log("is_earlybird=Trueが返る", status1.get('is_earlybird') is True, f"got={status1.get('is_earlybird')}")
log("既存フィールドplanが維持されている", status1.get('plan') == 'standard', f"got={status1.get('plan')}")
log("既存フィールドmonthly_meeting_countが維持されている", status1.get('monthly_meeting_count') == 3, f"got={status1.get('monthly_meeting_count')}")

u2 = create_user(f"verify_step41_b_{ts}@test.invalid", pw_hash, "検証B")
status2 = get_user_payment_status(u2['id'])
print(f"status2(free・is_earlybird未設定) = {status2}")
log("is_earlybird=False（デフォルト）が返る", status2.get('is_earlybird') is False, f"got={status2.get('is_earlybird')}")

# ════════════════════════════════════════════
# シナリオ②：/api/payment/statusがis_earlybirdを含めて返すこと（ログイン必須のまま）
# ════════════════════════════════════════════
print("\n=== シナリオ②：/api/payment/statusのレスポンス確認 ===")
with app.test_client() as c:
    # 未ログインで呼ぶと401になること（既存仕様が壊れていないことの確認）
    r0 = c.get('/api/payment/status')
    log("未ログインで/api/payment/statusは401", r0.status_code == 401, f"got={r0.status_code}")

    with c.session_transaction() as sess:
        sess['user_id'] = u1['id']
    r1 = c.get('/api/payment/status')
    body1 = r1.get_json() or {}
    print(f"response: status={r1.status_code} body={body1}")
    log("status=200", r1.status_code == 200)
    log("is_earlybirdが含まれる", body1.get('is_earlybird') is True, f"got={body1.get('is_earlybird')}")
    log("public_keyが含まれる（既存仕様維持）", 'public_key' in body1)

# ════════════════════════════════════════════
# シナリオ③：/api/payment/earlybird-statusが未ログインでも200で返ること（最重要：FT-15-D-06）
# ════════════════════════════════════════════
print("\n=== シナリオ③：未ログインでのearlybird-status確認 ===")
with app.test_client() as c:
    r2 = c.get('/api/payment/earlybird-status')
    body2 = r2.get_json() or {}
    print(f"response(未ログイン): status={r2.status_code} body={body2}")
    log("未ログインでも401にならない", r2.status_code == 200, f"got={r2.status_code}")
    log("earlybird_limitが100", body2.get('earlybird_limit') == EARLYBIRD_LIMIT, f"got={body2.get('earlybird_limit')}")
    log("earlybird_usedが整数で返る", isinstance(body2.get('earlybird_used'), int))
    log("earlybird_remaining = limit - used の関係が成立",
        body2.get('earlybird_remaining') == EARLYBIRD_LIMIT - body2.get('earlybird_used', -1))
    log("is_fullが含まれる", 'is_full' in body2)

# ════════════════════════════════════════════
# シナリオ④：is_earlybird=TRUEのユーザーがearlybird_usedに正しくカウントされること
# ════════════════════════════════════════════
print("\n=== シナリオ④：count_earlybird_users()との整合確認 ===")
from src.database import count_earlybird_users
before_count = count_earlybird_users()
with app.test_client() as c:
    r3 = c.get('/api/payment/earlybird-status')
    body3 = r3.get_json() or {}
log("earlybird_usedがcount_earlybird_users()の実値と一致", body3.get('earlybird_used') == before_count,
    f"expect={before_count} got={body3.get('earlybird_used')}")

# ════════════════════════════════════════════
print(f"\n=== 結果: {sum(results)}/{len(results)} OK ===")
print("ALL OK" if all(results) else "NG項目あり（上記参照）")

# 後始末
conn = get_connection()
conn.run("DELETE FROM users WHERE email LIKE 'verify_step41_%'")
conn.close()
