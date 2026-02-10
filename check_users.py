import sys
import os
import sqlite3

# Ensure we can import db_adapter
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from db_adapter import db_path

try:
    path = db_path()
    print(f"DB Path: {path}")
    
    conn = sqlite3.connect(path)
    cursor = conn.cursor()
    
    # Check users table info
    cursor.execute("PRAGMA table_info(users)")
    columns = cursor.fetchall()
    print(f"Users Table Columns: {columns}")
    
    # Check content
    cursor.execute("SELECT * FROM users")
    users = cursor.fetchall()
    print(f"Users: {users}")
    
    conn.close()

except Exception as e:
    print(f"Error: {e}")
