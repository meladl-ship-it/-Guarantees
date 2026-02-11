import sys
import os
import sqlite3
from werkzeug.security import generate_password_hash

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from db_adapter import db_path, check_and_migrate_db

try:
    # Ensure schema is up to date
    check_and_migrate_db()
    
    path = db_path()
    print(f"Connecting to DB: {path}")
    
    conn = sqlite3.connect(path)
    cursor = conn.cursor()
    
    new_hash = generate_password_hash('admin')
    
    cursor.execute("SELECT id FROM users WHERE username = 'admin'")
    row = cursor.fetchone()
    
    if row:
        print("Updating admin...")
        cursor.execute("UPDATE users SET password_hash = ?, email = 'admin@example.com', role = 'admin', active = 1 WHERE username = 'admin'", (new_hash,))
    else:
        print("Creating admin...")
        cursor.execute("INSERT INTO users (username, password_hash, email, role, active) VALUES (?, ?, ?, ?, ?)", 
                      ('admin', new_hash, 'admin@example.com', 'admin', 1))
                      
    conn.commit()
    print("SUCCESS: Password for 'admin' is set to 'admin'")
    conn.close()
    
except Exception as e:
    print(f"ERROR: {e}")
