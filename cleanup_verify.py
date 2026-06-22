import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from src.database import get_connection
conn = get_connection()
rows = conn.run("SELECT id, email, stripe_customer_id FROM users WHERE email LIKE 'verify_step31_%'")
print("残存テストユーザー:")
for r in rows:
    print(" ", r)
conn.run("DELETE FROM users WHERE email LIKE 'verify_step31_%'")
print(f"削除件数: {conn.row_count}")
conn.close()
