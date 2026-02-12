import os
import shutil
import sqlite3

SOURCE_DIR = os.getcwd()
DEST_DIR = os.path.join(SOURCE_DIR, "نسخة 1")

IGNORE_DIRS = {".git", "__pycache__", "venv", "env", ".idea", "نسخة 1", "data"}
IGNORE_FILES = {"guarantees.db", "create_copy.py"}

def copy_project():
    print(f"Copying files from {SOURCE_DIR} to {DEST_DIR}...")
    
    for root, dirs, files in os.walk(SOURCE_DIR):
        # Filter dirs in-place
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        
        # Calculate relative path
        rel_path = os.path.relpath(root, SOURCE_DIR)
        
        # Determine destination directory
        dest_root = os.path.join(DEST_DIR, rel_path)
        
        if not os.path.exists(dest_root):
            os.makedirs(dest_root)
            
        for file in files:
            if file in IGNORE_FILES:
                continue
            if file.endswith(".db"):
                continue
                
            src_file = os.path.join(root, file)
            dest_file = os.path.join(dest_root, file)
            
            try:
                shutil.copy2(src_file, dest_file)
            except Exception as e:
                print(f"Failed to copy {src_file}: {e}")

def create_empty_db():
    db_path = os.path.join(DEST_DIR, "guarantees.db")
    print(f"Creating empty database at {db_path}...")
    
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    # Schema from db_adapter.py
    pk_type = "INTEGER PRIMARY KEY AUTOINCREMENT"
    
    # 1. Guarantees Table
    c.execute(
        f"""CREATE TABLE IF NOT EXISTS guarantees (
            id {pk_type},
            department TEXT, bank TEXT, g_no TEXT UNIQUE,
            g_type TEXT, amount REAL, insurance_amount REAL, percent REAL,
            beneficiary TEXT, requester TEXT, project_name TEXT,
            issue_date TEXT, end_date TEXT,
            user_status TEXT, cash_flag INTEGER DEFAULT 0, attachment TEXT,
            delivery_status TEXT, recipient_name TEXT, notes TEXT, entry_number TEXT
        )"""
    )
    
    # 2. Users Table
    c.execute(
        f"""CREATE TABLE IF NOT EXISTS users (
            id {pk_type},
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT,
            pass_hash TEXT,
            role TEXT DEFAULT 'user',
            active INTEGER DEFAULT 1,
            email TEXT,
            is_approved INTEGER DEFAULT 0
        )"""
    )
    
    # 3. Attachments Table
    c.execute(f"""CREATE TABLE IF NOT EXISTS attachments (
                    id {pk_type},
                    g_no TEXT NOT NULL,
                    path TEXT NOT NULL,
                    notes TEXT
                )""")

    # 4. Loans Table
    c.execute(
        f"""CREATE TABLE IF NOT EXISTS loans (
            id {pk_type},
            loan_type TEXT,
            principal REAL,
            outstanding REAL,
            start_date TEXT,
            end_date TEXT,
            duration_days INTEGER,
            rate_percent REAL,
            cybor_percent REAL,
            total_percent REAL,
            period_interest REAL,
            total_due REAL,
            sector TEXT
        )"""
    )
    
    # 5. Bank Limits Table
    c.execute(f"""CREATE TABLE IF NOT EXISTS bank_limits (
                    id {pk_type},
                    bank_name TEXT UNIQUE NOT NULL,
                    limit_amount REAL DEFAULT 0.0
                )""")
    
    # Add default admin user
    # Using a simple default or just leaving it empty?
    # Usually better to have at least one admin to log in.
    # Based on memory, default is admin/admin
    # But I should probably leave it empty if the goal is to import backup?
    # The user said "ready to import backup", which implies the backup will restore users too.
    # However, having a clean slate is safer.
    
    conn.commit()
    conn.close()
    print("Database created successfully.")

if __name__ == "__main__":
    copy_project()
    create_empty_db()
    print("Done!")
