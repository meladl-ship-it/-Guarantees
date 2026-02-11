import sqlite3
import os
import sys

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from db_adapter import connect_db, db_path

def inspect_users():
    print(f"Using DB Path: {db_path()}")
    
    conn = connect_db()
    
    # Check if it's sqlite or postgres (it should be sqlite locally)
    try:
        conn.row_factory = sqlite3.Row
    except:
        pass
        
    cursor = conn.cursor()

    cursor.execute("PRAGMA table_info(users)")
    columns = cursor.fetchall()
    print("\nColumns:")
    for col in columns:
        print(col)

    print("\nUsers Data:")
    cursor.execute("SELECT id, username, password_hash, role FROM users")
    users = cursor.fetchall()
    for user in users:
        print(f"ID: {user[0]}, User: {user[1]}, Role: {user[3]}")
        print(f"Hash: {user[2]}")
        print("-" * 50)
    
    conn.close()

if __name__ == "__main__":
    inspect_users()