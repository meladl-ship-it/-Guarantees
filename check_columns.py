import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from db_adapter import connect_db

conn = connect_db()
c = conn.cursor()
c.execute('PRAGMA table_info(guarantees)')
columns = [row[1] for row in c.fetchall()]
print("Columns:", columns)
conn.close()