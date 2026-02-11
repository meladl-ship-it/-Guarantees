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

    try:
        # Get columns
        cursor.execute("PRAGMA table_info(users)")
        columns = [row[1] for row in cursor.fetchall()] # row[1] is name in pragma output
        print(f"User Table Columns: {columns}")

        # Get sample data
        cursor.execute("SELECT * FROM users")
        rows = cursor.fetchall()
        print(f"Total Users: {len(rows)}")
        for row in rows:
            if isinstance(row, sqlite3.Row):
                print(f"User: {dict(row)}")
            else:
                # Tuple fallback
                print(f"User (tuple): {row}")
                
    except Exception as e:
        print(f"Error inspecting DB: {e}")

    conn.close()

if __name__ == "__main__":
    inspect_users()