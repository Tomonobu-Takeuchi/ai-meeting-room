"""
Step3-3 デグレ・動作検証スクリプト
実行: $env:DATABASE_URL="postgresql://postgres:localpass@localhost:6300/ai_meeting"; python -X utf8 verify_step3_3.py
"""
import os, sys
from datetime import datetime
from types import SimpleNamespace
import bcrypt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.main import app, verify_payment_session
from src.database import get_connection, create_user, get_user_by_id, add_user_credits, save_payment

results = []
def log(label, ok, detail=""):
    mark = "OK" if ok else "NG"
    results.append(ok)
    print(f"[{mark}] {label} {detail}")

ts = int(datetime.utcnow().timestamp())
pw_hash = bcrypt.hashpw(b"Verify123!", bcrypt.gensalt()).decode()

# ════════════════════════════════════════════
# シナリオ①：Webhook未処理の状態でverify-sessionを呼ぶ
#   → DB更新が一切発生しないこと（最重要：今回のバグの再発防止確認）
# ════════════════════════════════════════════
print("\n=== シナリオ①：Webhook未処理時にverify-sessionを呼ぶ ===")
u1 = create_user(f"verify_step33_a_{ts}@test.invalid", pw_hash, "検証A")
session_id_1 = f"cs_test_verify33_{ts}_a"
save_payment(u1['id'], session_id_1, 'standard', 480, 0)  # status='pending'相当で保存される想定

# StripeのCheckout.Session.retrieveをモック化
import stripe
fake_session = SimpleNamespace(
    metadata=SimpleNamespace(user_id=str(u1['id']), payment_type='standard'),
    payment_status='paid',
    status='complete',
    customer='cus_test_verify33_a',
)
stripe.checkout.Session.retrieve = lambda sid, **kw: fake_session

with app.test_client() as c:
    with c.session_transaction() as sess:
        sess['user_id'] = u1['id']
    r1 = c.post('/api/payment/verify-session', json={'session_id': session_id_1})
    body1 = r1.get_json() or {}
    print(f"response: status={r1.status_code} body={body1}")

d1 = get_user_by_id(u1['id'])
print(f"DB状態: plan={d1['plan']} credits={d1['credits']} is_earlybird={d1['is_earlybird']}")

log("verified=Falseが返る（webhook未処理なので）", body1.get('verified') is False, f"got={body1.get('verified')}")
log("reason=webhook_pending", body1.get('reason') == 'webhook_pending', f"got={body1.get('reason')}")
log("planがstandardに書き換わっていない（DB更新されていない証拠）", d1['plan'] == 'free', f"got={d1['plan']}")
log("creditsが加算されていない（add_user_credits未呼び出しの証拠）", d1['credits'] == 0, f"got={d1['credits']}")

# ════════════════════════════════════════════
# シナリオ②：Webhook処理済み（payments.status='completed'）の状態でverify-sessionを呼ぶ
#   → verified=Trueになり、status_dataが正しく返ること（DB更新は依然として行わないこと）
# ════════════════════════════════════════════
print("\n=== シナリオ②：Webhook処理済み後にverify-sessionを呼ぶ ===")
u2 = create_user(f"verify_step33_b_{ts}@test.invalid", pw_hash, "検証B")
session_id_2 = f"cs_test_verify33_{ts}_b"
save_payment(u2['id'], session_id_2, 'pro', 1980, 0)

# Webhookが先に処理済みだった状態を模擬
conn = get_connection()
conn.run("UPDATE users SET plan='pro', is_earlybird=TRUE, billing_anchor_day=19 WHERE id=:id", id=u2['id'])
conn.run("UPDATE payments SET status='completed' WHERE stripe_session_id=:sid", sid=session_id_2)
conn.close()

fake_session2 = SimpleNamespace(
    metadata=SimpleNamespace(user_id=str(u2['id']), payment_type='pro'),
    payment_status='paid',
    status='complete',
    customer='cus_test_verify33_b',
)
stripe.checkout.Session.retrieve = lambda sid, **kw: fake_session2

with app.test_client() as c:
    with c.session_transaction() as sess:
        sess['user_id'] = u2['id']
    r2 = c.post('/api/payment/verify-session', json={'session_id': session_id_2})
    body2 = r2.get_json() or {}
    print(f"response: status={r2.status_code} body={body2}")

d2_before_plan = 'pro'  # webhook側で既に設定済みだった値
d2 = get_user_by_id(u2['id'])

log("verified=Trueが返る（webhook処理済みなので）", body2.get('verified') is True, f"got={body2.get('verified')}")
log("statusにplan=proが含まれる", (body2.get('status') or {}).get('plan') == 'pro')
log("DB側のplanが変化していない（verify-session自体は何も書き込んでいない証拠）", d2['plan'] == d2_before_plan, f"got={d2['plan']}")
log("is_earlybirdがTrueのまま保持されている（webhookが設定した値を上書きしていない）", d2['is_earlybird'] is True, f"got={d2['is_earlybird']}")

# ════════════════════════════════════════════
# シナリオ③：unknown payment_typeでもDB更新が起きない確認（旧コードのelse分岐相当の安全確認）
# ════════════════════════════════════════════
print("\n=== シナリオ③：status!=completeの場合は即時verified=Falseで返ること ===")
u3 = create_user(f"verify_step33_c_{ts}@test.invalid", pw_hash, "検証C")
fake_session3 = SimpleNamespace(
    metadata=SimpleNamespace(user_id=str(u3['id']), payment_type='standard'),
    payment_status='unpaid',
    status='open',
    customer='cus_test_verify33_c',
)
stripe.checkout.Session.retrieve = lambda sid, **kw: fake_session3
with app.test_client() as c:
    with c.session_transaction() as sess:
        sess['user_id'] = u3['id']
    r3 = c.post('/api/payment/verify-session', json={'session_id': 'cs_test_verify33_c'})
    body3 = r3.get_json() or {}
    print(f"response: status={r3.status_code} body={body3}")

log("status=openでverified=Falseが返る", body3.get('verified') is False, f"got={body3.get('verified')}")
log("reasonにstatus=openが含まれる", body3.get('reason') == 'status=open', f"got={body3.get('reason')}")

# ════════════════════════════════════════════
print(f"\n=== 結果: {sum(results)}/{len(results)} OK ===")
print("ALL OK" if all(results) else "NG項目あり（上記参照）")

# 後始末
conn = get_connection()
conn.run("DELETE FROM users WHERE email LIKE 'verify_step33_%'")
conn.run("DELETE FROM payments WHERE stripe_session_id LIKE 'cs_test_verify33_%'")
conn.close()
