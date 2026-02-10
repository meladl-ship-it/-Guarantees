# -*- coding: utf-8 -*-
"""
دعم قاعدة البيانات لنظام إدارة الضمانات
"""

import sqlite3
import sys
import os
from typing import Optional, Union, Any
from PyQt5 import QtCore

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
    try:
        s = QtCore.QSettings("GuaranteesApp", "Main")
        custom_dir = s.value("db/dir", type=str)
    except Exception:
        custom_dir = None
    base = Path(custom_dir) if (custom_dir or "").strip() else base_default
    if not _is_writable_dir(base):
        base = base_default
        try:
            s = QtCore.QSettings("GuaranteesApp", "Main")
            s.setValue("db/dir", str(base))
        except Exception:
            pass
        try:
            base.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
    return str(base / "guarantees.db")


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
    conn = sqlite3.connect(db_path(), timeout=10.0, check_same_thread=False)
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
