from flask import Flask, render_template, url_for, redirect, session, flash, request, send_file, jsonify
import sys
import os
import io
import traceback
import sqlite3
import shutil
import tempfile
import json
from datetime import datetime, timedelta
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash
# Removed Flask-Mail as per user request

from itsdangerous import URLSafeTimedSerializer

# Load environment variables FIRST
load_dotenv()

# Ensure we can import db_adapter from current directory
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from db_adapter import db_path, connect_db, normalize_query, PSYCOPG2_AVAILABLE, check_and_migrate_db, ensure_db
from reports_handler import ReportsHandler

# Import psycopg2 if available to avoid NameErrors
if PSYCOPG2_AVAILABLE:
    import psycopg2
    import psycopg2.extras
    import psycopg2.extensions

# Ensure DB schema is up to date (add password column if missing)
# For cloud apps, we must ensure tables exist first
try:
    ensure_db()
    check_and_migrate_db()
except Exception as e:
    print(f">>> SYSTEM WARNING: DB Init failed: {e}")

# --- Auto-fix: Ensure admin has the correct email ---
try:
    conn = connect_db()
    cursor = conn.cursor()
    # Check if we are on Postgres or SQLite
    if PSYCOPG2_AVAILABLE and isinstance(conn, psycopg2.extensions.connection):
        # Postgres
        cursor.execute("UPDATE users SET email = %s WHERE username = 'admin'", ('m.eladl@abs-haj.com',))
    else:
        # SQLite
        cursor.execute("UPDATE users SET email = ? WHERE username = 'admin'", ('m.eladl@abs-haj.com',))
    conn.commit()
    conn.close()
    print(">>> SYSTEM: Admin email updated to m.eladl@abs-haj.com")
except Exception as e:
    print(f">>> SYSTEM WARNING: Could not update admin email: {e}")
# ----------------------------------------------------

# Log Database Status for debugging
if os.environ.get('DATABASE_URL'):
    print(">>> SYSTEM STATUS: Configured to use PostgreSQL via DATABASE_URL")
else:
    print(">>> SYSTEM WARNING: DATABASE_URL not found. Using local SQLite (Data will be lost on restart!)")

app = Flask(__name__)
app.secret_key = 'super_secret_key_for_session_management' # Change this in production!

# Mail Configuration REMOVED

serializer = URLSafeTimedSerializer(app.secret_key)

# Initialize Login Manager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'welcome'

# User Class
class User(UserMixin):
    def __init__(self, id, username, email, role, is_approved=1):
        self.id = str(id)
        self.username = username
        self.email = email
        self.role = role
        self.is_approved = is_approved
    
    @staticmethod
    def get(user_id):
        try:
            conn = get_db_connection()
            
            # Configure cursor/factory based on DB type
            is_postgres = PSYCOPG2_AVAILABLE and isinstance(conn, psycopg2.extensions.connection)
            if is_postgres:
                cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            else:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
            sql = normalize_query("SELECT * FROM users WHERE id = ?")
            if is_postgres:
                sql = sql.replace('?', '%s')
            cursor.execute(sql, (user_id,))
            user = cursor.fetchone()
            conn.close()
            if user:
                # Convert sqlite3.Row to dict to ensure .get() works
                if not isinstance(user, dict):
                    user = dict(user)
                    
                return User(
                    id=user['id'], 
                    username=user['username'], 
                    email=user.get('email'), 
                    role=user.get('role', 'user'),
                    is_approved=user.get('is_approved', 1)
                )
        except Exception as e:
            print(f"Error fetching user: {e}")
        return None

    @staticmethod
    def get_by_email(email):
        try:
            conn = get_db_connection()
            
            is_postgres = PSYCOPG2_AVAILABLE and isinstance(conn, psycopg2.extensions.connection)
            if is_postgres:
                cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            else:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
            sql = normalize_query("SELECT * FROM users WHERE email = ?")
            if is_postgres:
                sql = sql.replace('?', '%s')
            cursor.execute(sql, (email,))
            user = cursor.fetchone()
            conn.close()
            
            if user:
                # Convert sqlite3.Row to dict to ensure .get() works
                if not isinstance(user, dict):
                    user = dict(user)
                    
                return User(
                    id=user['id'], 
                    username=user['username'], 
                    email=user.get('email'), 
                    role=user.get('role', 'user'),
                    is_approved=user.get('is_approved', 1)
                )
        except Exception as e:
            print(f"Error fetching user by email: {e}")
        return None

    @staticmethod
    def get_by_username(username):
        try:
            conn = get_db_connection()
            is_postgres = PSYCOPG2_AVAILABLE and isinstance(conn, psycopg2.extensions.connection)
            if is_postgres:
                cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            else:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
            sql = normalize_query("SELECT * FROM users WHERE username = ?")
            if is_postgres:
                sql = sql.replace('?', '%s')
            cursor.execute(sql, (username,))
            user = cursor.fetchone()
            conn.close()
            
            if user:
                # Return dict-like object to access password_hash outside
                # Convert sqlite3.Row to dict to ensure .get() works
                return dict(user)
        except Exception as e:
            print(f"Error fetching user by username: {e}")
        return None

    @staticmethod
    def update_password(user_id, new_password):
        try:
            conn = get_db_connection()
            is_postgres = PSYCOPG2_AVAILABLE and isinstance(conn, psycopg2.extensions.connection)
            
            password_hash = generate_password_hash(new_password)
            sql = normalize_query("UPDATE users SET password_hash = ? WHERE id = ?")
            if is_postgres:
                sql = sql.replace('?', '%s')
            
            cursor = conn.cursor()
            cursor.execute(sql, (password_hash, user_id))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Error updating password: {e}")
            return False

    @staticmethod
    def create(username, email, role='user', password=None, is_approved=0):
        try:
            conn = get_db_connection()
            
            is_postgres = PSYCOPG2_AVAILABLE and isinstance(conn, psycopg2.extensions.connection)
            if is_postgres:
                cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            else:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
            
            password_hash = generate_password_hash(password) if password else None
            
            sql = normalize_query("INSERT INTO users (username, email, role, password_hash, is_approved) VALUES (?, ?, ?, ?, ?)")
            if is_postgres:
                sql = sql.replace('?', '%s')
            cursor.execute(sql, (username, email, role, password_hash, is_approved))
            
            # Handle fetching ID for new user
            if is_postgres:
                # For Postgres, fetch the ID by email since lastrowid isn't reliable/supported the same way
                sql_id = normalize_query("SELECT id FROM users WHERE email = ?")
                if is_postgres:
                    sql_id = sql_id.replace('?', '%s')
                cursor.execute(sql_id, (email,))
                row = cursor.fetchone()
                user_id = row[0] if row else None
            else:
                user_id = cursor.lastrowid
                
            conn.commit()
            conn.close()
            return User(id=user_id, username=username, email=email, role=role, is_approved=is_approved)
        except Exception as e:
            print(f"Error creating user: {e}")
        return None

    @staticmethod
    def update(user_id, username=None, email=None, role=None, password=None, is_approved=None):
        try:
            conn = get_db_connection()
            is_postgres = PSYCOPG2_AVAILABLE and isinstance(conn, psycopg2.extensions.connection)
            if is_postgres:
                cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            else:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

            updates = []
            params = []
            
            if username:
                updates.append("username = ?")
                params.append(username)
            if email:
                updates.append("email = ?")
                params.append(email)
            if role:
                updates.append("role = ?")
                params.append(role)
            if password:
                updates.append("password_hash = ?")
                params.append(generate_password_hash(password))
            if is_approved is not None:
                updates.append("is_approved = ?")
                params.append(is_approved)
            
            if not updates:
                return False
                
            params.append(user_id)
            sql = normalize_query(f"UPDATE users SET {', '.join(updates)} WHERE id = ?")
            
            if is_postgres:
                sql = sql.replace('?', '%s')
                
            cursor.execute(sql, tuple(params))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Error updating user: {e}")
            return False

    @staticmethod
    def delete(user_id):
        try:
            conn = get_db_connection()
            is_postgres = PSYCOPG2_AVAILABLE and isinstance(conn, psycopg2.extensions.connection)
            if is_postgres:
                cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            else:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

            sql = normalize_query("DELETE FROM users WHERE id = ?")
            if is_postgres:
                sql = sql.replace('?', '%s')
                
            cursor.execute(sql, (user_id,))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Error deleting user: {e}")
            return False

    @staticmethod
    def get_all():
        try:
            conn = get_db_connection()
            is_postgres = PSYCOPG2_AVAILABLE and isinstance(conn, psycopg2.extensions.connection)
            if is_postgres:
                cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            else:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
            cursor.execute("SELECT * FROM users ORDER BY username")
            rows = cursor.fetchall()
            conn.close()
            
            users = []
            for row in rows:
                u = dict(row)
                users.append(User(
                    id=u['id'], 
                    username=u['username'], 
                    email=u.get('email'), 
                    role=u.get('role', 'user'),
                    is_approved=u.get('is_approved', 1)
                ))
            return users
        except Exception as e:
            print(f"Error fetching all users: {e}")
            return []

@login_manager.user_loader
def load_user(user_id):
    return User.get(user_id)

def get_db_connection():
    # Use centralized adapter which handles local SQLite vs Cloud Postgres
    return connect_db()

# Create tables if they don't exist
with app.app_context():
    try:
        # Note: db_path check is only valid for local SQLite. 
        # For cloud, we assume DB exists or let connect_db handle creation.
        if not (os.environ.get('DATABASE_URL') and PSYCOPG2_AVAILABLE):
            # Ensure DB exists by triggering connection (which creates it if needed for SQLite)
            connect_db().close()

        conn = get_db_connection()
        
        # Ensure default admin user exists
        admin_user = User.get_by_username('admin')
        if not admin_user:
            print("Creating default admin user...")
            User.create('admin', 'admin@example.com', 'admin', 'admin')
            
    except Exception as e:
        print(f"Error checking DB: {e}")

@app.route('/debug')
def debug_info():
    return f"""
    <h1>Debug Info</h1>
    <p>Host: {request.host}</p>
    <p>Base URL: {request.base_url}</p>
    <p>Remote Addr: {request.remote_addr}</p>
    """

@app.route('/test-email')
def test_email_route():
    # REMOVED PER USER REQUEST
    return "Email functionality has been disabled."

@app.route('/')
def welcome():
    return render_template('welcome.html', user=current_user)

import hashlib

def check_legacy_hash(stored_hash, password):
    # Try simple SHA256 (common in older systems)
    try:
        if len(stored_hash) == 64:
            # Assume SHA256
            if hashlib.sha256(password.encode()).hexdigest() == stored_hash:
                return True
    except:
        pass
    return False

# Global debug log for login attempts (InMemory)
login_attempts_log = []

@app.route('/forgot-password')
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('forgot_password.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        
        # Check if user already exists
        if User.get_by_username(username) or User.get_by_email(email):
            flash('اسم المستخدم أو البريد الإلكتروني مسجل بالفعل', 'danger')
        else:
            # Create user with is_approved=0 (Pending)
            # Default role is 'user'
            new_user = User.create(username, email, 'user', password, is_approved=0)
            if new_user:
                flash('تم تسجيل حسابك بنجاح! يرجى انتظار موافقة المسؤول لتفعيل الحساب.', 'success')
                return redirect(url_for('login'))
            else:
                flash('حدث خطأ أثناء التسجيل. يرجى المحاولة مرة أخرى.', 'danger')
                
    return render_template('register.html')

@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
        
    try:
        email = serializer.loads(token, salt='password-reset-salt', max_age=3600)
    except:
        flash('الرابط غير صالح أو منتهي الصلاحية.', 'danger')
        return redirect(url_for('forgot_password'))
        
    if request.method == 'POST':
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        if password != confirm_password:
            flash('كلمتا المرور غير متطابقتين.', 'danger')
            return render_template('reset_password.html')
            
        # Try to find user by email first
        # Note: 'email' variable here comes from serializer.loads() above
        user_data = User.get_by_email(email)
        
        # If email was a placeholder (e.g. admin@system.local), try to extract username
        if not user_data and "@system.local" in email:
             username = email.split('@')[0]
             user_data = User.get_by_username(username)
             
        if user_data:
            # Update password
            # Handle dict vs object
            user_id = user_data['id'] if isinstance(user_data, dict) else user_data.id
            
            if User.update_password(user_id, password):
                flash('تم تغيير كلمة المرور بنجاح. يمكنك تسجيل الدخول الآن.', 'success')
                return redirect(url_for('welcome'))
            else:
                flash('حدث خطأ أثناء تحديث كلمة المرور.', 'danger')
        else:
            flash('المستخدم غير موجود.', 'danger')
            
    return render_template('reset_password.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        # Debug logging
        try:
            import datetime
            log_entry = {
                'time': str(datetime.datetime.now()),
                'username_input': f"'{username}'",
                'password_len': len(password) if password else 0,
                'password_preview': password[:2] + '***' if password else 'None',
            }
        except:
            log_entry = {'error': 'logging_failed'}

        user_data = User.get_by_username(username)
        log_entry['user_found'] = bool(user_data)
        
        valid_login = False
        if user_data and user_data.get('password_hash'):
            h = user_data['password_hash']
            log_entry['hash_preview'] = h[:10] + '...'
            
            # Try standard Werkzeug hash
            try:
                if check_password_hash(h, password):
                    valid_login = True
                    log_entry['check_result'] = 'True'
                else:
                    log_entry['check_result'] = 'False'
            except Exception as e:
                log_entry['check_error'] = str(e)
                
            # Fallback for legacy hashes (e.g. raw SHA256)
            if not valid_login and check_legacy_hash(h, password):
                valid_login = True
                log_entry['legacy_check'] = 'True'
                
        login_attempts_log.append(log_entry)
        # Keep only last 10
        if len(login_attempts_log) > 10:
            login_attempts_log.pop(0)

        if valid_login:
            user = User(id=user_data['id'], 
                       username=user_data['username'], 
                       email=user_data.get('email'), 
                       role=user_data.get('role', 'user'),
                       is_approved=user_data.get('is_approved', 1))
            
            # Check approval status
            if not user.is_approved:
                flash('الحساب قيد المراجعة من قبل المسؤول.', 'warning')
                return render_template('welcome.html')

            login_user(user)
            return redirect(url_for('dashboard'))
        else:
            flash('اسم المستخدم أو كلمة المرور غير صحيحة', 'danger')
            
    return render_template('welcome.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('welcome'))

@app.route('/debug/users')
def debug_users():
    # TEMPORARY DEBUG ROUTE
    try:
        import werkzeug
        from werkzeug.security import check_password_hash
        
        conn = get_db_connection()
        if PSYCOPG2_AVAILABLE and isinstance(conn, psycopg2.extensions.connection):
            cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        else:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
        cursor.execute("SELECT * FROM users")
        rows = cursor.fetchall()
        conn.close()
        
        # Safe version check
        w_ver = getattr(werkzeug, '__version__', 'unknown')
        
        html = f"<h1>Debug Users (Werkzeug {w_ver})</h1>"
        html += f"<p><a href='/debug/login_attempts'>View Login Attempts Log</a></p>"
        html += "<ul>"
        for r in rows:
            u = dict(r)
            h = u.get('password_hash', '')
            # Test hash for admin
            is_valid = "N/A"
            if u.get('username') == 'admin':
                try:
                    is_valid = check_password_hash(h, 'admin')
                except Exception as e:
                    is_valid = f"Error: {e}"
            
            html += f"<li>User: {u.get('username')} | Role: {u.get('role')} | Hash: {h[:20]}...{h[-10:] if h and len(h)>20 else ''} (Len: {len(h) if h else 0}) | Valid('admin'): {is_valid}</li>"
        html += "</ul>"
        return html
    except Exception as e:
        return f"Error: {e}"

@app.route('/debug/login_attempts')
def debug_login_attempts():
    try:
        html = "<h1>Login Attempts Log</h1><ul>"
        for entry in reversed(login_attempts_log):
            html += f"<li>{entry}</li>"
        html += "</ul>"
        return html
    except Exception as e:
        return f"Error: {e}"

@app.route('/api/sync', methods=['POST'])
def sync_data():
    # Ensure DB exists and is migrated before processing sync
    # This covers cases where startup hook failed or filesystem is ephemeral
    try:
        ensure_db()
    except Exception as e:
        print(f"Error ensuring DB in sync: {e}")

    api_key = request.headers.get('X-API-Key')
    # Use fallback API key if not set in environment (matches local .env default)
    server_key = os.environ.get('API_KEY', 'bb16e983-3950-4b9a-8aa0-a7f9d0f2ac32')
    if api_key != server_key:
        return json.dumps({'error': 'Unauthorized'}), 401

    data = request.json
    if not data or 'guarantees' not in data:
        return json.dumps({'error': 'Invalid data'}), 400

    guarantees_list = data.get('guarantees', [])
    users_list = data.get('users', [])
    bank_limits_list = data.get('bank_limits', [])
    
    print(f"DEBUG SYNC: Received {len(users_list)} users.")
    for u in users_list:
        h = u.get('password_hash', '')
        print(f" - Sync User: {u.get('username')} HashPrefix: {h[:20]}...")
    
    conn = connect_db()
    try:
        if PSYCOPG2_AVAILABLE and isinstance(conn, psycopg2.extensions.connection):
            cursor = conn.cursor()
            
            # --- Sync Guarantees ---
            if guarantees_list:
                # Delete existing data to ensure full sync
                cursor.execute("TRUNCATE TABLE guarantees RESTART IDENTITY")
                
                # Batch insert
                columns = [
                    "id", "department", "bank", "g_no", "g_type", "amount", 
                    "insurance_amount", "percent", "beneficiary", "requester", 
                    "project_name", "issue_date", "end_date", "user_status", 
                    "cash_flag", "attachment", "delivery_status", "recipient_name", 
                    "notes", "entry_number"
                ]
                
                # Check data integrity (handle ID casing or missing ID)
                if guarantees_list:
                    # First pass: Fix casing for ALL items and check ID validity
                    valid_ids_count = 0
                    for g in guarantees_list:
                        # Fix ID casing if needed
                        if 'id' not in g and 'ID' in g:
                            g['id'] = g.pop('ID')
                        
                        if g.get('id') is not None:
                            valid_ids_count += 1

                    # If ANY ID is missing/None, we must remove 'id' column from insertion to let DB auto-increment
                    # This avoids the "null value in column id" error.
                    # Ideally we want to preserve IDs, but safety first.
                    if valid_ids_count < len(guarantees_list):
                        if 'id' in columns:
                            columns.remove('id')
                            print(f"Warning: Removed 'id' from sync columns because {len(guarantees_list) - valid_ids_count} records have null/missing IDs.")
                
                # Build query
                cols_str = ", ".join([f'"{c}"' for c in columns]) # Quote columns for safety
                vals_str = ", ".join(["%s"] * len(columns))
                query = f"INSERT INTO guarantees ({cols_str}) VALUES ({vals_str})"
                
                for g in guarantees_list:
                    # Prepare values tuple, matching columns order
                    # Handle missing keys safely
                    vals = tuple(g.get(c) for c in columns)
                    cursor.execute(query, vals)
            
            # --- Sync Users ---
            if users_list:
                # Instead of updating existing users, we only insert NEW users.
                # If a user already exists (by username), we DO NOTHING (preserve their current state).
                
                user_columns = ["username", "password_hash", "pass_hash", "role", "active", "email"]
                
                cols_str = ", ".join([f'"{c}"' for c in user_columns])
                vals_str = ", ".join(["%s"] * len(user_columns))
                
                # Postgres INSERT ON CONFLICT DO NOTHING
                query = f"""
                    INSERT INTO users ({cols_str}) VALUES ({vals_str})
                    ON CONFLICT (username) DO NOTHING
                """
                
                for u in users_list:
                    if not u.get('username'): continue
                    vals = tuple(u.get(c) for c in user_columns)
                    cursor.execute(query, vals)
            
            # --- Sync Bank Limits ---
            if bank_limits_list:
                # Create table if not exists (for Postgres, though db_adapter should handle it, we want to be safe)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS bank_limits (
                        id SERIAL PRIMARY KEY,
                        bank_name TEXT NOT NULL UNIQUE,
                        limit_amount REAL DEFAULT 0.0
                    )
                """)
                cursor.execute("TRUNCATE TABLE bank_limits RESTART IDENTITY")
                
                bl_columns = ["bank_name", "limit_amount"]
                cols_str = ", ".join([f'"{c}"' for c in bl_columns])
                vals_str = ", ".join(["%s"] * len(bl_columns))
                query = f"INSERT INTO bank_limits ({cols_str}) VALUES ({vals_str})"
                
                for bl in bank_limits_list:
                    vals = tuple(bl.get(c) for c in bl_columns)
                    cursor.execute(query, vals)

        else:
            # SQLite
            cursor = conn.cursor()
            
            # --- Sync Guarantees ---
            if guarantees_list:
                cursor.execute("DELETE FROM guarantees")
                
                columns = [
                    "id", "department", "bank", "g_no", "g_type", "amount", 
                    "insurance_amount", "percent", "beneficiary", "requester", 
                    "project_name", "issue_date", "end_date", "user_status", 
                    "cash_flag", "attachment", "delivery_status", "recipient_name", 
                    "notes", "entry_number"
                ]
                
                cols_str = ", ".join([f'"{c}"' for c in columns])
                vals_str = ", ".join(["?"] * len(columns))
                query = f"INSERT INTO guarantees ({cols_str}) VALUES ({vals_str})"
                
                for g in guarantees_list:
                    vals = tuple(g.get(c) for c in columns)
                    cursor.execute(query, vals)
            
            # --- Sync Users ---
            if users_list:
                # SQLite Logic: Insert New Only (Ignore Existing)
                
                # First, get existing usernames to skip them
                cursor.execute("SELECT username FROM users")
                existing_usernames = {row[0] for row in cursor.fetchall()}
                
                user_columns = ["username", "password_hash", "pass_hash", "role", "active", "email"]
                cols_str = ", ".join([f'"{c}"' for c in user_columns])
                vals_str = ", ".join(["?"] * len(user_columns))
                
                query = f"INSERT INTO users ({cols_str}) VALUES ({vals_str})"
                
                for u in users_list:
                    username = u.get('username')
                    if not username: continue
                    
                    if username in existing_usernames:
                        continue # Skip existing user
                    else:
                        # Insert new user
                        vals = tuple(u.get(c) for c in user_columns)
                        cursor.execute(query, vals)
                     
            # --- Sync Bank Limits ---
            if bank_limits_list:
                # Ensure table exists
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS bank_limits (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        bank_name TEXT UNIQUE,
                        limit_amount REAL DEFAULT 0.0
                    )
                """)
                cursor.execute("DELETE FROM bank_limits")
                
                bl_columns = ["bank_name", "limit_amount"]
                cols_str = ", ".join([f'"{c}"' for c in bl_columns])
                vals_str = ", ".join(["?"] * len(bl_columns))
                query = f"INSERT INTO bank_limits ({cols_str}) VALUES ({vals_str})"
                
                for bl in bank_limits_list:
                    vals = tuple(bl.get(c) for c in bl_columns)
                    cursor.execute(query, vals)
                
        conn.commit()
        return json.dumps({
            'status': 'success', 
            'count_guarantees': len(guarantees_list), 
            'count_users': len(users_list),
            'count_bank_limits': len(bank_limits_list)
        }), 200
        
    except Exception as e:
        conn.rollback()
        print(f"Sync Error: {e}")
        return json.dumps({'error': str(e)}), 500
    finally:
        conn.close()

@app.route('/dashboard')
@login_required
def dashboard():
    return index_logic(view_type='dashboard')

@app.route('/data')
@login_required
def data_table():
    return index_logic(view_type='table')

# --- Bank Limits Logic ---
ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

def normalize_gno(g_no):
    n = (g_no or "").strip().upper()
    n = n.translate(ARABIC_DIGITS)
    n = n.replace(" ", "").replace("-", "").replace("/", "")
    return n

def detect_bank_from_gno(g_no):
    n = normalize_gno(g_no)
    raw = (g_no or "").strip().upper().translate(ARABIC_DIGITS)
    
    if n == "B299015":
        return "الأهلي مطارات الرياض"
        
    markers = ["ATNHTS", "APNHTS", "APNGCU", "ATNGCU", "AFGGCU", "GST", "AFGWPM", "APNWPM", "ATNCBG", "APNCBG", "GIC"]
    if any(m and (m in n) for m in markers):
        return "ساب"
        
    if "OGTE" in n:
        return "الراجحي"
        
    if ("JLG" in n) or ("RLG" in n):
        return "الرياض"
        
    if "MD" in n:
        return "الإنماء"
        
    try:
        if ("B" in raw) or ("M" in raw):
            return "الأهلي"
    except:
        pass
        
    return ""

def normalize_bank(b, g_no):
    b = (b or "").strip()
    
    if normalize_gno(g_no) == "B299015":
        return "الأهلي مطارات الرياض"
        
    if "مطارات الرياض" in b or "الأهلي مطارات الرياض" in b or "الاهلي مطارات الرياض" in b:
        return "الأهلي مطارات الرياض"
    if any(x in b for x in ("الاهلي", "الأهلي", "الاهلي ")):
        return "الأهلي"
    if "ساب" in b:
        return "ساب"
    if "الراجحي" in b:
        return "الراجحي"
    if "الرياض" in b:
        return "الرياض"
    if "الإنماء" in b or "الانماء" in b:
        return "الإنماء"
        
    auto = detect_bank_from_gno(g_no)
    if auto:
        return auto
        
    return b or ""

@app.route('/bank-limits')
@login_required
def bank_limits():
    try:
        conn = get_db_connection()
        if PSYCOPG2_AVAILABLE and isinstance(conn, psycopg2.extensions.connection):
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        else:
            conn.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
            cursor = conn.cursor()
            
        # Fetch guarantees
        cursor.execute("SELECT * FROM guarantees")
        rows = cursor.fetchall()
        
        # Fetch limits
        limits_data = {}
        try:
            # Ensure table exists (for SQLite locally it might be created by desktop app, for Postgres we might need to check)
            # We'll just try to select.
            cursor.execute("SELECT bank_name, limit_amount FROM bank_limits")
            for row in cursor.fetchall():
                # Handle dictionary access depending on row factory
                if isinstance(row, dict):
                    limits_data[row['bank_name']] = float(row['limit_amount'] or 0.0)
                else:
                    # Fallback if something weird happens with factory (e.g. SQLite Row)
                    limits_data[row[0]] = float(row[1] or 0.0)
        except Exception as e:
            print(f"Note: bank_limits table might not exist or empty: {e}")
            
        conn.close()
        
        # Process data
        bank_data = {}
        today = datetime.now()
        today = datetime(today.year, today.month, today.day)
        
        allowed_statuses = ("ساري", "قارب على الانتهاء", "انتهى في انتظار التأكيد", "ضمان غير مسجل")
        
        for r in rows:
            raw_status = (r.get('user_status') or '').strip()
            # Exclude cash
            is_cash = (r.get('cash_flag') == 1)
            if is_cash: continue
            
            # Determine effective status
            display_status = raw_status
            if display_status == '' or display_status == 'ساري':
                display_status = 'ساري'
                end_date_str = r.get('end_date')
                if end_date_str:
                    try:
                        end_date = datetime.strptime(str(end_date_str), '%Y-%m-%d')
                        days_left = (end_date - today).days
                        if 0 <= days_left <= 30:
                            display_status = 'قارب على الانتهاء'
                        elif days_left < 0:
                            display_status = 'انتهى في انتظار التأكيد'
                    except:
                        pass
            
            if display_status not in allowed_statuses:
                continue
                
            # Normalize bank
            bname = normalize_bank(r.get('bank'), r.get('g_no'))
            if not bname: continue
            
            if bname not in bank_data:
                bank_data[bname] = {"existing": 0.0, "unregistered": 0.0}
                
            try:
                amt = float(r.get('amount') or 0.0)
            except:
                amt = 0.0
                
            if display_status == 'ضمان غير مسجل':
                bank_data[bname]["unregistered"] += amt
            else:
                bank_data[bname]["existing"] += amt
                
        # Prepare table data
        table_data = []
        # Include banks from limits even if they have no guarantees? 
        # guarantees.py doesn't, but it might be better UI. 
        # Let's union keys.
        all_banks = set(bank_data.keys()) | set(limits_data.keys())
        
        for bank_name in sorted(all_banks):
            if bank_name not in bank_data:
                data = {"existing": 0.0, "unregistered": 0.0}
            else:
                data = bank_data[bank_name]
                
            limit = limits_data.get(bank_name, 0.0)
            existing = data["existing"]
            unregistered = data["unregistered"]
            total = existing + unregistered
            remaining = max(0.0, limit - total)
            usage_pct = (total / limit * 100.0) if limit > 0 else 0.0
            
            table_data.append({
                "bank": bank_name,
                "limit": limit,
                "existing": existing,
                "unregistered": unregistered,
                "total": total,
                "remaining": remaining,
                "usage_pct": usage_pct
            })
            
        return render_template('bank_limits.html', data=table_data, today_date=today.strftime('%Y-%m-%d'))
        
    except Exception as e:
        print(f"Error in bank_limits: {e}")
        traceback.print_exc()
        flash('حدث خطأ أثناء جلب بيانات حدود البنوك', 'danger')
        return redirect(url_for('dashboard'))

def index_logic(view_type='dashboard'):
    try:
        # Note: db_path check is only valid for local SQLite. 
        # For cloud, we assume DB exists or let connect_db handle creation.
        if not (os.environ.get('DATABASE_URL') and PSYCOPG2_AVAILABLE):
            # Ensure DB exists by triggering connection (which creates it if needed for SQLite)
            connect_db().close()

        conn = get_db_connection()
        
        # Configure cursor/factory
        if PSYCOPG2_AVAILABLE and isinstance(conn, psycopg2.extensions.connection):
            # RealDictCursor returns actual dicts, supporting .get()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        else:
            # SQLite: Use lambda to create dicts
            conn.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
            cursor = conn.cursor()
        
        # جلب كافة البيانات من جدول الضمانات
        cursor.execute("SELECT * FROM guarantees ORDER BY id DESC")
        rows = cursor.fetchall()
        conn.close()

        # === تحضير البيانات ===
        
        active_rows = []
        processed_rows = []
        today = datetime.now()
        today = datetime(today.year, today.month, today.day) # Strip time for accurate day calculation
        today_str = today.strftime('%Y-%m-%d')
        
        for r in rows:
            # تحويل الصف إلى قاموس قابل للتعديل إذا لزم الأمر
            if not isinstance(r, dict):
                r = dict(r)

            # تطبيع الحالة: تحويل القيمة الفارغة إلى نص فارغ
            raw_status = (r.get('user_status') or '').strip()
            # استبعاد الضمانات النقدية (cash_flag = 1) بناء على طلب المستخدم
            is_cash = (r.get('cash_flag') == 1)
            
            # تحديد الحالة
            is_expired = (raw_status in ['منتهي', 'مسترد'])
            
            # منطق تحديد الحالة للعرض (Status Chart & Table)
            display_status = raw_status
            
            # 1. معالجة الحالة الفارغة أو 'ساري' للتحقق من "قارب على الانتهاء"
            if display_status == '' or display_status == 'ساري':
                display_status = 'ساري' # الافتراضي
                
                end_date_str = r.get('end_date')
                if end_date_str:
                    try:
                        # محاولة تحليل التاريخ (المتوقع yyyy-MM-dd)
                        end_date = datetime.strptime(str(end_date_str), '%Y-%m-%d')
                        days_left = (end_date - today).days
                        
                        # منطق قارب على الانتهاء: متبقي 30 يوم أو أقل (وليس منتهي)
                        if 0 <= days_left <= 30:
                            display_status = 'قارب على الانتهاء'
                        # منطق انتهى في انتظار التأكيد (ضمني): التاريخ انتهى ولكن الحالة لم تُحدث
                        elif days_left < 0:
                            display_status = 'انتهى في انتظار التأكيد'
                    except:
                        pass # في حال فشل تحليل التاريخ، يبقى 'ساري'
            
            # 2. ضمان أن 'ضمان غير مسجل' يظهر كما هو
            elif display_status == 'ضمان غير مسجل':
                pass 
                
            # تخزين الحالة المحسوبة للعرض
            r['display_status'] = display_status
            
            # إضافة للصفوف المعالجة (للجدول)
            processed_rows.append(r)

            # الشرط: نستبعد 'منتهي' فقط، ونشمل الكل (نقدي، ساري، غير مسجل، انتظار تأكيد) للإحصائيات
            if not is_expired:
                active_rows.append(r)
        
        # 2. الإجماليات الرئيسية
        total_count = len(rows) # العدد الكلي المطلق
        net_active_count = len(active_rows)
        net_total_amount = sum(r['amount'] for r in active_rows if r['amount'] is not None)
        
        # تفصيل السارية (نقدي vs تسهيلات)
        active_cash_rows = [r for r in active_rows if r.get('cash_flag') == 1]
        active_credit_rows = [r for r in active_rows if r.get('cash_flag') != 1]
        
        active_cash_count = len(active_cash_rows)
        active_cash_amount = sum(r['amount'] for r in active_cash_rows if r['amount'] is not None)
        
        active_credit_count = len(active_credit_rows)
        active_credit_amount = sum(r['amount'] for r in active_credit_rows if r['amount'] is not None)
        
        if view_type == 'table':
            # Pass all guarantees to table (filtering handled in UI)
            table_rows = processed_rows
            
            # Extract unique values for filters (sorted)
            departments = sorted(list(set(r.get('department') or '' for r in table_rows if r.get('department'))))
            banks = sorted(list(set(r.get('bank') or '' for r in table_rows if r.get('bank'))))
            statuses = sorted(list(set(r.get('display_status') or '' for r in table_rows if r.get('display_status'))))
            g_types = sorted(list(set(r.get('g_type') or '' for r in table_rows if r.get('g_type'))))
            
            return render_template('table.html', 
                                 guarantees=table_rows, 
                                 today_date=today_str,
                                 departments=departments,
                                 banks=banks,
                                 statuses=statuses,
                                 g_types=g_types)

        # === منطق لوحة الإحصائيات ===
        
        # أ. إحصائيات الحالة (استخدام display_status المحسوبة)
        status_map = {}
        total_status_amount = 0.0
        
        for r in active_rows:
            status = r.get('display_status') or 'غير محدد'
            amount = r.get('amount') or 0.0
            
            if status not in status_map:
                status_map[status] = 0.0
            status_map[status] += amount
            total_status_amount += amount
            
        status_stats = []
        safe_total = total_status_amount or 1.0
        
        for status, amount in status_map.items():
            status_stats.append({
                'name': status,
                'amount': amount,
                'percent': (amount / safe_total) * 100
            })
        
        status_stats.sort(key=lambda x: x['amount'], reverse=True)

        # ب. إحصائيات البنوك (استبعاد النقدي)
        bank_map = {}
        # متغيرات لحساب الإحصائيات المطلوبة (قارب على الانتهاء & انتظار البنك) وتفصيلها نقدي/تسهيلات
        near_expiry_count = 0
        near_expiry_amount = 0.0
        near_expiry_cash_count = 0
        near_expiry_cash_amount = 0.0
        near_expiry_credit_count = 0
        near_expiry_credit_amount = 0.0

        pending_bank_count = 0
        pending_bank_amount = 0.0
        pending_bank_cash_count = 0
        pending_bank_cash_amount = 0.0
        pending_bank_credit_count = 0
        pending_bank_credit_amount = 0.0

        for r in active_rows:
            # حساب الإحصائيات المطلوبة
            status = r.get('display_status')
            amount_val = r.get('amount') or 0.0
            is_cash_item = (r.get('cash_flag') == 1)
            
            if status == 'قارب على الانتهاء':
                near_expiry_count += 1
                near_expiry_amount += amount_val
                
                if is_cash_item:
                    near_expiry_cash_count += 1
                    near_expiry_cash_amount += amount_val
                else:
                    near_expiry_credit_count += 1
                    near_expiry_credit_amount += amount_val
                    
            elif status == 'انتهى في انتظار التأكيد':
                pending_bank_count += 1
                pending_bank_amount += amount_val
                
                if is_cash_item:
                    pending_bank_cash_count += 1
                    pending_bank_cash_amount += amount_val
                else:
                    pending_bank_credit_count += 1
                    pending_bank_credit_amount += amount_val

            # استبعاد النقدي من إحصائيات المبالغ فقط
            if is_cash_item:
                continue
                
            bank = r.get('bank') or 'غير محدد'
            amount = r.get('amount') or 0.0
            if bank not in bank_map:
                bank_map[bank] = 0.0
            bank_map[bank] += amount
            
        bank_stats_list = [{'name': k, 'amount': v} for k, v in bank_map.items()]
        bank_stats_list.sort(key=lambda x: x['amount'], reverse=True)
        bank_stats_top5 = bank_stats_list[:5]
        
        # حساب إجمالي المبالغ (بدون نقدي) لحساب النسب المئوية الصحيحة
        total_amount_non_cash = sum(item['amount'] for item in bank_stats_list) or 1.0
        max_bank_amount = bank_stats_top5[0]['amount'] if bank_stats_top5 else 1.0
        
        for item in bank_stats_top5:
            item['percent'] = (item['amount'] / total_amount_non_cash) * 100
            item['percent_relative'] = (item['amount'] / max_bank_amount) * 100

        # ج. إحصائيات الأقسام (استبعاد النقدي)
        dept_map = {}
        for r in active_rows:
            # استبعاد النقدي من إحصائيات المبالغ فقط
            if r.get('cash_flag') == 1:
                continue

            dept = r.get('department') or 'غير محدد'
            amount = r.get('amount') or 0.0
            
            if dept not in dept_map:
                dept_map[dept] = {'count': 0, 'amount': 0.0}
            dept_map[dept]['count'] += 1
            dept_map[dept]['amount'] += amount
            
        dept_stats = [{'name': k, **v} for k, v in dept_map.items()]
        dept_stats.sort(key=lambda x: x['amount'], reverse=True)
        
        # عدد الضمانات غير النقدية لحساب نسبة العدد
        non_cash_count = sum(item['count'] for item in dept_stats) or 1
        
        for item in dept_stats:
            item['percent_count'] = (item['count'] / non_cash_count) * 100
            
        return render_template('dashboard.html', 
                             total_count=total_count,
                             net_active_count=net_active_count,
                             net_total_amount=net_total_amount,
                             active_cash_count=active_cash_count,
                             active_cash_amount=active_cash_amount,
                             active_credit_count=active_credit_count,
                             active_credit_amount=active_credit_amount,
                             near_expiry_count=near_expiry_count,
                             near_expiry_amount=near_expiry_amount,
                             near_expiry_cash_count=near_expiry_cash_count,
                             near_expiry_cash_amount=near_expiry_cash_amount,
                             near_expiry_credit_count=near_expiry_credit_count,
                             near_expiry_credit_amount=near_expiry_credit_amount,
                             pending_bank_count=pending_bank_count,
                             pending_bank_amount=pending_bank_amount,
                             pending_bank_cash_count=pending_bank_cash_count,
                             pending_bank_cash_amount=pending_bank_cash_amount,
                             pending_bank_credit_count=pending_bank_credit_count,
                             pending_bank_credit_amount=pending_bank_credit_amount,
                             status_stats=status_stats,
                             bank_stats_top5=bank_stats_top5,
                             dept_stats=dept_stats,
                             today_date=today_str)

    except Exception as e:
        error_trace = traceback.format_exc()
        print(f"ERROR: {error_trace}")
        return f"<h1>حدث خطأ أثناء الاتصال بقاعدة البيانات:</h1><p>{e}</p><pre>{error_trace}</pre>"

@app.route('/settings')
@login_required
def settings():
    if current_user.role != 'admin':
        flash('غير مصرح لك بالوصول لهذه الصفحة', 'danger')
        return redirect(url_for('dashboard'))
    
    users = User.get_all()
    return render_template('settings.html', users=users)

@app.route('/settings/users/add', methods=['POST'])
@login_required
def add_user():
    if current_user.role != 'admin':
        flash('غير مصرح لك بهذا الإجراء', 'danger')
        return redirect(url_for('dashboard'))
    
    username = request.form.get('username')
    email = request.form.get('email')
    password = request.form.get('password')
    role = request.form.get('role', 'user')
    
    if not username or not password:
        flash('اسم المستخدم وكلمة المرور مطلوبان', 'warning')
        return redirect(url_for('settings'))
        
    if User.get_by_username(username):
        flash('اسم المستخدم موجود بالفعل', 'warning')
        return redirect(url_for('settings'))
        
    if User.create(username, email, role, password):
        flash('تم إضافة المستخدم بنجاح', 'success')
    else:
        flash('حدث خطأ أثناء إضافة المستخدم', 'danger')
        
    return redirect(url_for('settings'))

@app.route('/settings/users/edit/<user_id>', methods=['POST'])
@login_required
def edit_user(user_id):
    if current_user.role != 'admin':
        flash('غير مصرح لك بهذا الإجراء', 'danger')
        return redirect(url_for('dashboard'))
    
    username = request.form.get('username')
    email = request.form.get('email')
    password = request.form.get('password')
    role = request.form.get('role')
    
    if not username:
        flash('اسم المستخدم مطلوب', 'warning')
        return redirect(url_for('settings'))
        
    if User.update(user_id, username, email, role, password if password else None):
        flash('تم تحديث بيانات المستخدم بنجاح', 'success')
    else:
        flash('حدث خطأ أثناء تحديث المستخدم', 'danger')
        
    return redirect(url_for('settings'))

@app.route('/settings/users/delete/<user_id>', methods=['POST'])
@login_required
def delete_user(user_id):
    if current_user.role != 'admin':
        flash('غير مصرح لك بهذا الإجراء', 'danger')
        return redirect(url_for('dashboard'))
        
    if user_id == current_user.id:
        flash('لا يمكنك حذف حسابك الحالي', 'warning')
        return redirect(url_for('settings'))
        
    if User.delete(user_id):
        flash('تم حذف المستخدم بنجاح', 'success')
    else:
        flash('حدث خطأ أثناء حذف المستخدم', 'danger')
        
    return redirect(url_for('settings'))

@app.route('/settings/users/approve/<user_id>', methods=['POST'])
@login_required
def approve_user(user_id):
    if current_user.role != 'admin':
        flash('غير مصرح لك بهذا الإجراء', 'danger')
        return redirect(url_for('dashboard'))
        
    if User.update(user_id, is_approved=1):
        flash('تم تفعيل حساب المستخدم بنجاح', 'success')
    else:
        flash('حدث خطأ أثناء تفعيل المستخدم', 'danger')
        
    return redirect(url_for('settings'))

@app.route('/reports')
@login_required
def reports():
    try:
        conn = get_db_connection()
        if PSYCOPG2_AVAILABLE and isinstance(conn, psycopg2.extensions.connection):
            cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        else:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
        # Get distinct departments that have active guarantees
        cursor.execute("SELECT DISTINCT department FROM guarantees WHERE department IS NOT NULL AND department != ''")
        rows = cursor.fetchall()
        
        depts = []
        for r in rows:
            d = r['department'] if isinstance(r, dict) else r[0]
            if d:
                depts.append(d)
        
        depts.sort()
        conn.close()
        
        return render_template('reports.html', departments=depts)
    except Exception as e:
        print(f"Error fetching departments: {e}")
        flash('حدث خطأ أثناء جلب الأقسام', 'danger')
        return redirect(url_for('dashboard'))

@app.route('/reports/download/<path:dept_name>')
@login_required
def download_report(dept_name):
    try:
        # Generate report to memory
        output = io.BytesIO()
        
        success = ReportsHandler.generate_word_for_dept(dept_name, output)
        
        if success:
            output.seek(0)
            safe_dept = dept_name.replace('/', '-').replace('\\', '-')
            filename = f"Report_{safe_dept}_{datetime.now().strftime('%Y-%m-%d')}.docx"
            
            return send_file(
                output,
                as_attachment=True,
                download_name=filename,
                mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            )
        else:
            flash(f'لا توجد بيانات للقسم: {dept_name}', 'warning')
            return redirect(url_for('reports'))
            
    except Exception as e:
        print(f"Error generating report: {e}")
        flash(f'حدث خطأ أثناء إنشاء التقرير: {e}', 'danger')
        return redirect(url_for('reports'))

# === إدارة الضمانات (إضافة/تعديل/حذف) ===

@app.route('/guarantees/add', methods=['POST'])
@login_required
def add_guarantee():
    try:
        # استلام البيانات من النموذج
        data = request.form
        
        g_no = data.get('g_no')
        if not g_no:
            flash('رقم الضمان مطلوب', 'warning')
            return redirect(url_for('data_table'))

        bank = data.get('bank')
        department = data.get('department')
        g_type = data.get('g_type')
        amount = data.get('amount')
        beneficiary = data.get('beneficiary')
        project_name = data.get('project_name')
        issue_date = data.get('issue_date')
        end_date = data.get('end_date')
        user_status = data.get('user_status', 'ساري')
        
        # New fields
        insurance_amount = data.get('insurance_amount')
        percent = data.get('percent')
        requester = data.get('requester')
        notes = data.get('notes')
        entry_number = data.get('entry_number')
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # التحقق من تكرار رقم الضمان
        try:
            # استعلام الإدخال
            query = """
                INSERT INTO guarantees (
                    g_no, bank, department, g_type, amount, beneficiary, 
                    project_name, issue_date, end_date, user_status,
                    insurance_amount, percent, requester, notes, entry_number
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            
            # تعديل الاستعلام لـ Postgres
            if PSYCOPG2_AVAILABLE and isinstance(conn, psycopg2.extensions.connection):
                query = query.replace('?', '%s')
                
            cursor.execute(query, (
                g_no, bank, department, g_type, amount, beneficiary, 
                project_name, issue_date, end_date, user_status,
                insurance_amount, percent, requester, notes, entry_number
            ))
            
            conn.commit()
            conn.close()
            flash('تم إضافة الضمان بنجاح', 'success')
            
        except sqlite3.IntegrityError:
            conn.close()
            flash('رقم الضمان موجود بالفعل', 'danger')
        except psycopg2.errors.UniqueViolation:
            conn.rollback()
            conn.close()
            flash('رقم الضمان موجود بالفعل', 'danger')
            
    except Exception as e:
        print(f"Error adding guarantee: {e}")
        flash('حدث خطأ أثناء إضافة الضمان', 'danger')
        
    return redirect(url_for('data_table'))

@app.route('/guarantees/edit/<int:id>', methods=['POST'])
@login_required
def edit_guarantee(id):
    try:
        data = request.form
        
        # الحقول القابلة للتعديل
        g_no = data.get('g_no')
        bank = data.get('bank')
        department = data.get('department')
        g_type = data.get('g_type')
        amount = data.get('amount')
        beneficiary = data.get('beneficiary')
        project_name = data.get('project_name')
        issue_date = data.get('issue_date')
        end_date = data.get('end_date')
        user_status = data.get('user_status')
        
        # New fields
        insurance_amount = data.get('insurance_amount')
        percent = data.get('percent')
        requester = data.get('requester')
        notes = data.get('notes')
        entry_number = data.get('entry_number')
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        query = """
            UPDATE guarantees SET 
                g_no=?, bank=?, department=?, g_type=?, amount=?, 
                beneficiary=?, project_name=?, issue_date=?, end_date=?, user_status=?,
                insurance_amount=?, percent=?, requester=?, notes=?, entry_number=?
            WHERE id=?
        """
        
        if PSYCOPG2_AVAILABLE and isinstance(conn, psycopg2.extensions.connection):
            query = query.replace('?', '%s')
            
        cursor.execute(query, (
            g_no, bank, department, g_type, amount, beneficiary, 
            project_name, issue_date, end_date, user_status,
            insurance_amount, percent, requester, notes, entry_number, id
        ))
        
        conn.commit()
        conn.close()
        flash('تم تحديث الضمان بنجاح', 'success')
        
    except Exception as e:
        print(f"Error editing guarantee: {e}")
        flash('حدث خطأ أثناء تحديث الضمان', 'danger')
        
    return redirect(url_for('data_table'))

@app.route('/guarantees/delete/<int:id>', methods=['POST'])
@login_required
def delete_guarantee(id):
    if current_user.role != 'admin':
        flash('غير مصرح لك بالحذف', 'danger')
        return redirect(url_for('data_table'))
        
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        query = "DELETE FROM guarantees WHERE id=?"
        if PSYCOPG2_AVAILABLE and isinstance(conn, psycopg2.extensions.connection):
            query = query.replace('?', '%s')
            
        cursor.execute(query, (id,))
        conn.commit()
        conn.close()
        flash('تم حذف الضمان بنجاح', 'success')
        
    except Exception as e:
        print(f"Error deleting guarantee: {e}")
        flash('حدث خطأ أثناء حذف الضمان', 'danger')
        
    return redirect(url_for('data_table'))

@app.route('/guarantees/bulk_action', methods=['POST'])
@login_required
def bulk_action():
    if current_user.role != 'admin':
        return jsonify({'success': False, 'message': 'غير مصرح لك بهذا الإجراء'}), 403

    try:
        data = request.get_json()
        action = data.get('action')
        ids = data.get('ids', [])

        if not ids and action != 'deselect_all': # deselect_all is client side usually, but just in case
            return jsonify({'success': False, 'message': 'لم يتم تحديد أي ضمانات'}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        if action == 'delete':
            # SQLite handles placeholders differently than Postgres if we construct query manually
            # But we can use executemany or constructing IN clause
            placeholders = ','.join(['?' for _ in ids])
            query = f"DELETE FROM guarantees WHERE id IN ({placeholders})"
            
            if PSYCOPG2_AVAILABLE and isinstance(conn, psycopg2.extensions.connection):
                query = query.replace('?', '%s')
                
            cursor.execute(query, ids)
            conn.commit()
            message = f'تم حذف {cursor.rowcount} ضمان/ضمانات بنجاح'

        elif action == 'to_file':
            placeholders = ','.join(['?' for _ in ids])
            query = f"UPDATE guarantees SET user_status = ? WHERE id IN ({placeholders})"
            params = ['ملف'] + ids
            
            if PSYCOPG2_AVAILABLE and isinstance(conn, psycopg2.extensions.connection):
                query = query.replace('?', '%s')
                
            cursor.execute(query, params)
            conn.commit()
            message = f'تم تحويل {cursor.rowcount} ضمان/ضمانات إلى ملف'

        elif action == 'clear_status': # "مسح" (Clear user_status / Auto)
            placeholders = ','.join(['?' for _ in ids])
            query = f"UPDATE guarantees SET user_status = ? WHERE id IN ({placeholders})"
            params = [''] + ids
            
            if PSYCOPG2_AVAILABLE and isinstance(conn, psycopg2.extensions.connection):
                query = query.replace('?', '%s')
                
            cursor.execute(query, params)
            conn.commit()
            message = f'تم مسح الحالة (تحويل لتلقائي) لـ {cursor.rowcount} ضمان/ضمانات'

        else:
            conn.close()
            return jsonify({'success': False, 'message': 'إجراء غير معروف'}), 400

        conn.close()
        return jsonify({'success': True, 'message': message})

    except Exception as e:
        print(f"Error in bulk action: {e}")
        return jsonify({'success': False, 'message': f'حدث خطأ: {str(e)}'}), 500


if __name__ == '__main__':
    print("جاري تشغيل الموقع...")
    print("الرابط الأساسي: http://127.0.0.1")
    print("رابط بديل: http://sagan.irc.com")
    # For production use, debug should be False.
    # Host 0.0.0.0 allows access from other devices on the network.
    # Port 80 is the default HTTP port (no number needed in URL).
    # NOTE: Running on port 80 might require Administrator privileges on Windows.
    try:
        app.run(debug=False, port=80, host='0.0.0.0')
    except PermissionError:
        print("ERROR: Permission denied for port 80. Please run as Administrator.")
        print("Fallback to port 5000...")
        app.run(debug=False, port=5000, host='0.0.0.0')