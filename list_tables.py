import pg8000.native
conn = pg8000.native.Connection(host='localhost', user='postgres', password='localpass', database='ai_meeting', port=6300)
result = conn.run("SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name")
for r in result:
    print(r[0])
