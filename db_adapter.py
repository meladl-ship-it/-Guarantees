# -*- coding: utf-8 -*-
"""
دعم قاعدة البيانات لنظام إدارة الضمانات
"""

import sqlite3
import sys
import os
from typing import Optional, Union, Any

# Try importing PyQt5, but don't fail if it's missing (Web/Headless mode)
try:
    from PyQt5 import QtCore
    QT_AVAILABLE = True
except ImportError:
    QT_AVAILABLE = False

# Try importing psycopg2 for PostgreSQL support
try:
    import psycopg2
    import psycopg2.extras
    import psycopg2.extensions
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False

def normalize_query(query: str) -> str:
    """Normalize search query by converting wildcard '*' to 'OR' logic for multi-term search."""
    if not query:
        return ""
    # If contains '*', replace with OR logic structure if needed, or just return as is for custom handling
    # For now, we'll keep it simple as a utility function
    return query.strip()

# Original SQLite functions
def db_path():
    r"""Return a valid, writable DB path.
    """
    # SQLite logic
    from pathlib import Path
    
    def _is_writable_dir(p: Path) -> bool:
        try:
            p.mkdir(parents=True, exist_ok=True)
            import tempfile, os
            tf = p / (".__writable_" + next(iter("xy")))
            with open(tf, "w", encoding="utf-8") as f:
                f.write("ok")
            try:
                os.remove(str(tf))
            except Exception:
                pass
            return True
        except Exception:
            return False

    base_default = Path.home() / "Documents" / "Guarantees"
    
    # If running in a web environment (no Qt or headless), use a local 'data' folder
    if not QT_AVAILABLE or os.environ.get('RENDER') or os.environ.get('WEBSITE_HOSTNAME'):
        # Web server mode: use 'data' directory in current project
        base = Path(__file__).parent / "data"
        try:
            base.mkdir(exist_ok=True)
        except:
            pass
        return str(base / "guarantees.db")

    try:
        if QT_AVAILABLE:
            s = QtCore.QSettings("GuaranteesApp", "Main")
            custom_dir = s.value("db/dir", type=str)
        else:
            custom_dir = None
    except Exception:
        custom_dir = None
    base = Path(custom_dir) if (custom_dir or "").strip() else base_default
    if not _is_writable_dir(base):
        base = base_default
        try:
            if QT_AVAILABLE:
                s = QtCore.QSettings("GuaranteesApp", "Main")
                s.setValue("db/dir", str(base))
        except Exception:
            pass
        try:
            base.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
    return str(base / "guarantees.db")


def check_and_migrate_db():
    """Ensure database schema is up to date."""
    conn = connect_db()
    try:
        # Check if password_hash column exists in users table
        is_postgres = PSYCOPG2_AVAILABLE and isinstance(conn, psycopg2.extensions.connection)
        
        if is_postgres:
            cursor = conn.cursor()
            cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name='users' AND column_name='password_hash'")
            if not cursor.fetchone():
                cursor.execute("ALTER TABLE users ADD COLUMN password_hash TEXT")
                conn.commit()
                print("Migrated: Added password_hash to users table (Postgres)")

            # Check if email column exists
            cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name='users' AND column_name='email'")
            if not cursor.fetchone():
                cursor.execute("ALTER TABLE users ADD COLUMN email TEXT")
                conn.commit()
                print("Migrated: Added email to users table (Postgres)")
        else:
            # SQLite
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(users)")
            columns = [info[1] for info in cursor.fetchall()]
            if 'password_hash' not in columns:
                cursor.execute("ALTER TABLE users ADD COLUMN password_hash TEXT")
                conn.commit()
                print("Migrated: Added password_hash to users table (SQLite)")
            
            if 'email' not in columns:
                cursor.execute("ALTER TABLE users ADD COLUMN email TEXT")
                conn.commit()
                print("Migrated: Added email to users table (SQLite)")
                
    except Exception as e:
        print(f"Migration error: {e}")
    finally:
        try:
            conn.close()
        except:
            pass

def connect_db():
    """Create a database connection.
    
    Returns:
        Database connection object (sqlite3.Connection or psycopg2.extensions.connection)
    """
    # Check for DATABASE_URL environment variable (common in cloud hosting)
    database_url = os.environ.get('DATABASE_URL')
    
    if database_url and PSYCOPG2_AVAILABLE:
        try:
            conn = psycopg2.connect(database_url, sslmode='require')
            return conn
        except Exception as e:
            print(f"Error connecting to PostgreSQL: {e}")
            pass

    # SQLite connection
    db_file = db_path()
    
    # Initialize DB if missing (for cloud/web environment)
    # We rely on ensure_db being called explicitly, but for robustness:
    initialize_new = False
    
    # Ensure directory exists (critical for cloud deployment)
    try:
        db_dir = os.path.dirname(db_file)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
            # print(f"Created database directory: {db_dir}")
    except Exception as e:
        print(f"Error creating database directory: {e}")

    if not os.path.exists(db_file):
        initialize_new = True
        
    conn = sqlite3.connect(db_file, timeout=10.0, check_same_thread=False)
    
    if initialize_new:
        # We can call ensure_db() here, but connect_db is called BY ensure_db, so avoid recursion.
        # We'll let the caller handle schema creation via ensure_db()
        pass

    try:
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
    except Exception:
        # Pragmas are best-effort; continue even if any fails
        pass
    return conn

def ensure_db():
    """Ensure all database tables exist and are up-to-date."""
    conn = connect_db()
    try:
        c = conn.cursor()
        
        is_postgres = PSYCOPG2_AVAILABLE and isinstance(conn, psycopg2.extensions.connection)
        
        # Define types based on DB
        if is_postgres:
            pk_type = "SERIAL PRIMARY KEY"
        else:
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
                email TEXT
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

        conn.commit()
        
        # Run migrations to ensure columns exist (for SQLite)
        if not is_postgres:
            try:
                # Guarantees columns
                cols = [r[1] for r in c.execute("PRAGMA table_info(guarantees)").fetchall()]
                if "delivery_status" not in cols:
                    c.execute("ALTER TABLE guarantees ADD COLUMN delivery_status TEXT")
                if "recipient_name" not in cols:
                    c.execute("ALTER TABLE guarantees ADD COLUMN recipient_name TEXT")
                if "notes" not in cols:
                    c.execute("ALTER TABLE guarantees ADD COLUMN notes TEXT")
                if "entry_number" not in cols:
                    c.execute("ALTER TABLE guarantees ADD COLUMN entry_number TEXT")
                if "attachment" not in cols:
                    c.execute("ALTER TABLE guarantees ADD COLUMN attachment TEXT")
                
                # Attachments columns
                cols = [r[1] for r in c.execute("PRAGMA table_info(attachments)").fetchall()]
                if "notes" not in cols:
                    c.execute("ALTER TABLE attachments ADD COLUMN notes TEXT")
                    
                # Users columns
                cols = [r[1] for r in c.execute("PRAGMA table_info(users)").fetchall()]
                if "email" not in cols:
                    c.execute("ALTER TABLE users ADD COLUMN email TEXT")

                conn.commit()
            except Exception:
                pass

        # Use the existing check_and_migrate_db for users table
        check_and_migrate_db()
        
    except Exception as e:
        print(f"Error in ensure_db: {e}")
    finally:
        try:
            conn.close()
        except:
            pass
