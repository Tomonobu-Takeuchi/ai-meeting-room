import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.database import check_and_use_meeting, get_connection, create_user, get_user_by_id
from datetime import datetime, timedelta
import bcrypt

conn = get_connection()
pw_hash = bcrypt.hashpw(b"Verify123!", bcrypt.gensalt()).decode()
u = create_user(f"verify_pro_unlimited_{int(datetime.utcnow().timestamp())}@test.invalid", pw_hash, "pro無制限確認")
expires = datetime.utcnow() + timedelta(days=30)
conn.run("UPDATE users SET plan='pro', monthly_meeting_count=99, plan_expires_at=:exp WHERE id=:id", exp=expires, id=u['id'])
conn.close()

ok, reason = check_and_use_meeting(u['id'])
d = get_user_by_id(u['id'])
print(f"ok={ok} reason={reason!r} monthly_meeting_count={d['monthly_meeting_count']}")
assert ok is True, "pro無制限が壊れている"
assert d['monthly_meeting_count'] == 100, f"カウントアップされていない: {d['monthly_meeting_count']}"
print("pro無制限: OK")

conn2 = get_connection()
conn2.run("DELETE FROM users WHERE id=:id", id=u['id'])
conn2.close()
