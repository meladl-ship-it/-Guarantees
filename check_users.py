import sqlite3
import os
import sys

with open('users_check_result.txt', 'w', encoding='utf-8') as f:
    f.write(f"Current working directory: {os.getcwd()}\n")
    db_path = 'guarantees.db'
    if not os.path.exists(db_path):
        f.write(f"Database file '{db_path}' not found in current directory.\n")
    else:
        f.write(f"Database file found: {os.path.abspath(db_path)}\n")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
            if not cursor.fetchone():
                f.write("Table 'users' does not exist.\n")
            else:
                cursor.execute("SELECT id, username, email, role, is_approved FROM users")
                users = cursor.fetchall()
                f.write(f"Total users found: {len(users)}\n")
                for u in users:
                    f.write(str(u) + "\n")
        except Exception as e:
            f.write(f"Error: {e}\n")
        conn.close()
