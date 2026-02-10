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
        else:
            # SQLite
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(users)")
            columns = [info[1] for info in cursor.fetchall()]
            if 'password_hash' not in columns:
                cursor.execute("ALTER TABLE users ADD COLUMN password_hash TEXT")
                conn.commit()
                print("Migrated: Added password_hash to users table (SQLite)")
                
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
    initialize_new = False
    
    # Ensure directory exists (critical for cloud deployment)
    try:
        db_dir = os.path.dirname(db_file)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
            print(f"Created database directory: {db_dir}")
    except Exception as e:
        print(f"Error creating database directory: {e}")

    if not os.path.exists(db_file):
        initialize_new = True
        
    conn = sqlite3.connect(db_file, timeout=10.0, check_same_thread=False)
    
    if initialize_new:
        try:
            # Create basic schema if DB is new
            # Users table (Updated to include password_hash)
            conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                role TEXT DEFAULT 'user',
                password_hash TEXT
            )
            ''')
            # Guarantees table
            conn.execute('''
            CREATE TABLE IF NOT EXISTS guarantees (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                g_no TEXT UNIQUE,
                beneficiary TEXT,
                amount REAL,
                currency TEXT,
                start_date TEXT,
                end_date TEXT,
                bank TEXT,
                department TEXT,
                user_status TEXT,
                notes TEXT,
                cash_flag INTEGER DEFAULT 0,
                type TEXT
            )
            ''')
            conn.commit()
            print(f"Initialized new database at {db_file}")
        except Exception as e:
            print(f"Error initializing database: {e}")

    try:
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
    except Exception:
        # Pragmas are best-effort; continue even if any fails
        pass
    return conn


def get_db_type():
    """Get the current database type being used."""
    if os.environ.get('DATABASE_URL') and PSYCOPG2_AVAILABLE:
        return "postgres"
    return "sqlite"


def is_centralized_db():
    """Check if centralized database is being used."""
    return get_db_type() == "postgres"


def get_placeholder():
    """Return the parameter placeholder for the current DB type."""
    return "%s" if get_db_type() == "postgres" else "?"


def normalize_query(query: str) -> str:
    """Replace '?' with '%s' if using PostgreSQL."""
    if get_db_type() == "postgres":
        return query.replace("?", "%s")
    return query


def execute_query(query: str, params: Optional[tuple] = None, fetch: bool = False):
    # Execute a database query with automatic connection management.
    conn = connect_db()
    
    # Normalize query for the active DB connection
    is_postgres = False
    if PSYCOPG2_AVAILABLE:
         is_postgres = isinstance(conn, psycopg2.extensions.connection)

    final_query = query
    if is_postgres:
        final_query = query.replace("?", "%s")
    
    try:
        if is_postgres:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        else:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
        if params:
            cursor.execute(final_query, params)
        else:
            cursor.execute(final_query)
            
        if fetch:
            result = cursor.fetchall()
            conn.commit()
            return result
        conn.commit()
        return None
    except Exception:
        conn.rollback()
        raise
    finally:
        try:
            conn.close()
        except:
            pass
