import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from db_adapter import connect_db

conn = connect_db()
c = conn.cursor()
c.execute('SELECT DISTINCT g_type FROM guarantees')
print("Types:", c.fetchall())
c.execute('SELECT DISTINCT user_status FROM guarantees')
print("Statuses:", c.fetchall())
conn.close()