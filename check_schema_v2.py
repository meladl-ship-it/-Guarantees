import sys
import os
import sqlite3

# Add current directory to path
sys.path.append(os.getcwd())

try:
    from db_adapter import db_path
    path = db_path()
    print(f"DB Path: {path}")
    
    if os.path.exists(path):
        conn = sqlite3.connect(path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(users)")
        columns = cursor.fetchall()
        print("Users table columns:")
        for col in columns:
            print(col)
        conn.close()
    else:
        print("DB file does not exist at path.")
except Exception as e:
    print(f"Error: {e}")
