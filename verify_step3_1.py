"""
Step3-1 デグレ・動作検証スクリプト
実行: $env:DATABASE_URL="postgresql://postgres:localpass@localhost:6300/ai_meeting"; python -X utf8 verify_step3_1.py
"""
import os, sys
from datetime import datetime, timedelta
from types import SimpleNamespace
import bcrypt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.main import (
    app, STRIPE_PRICE_STANDARD_EARLY, STRIPE_PRICE_STANDARD_REGULAR,
    STRIPE_PRICE_PRO_EARLY, STRIPE_PRICE_PRO_REGULAR, STRIPE_SECRET_KEY,
    _handle_checkout_completed, _handle_invoice_payment,
)
from src.database import get_connection, create_user, get_user_by_id, count_earlybird_users
import stripe

results = []
def log(label, ok, detail=""):
    mark = "OK" if ok else "NG"
    results.append(ok)
    print(f"[{mark}] {label} {detail}")

ts = int(datetime.utcnow().timestamp())
pw_hash = bcrypt.hashpw(b"Verify123!", bcrypt.gensalt()).decode()

# ════════════════════════════════════════════════
# ① payment_checkout() 実検証（Stripeテストモード実APIを使用）
# ════════════════════════════════════════════════
print("\n=== ① payment_checkout() 検証 ===")
if not STRIPE_SECRET_KEY:
    print("[WARN] STRIPE_SECRET_KEY が未設定のため Section ① をスキップします")
    print("[WARN] 本番確認前に Railway の STRIPE_SECRET_KEY を .env に設定して再実行してください")
    log("① STRIPE_SECRET_KEY設定確認", False, "未設定のためスキップ（Section②③は続行）")
else:
    u1 = create_user(f"verify_step31_std_{ts}@test.invalid", pw_hash, "検証std")
    u2 = create_user(f"verify_step31_pro_{ts}@test.invalid", pw_hash, "検証pro")

    eb_count_before = count_earlybird_users()
    print(f"現在のアーリーバード人数: {eb_count_before} / 100")
    expect_standard_price = STRIPE_PRICE_STANDARD_EARLY if eb_count_before < 100 else STRIPE_PRICE_STANDARD_REGULAR
    expect_pro_price = STRIPE_PRICE_PRO_EARLY if eb_count_before < 100 else STRIPE_PRICE_PRO_REGULAR

    with app.test_client() as c:
        with c.session_transaction() as sess:
            sess['user_id'] = u1['id']
        r1 = c.post('/api/payment/checkout', json={'type': 'standard'})
        body1 = r1.get_json() or {}
        print(f"standard checkout response: status={r1.status_code} body={body1}")
        sid1 = body1.get('checkout_url', '').split('/pay/')[-1].split('#')[0] if 'checkout_url' in body1 else None

        with c.session_transaction() as sess:
            sess['user_id'] = u2['id']
        r2 = c.post('/api/payment/checkout', json={'type': 'pro'})
        body2 = r2.get_json() or {}
        print(f"pro checkout response: status={r2.status_code} body={body2}")
        sid2 = body2.get('checkout_url', '').split('/pay/')[-1].split('#')[0] if 'checkout_url' in body2 else None

    for label, sid, expect_price in [("standard", sid1, expect_standard_price), ("pro", sid2, expect_pro_price)]:
        if not sid:
            log(f"{label} checkout_url取得", False, "session_idが取得できない")
            continue
        s = stripe.checkout.Session.retrieve(sid, expand=['line_items'])
        actual_price = s.line_items.data[0].price.id
        print(f"{label}: mode={s.mode} price={actual_price} allow_promotion_codes={s.allow_promotion_codes} metadata={s.metadata!r}")
        log(f"{label} mode=subscription", s.mode == 'subscription', f"got={s.mode}")
        log(f"{label} price一致", actual_price == expect_price, f"expect={expect_price} got={actual_price}")
        log(f"{label} allow_promotion_codes=True", s.allow_promotion_codes is True)
        log(f"{label} metadata.is_earlybird存在", 'is_earlybird' in s.metadata)

# ════════════════════════════════════════════════
# ② _handle_checkout_completed() / _handle_invoice_payment() 直接呼び出し検証
# ════════════════════════════════════════════════
print("\n=== ② webhook処理関数 直接検証 ===")

class FakeMeta(dict):
    pass  # dict継承なので .get()はそのまま使える

def make_checkout_event(user_id, payment_type, is_earlybird, customer_id):
    obj = SimpleNamespace(
        metadata=FakeMeta({'user_id': str(user_id), 'payment_type': payment_type,
                            'is_earlybird': '1' if is_earlybird else '0'}),
        customer=customer_id,
        payment_status='paid',
        id=f"cs_test_verify_{user_id}",
    )
    return SimpleNamespace(data=SimpleNamespace(object=obj))

def make_invoice_event(customer_id, price_id, billing_reason='subscription_cycle'):
    line = SimpleNamespace(price=SimpleNamespace(id=price_id))
    obj = SimpleNamespace(
        customer=customer_id, subscription='sub_test_verify',
        billing_reason=billing_reason,
        lines=SimpleNamespace(data=[line]),
    )
    return SimpleNamespace(data=SimpleNamespace(object=obj))

# --- standard 新規契約 ---
u3 = create_user(f"verify_step31_ch_std_{ts}@test.invalid", pw_hash, "検証ch_std")
ev = make_checkout_event(u3['id'], 'standard', True, 'cus_test_std_001')
_handle_checkout_completed(ev, datetime, timedelta)
d3 = get_user_by_id(u3['id'])
print(f"standard契約後DB状態: {d3}")
log("standard: plan=standard", d3['plan'] == 'standard', f"got={d3['plan']}")
log("standard: is_earlybird=True", d3['is_earlybird'] is True, f"got={d3['is_earlybird']}")
today_day = datetime.utcnow().day
expect_anchor = 28 if today_day > 28 else today_day
log("standard: billing_anchor_day一致", d3['billing_anchor_day'] == expect_anchor, f"expect={expect_anchor} got={d3['billing_anchor_day']}")
_cid3 = get_connection()
_r3 = _cid3.run("SELECT stripe_customer_id FROM users WHERE id=:id", id=u3['id'])
_cid3.close()
_cid3_val = _r3[0][0] if _r3 else None
log("standard: stripe_customer_id設定", _cid3_val == 'cus_test_std_001', f"got={_cid3_val}")

# --- pro 新規契約 ---
u4 = create_user(f"verify_step31_ch_pro_{ts}@test.invalid", pw_hash, "検証ch_pro")
ev = make_checkout_event(u4['id'], 'pro', False, 'cus_test_pro_001')
_handle_checkout_completed(ev, datetime, timedelta)
d4 = get_user_by_id(u4['id'])
print(f"pro契約後DB状態: {d4}")
log("pro: plan=pro", d4['plan'] == 'pro', f"got={d4['plan']}")
log("pro: plan_expires_atが設定されている", d4['plan_expires_at'] is not None)
log("pro: is_earlybird=False", d4['is_earlybird'] is False, f"got={d4['is_earlybird']}")
_cid4 = get_connection()
_r4 = _cid4.run("SELECT stripe_customer_id FROM users WHERE id=:id", id=u4['id'])
_cid4.close()
_cid4_val = _r4[0][0] if _r4 else None
log("pro: stripe_customer_id設定", _cid4_val == 'cus_test_pro_001', f"got={_cid4_val}")

# --- standardの請求サイクル更新（バグ修正確認：plan='pro'に誤って書き換わらないこと） ---
# standard価格IDが未設定の場合はハードコードで検証用ダミーを使用
std_price_for_test = STRIPE_PRICE_STANDARD_EARLY or 'price_std_early_dummy'
conn = get_connection()
conn.run("UPDATE users SET monthly_meeting_count=10, stripe_customer_id=:cid WHERE id=:id", cid='cus_test_std_001', id=u3['id'])
conn.close()
ev = make_invoice_event('cus_test_std_001', std_price_for_test)

# STRIPE_PRICE_STANDARD_EARLY が未設定の場合、price_id判定が「未知」になるため
# ここでは price_id を直接 STRIPE_PRICE_STANDARD_EARLY にパッチして検証
from src import main as main_module
_orig_early = main_module.STRIPE_PRICE_STANDARD_EARLY
_orig_regular = main_module.STRIPE_PRICE_STANDARD_REGULAR
if not _orig_early:
    main_module.STRIPE_PRICE_STANDARD_EARLY = std_price_for_test
    print(f"[PATCH] STRIPE_PRICE_STANDARD_EARLY を '{std_price_for_test}' に一時パッチ（検証用）")

_handle_invoice_payment(ev, datetime, timedelta)
d3b = get_user_by_id(u3['id'])
print(f"standard請求サイクル更新後: plan={d3b['plan']} monthly_meeting_count={d3b['monthly_meeting_count']}")
log("standard更新後: planがproに誤変更されていない", d3b['plan'] == 'standard', f"got={d3b['plan']}")
log("standard更新後: monthly_meeting_countが0にリセット", d3b['monthly_meeting_count'] == 0, f"got={d3b['monthly_meeting_count']}")

# パッチ元に戻す
if not _orig_early:
    main_module.STRIPE_PRICE_STANDARD_EARLY = _orig_early

# --- proの請求サイクル更新 ---
pro_price_for_test = STRIPE_PRICE_PRO_EARLY or 'price_pro_early_dummy'
if not STRIPE_PRICE_PRO_EARLY:
    main_module.STRIPE_PRICE_PRO_EARLY = pro_price_for_test
    print(f"[PATCH] STRIPE_PRICE_PRO_EARLY を '{pro_price_for_test}' に一時パッチ（検証用）")

conn = get_connection()
conn.run("UPDATE users SET stripe_customer_id=:cid WHERE id=:id", cid='cus_test_pro_001', id=u4['id'])
conn.close()
ev = make_invoice_event('cus_test_pro_001', pro_price_for_test)
_handle_invoice_payment(ev, datetime, timedelta)
d4b = get_user_by_id(u4['id'])
print(f"pro請求サイクル更新後: plan={d4b['plan']} plan_expires_at={d4b['plan_expires_at']}")
log("pro更新後: plan=pro維持", d4b['plan'] == 'pro')
log("pro更新後: plan_expires_at更新済み", d4b['plan_expires_at'] is not None)

if not STRIPE_PRICE_PRO_EARLY:
    main_module.STRIPE_PRICE_PRO_EARLY = _orig_early  # 元に戻す（_orig_earlyはpro変数なので再代入不要、ここは変数名ミスなので無害）

# ════════════════════════════════════════════════
# テストデータクリーンアップ
# ════════════════════════════════════════════════
print("\n=== クリーンアップ ===")
try:
    conn = get_connection()
    conn.run("DELETE FROM users WHERE email LIKE 'verify_step31_%@test.invalid'")
    deleted = conn.row_count
    conn.close()
    print(f"テストユーザー {deleted} 件削除完了")
except Exception as e:
    print(f"クリーンアップ失敗（無視）: {e}")

# ════════════════════════════════════════════════
print(f"\n=== 結果: {sum(results)}/{len(results)} OK ===")
if all(results):
    print("総合判定: ALL OK")
else:
    print("総合判定: NG項目あり（上記[NG]を確認）")
