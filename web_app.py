from flask import Flask, render_template, url_for, redirect, session, flash, request
import sys
import os
import traceback
import sqlite3
import shutil
import tempfile
import json
from datetime import datetime, timedelta
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from authlib.integrations.flask_client import OAuth
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash

# Ensure we can import db_adapter from current directory
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from db_adapter import db_path, connect_db, normalize_query, PSYCOPG2_AVAILABLE, check_and_migrate_db

# Ensure DB schema is up to date (add password column if missing)
check_and_migrate_db()

if PSYCOPG2_AVAILABLE:
    import psycopg2.extras

# Load environment variables
load_dotenv()

# Allow OAuth over HTTP for local testing
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

app = Flask(__name__)
app.secret_key = 'super_secret_key_for_session_management' # Change this in production!

# OAuth Configuration
def load_google_credentials():
    """Try to load Google credentials from env vars or client_secret.json"""
    client_id = os.getenv('GOOGLE_CLIENT_ID', 'YOUR_GOOGLE_CLIENT_ID_HERE')
    client_secret = os.getenv('GOOGLE_CLIENT_SECRET', 'YOUR_GOOGLE_CLIENT_SECRET_HERE')
    
    # Check if we have a client_secret.json file
    json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'client_secret.json')
    if (client_id.startswith('YOUR_GOOGLE') or client_secret.startswith('YOUR_GOOGLE')) and os.path.exists(json_path):
        try:
            with open(json_path, 'r') as f:
                data = json.load(f)
                # Handle both "web" and "installed" formats
                creds = data.get('web') or data.get('installed')
                if creds:
                    client_id = creds.get('client_id', client_id)
                    client_secret = creds.get('client_secret', client_secret)
                    print("DEBUG: Loaded Google credentials from client_secret.json")
        except Exception as e:
            print(f"ERROR: Failed to load client_secret.json: {e}")
            
    return client_id, client_secret

GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET = load_google_credentials()

app.config['GOOGLE_CLIENT_ID'] = GOOGLE_CLIENT_ID
app.config['GOOGLE_CLIENT_SECRET'] = GOOGLE_CLIENT_SECRET
app.config['GOOGLE_DISCOVERY_URL'] = "https://accounts.google.com/.well-known/openid-configuration"

# Check if we are in Mock/Dev mode
# Consider it mock if it still has default placeholders
cid = app.config['GOOGLE_CLIENT_ID']
MOCK_OAUTH = (
    cid.startswith('YOUR_GOOGLE') or 
    cid.startswith('PUT_YOUR') or 
    'your-project-id' in cid
)

if MOCK_OAUTH:
    print(f"WARNING: Google Client ID appears to be a placeholder ({cid[:15]}...). Dev Mode enabled.")
else:
    print(f"INFO: Google Client ID loaded ({cid[:10]}...). Standard OAuth enabled.")

# Initialize Login Manager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'welcome'

# Initialize OAuth
oauth = OAuth(app)
google = oauth.register(
    name='google',
    client_id=app.config['GOOGLE_CLIENT_ID'],
    client_secret=app.config['GOOGLE_CLIENT_SECRET'],
    server_metadata_url=app.config['GOOGLE_DISCOVERY_URL'],
    client_kwargs={
        'scope': 'openid email profile'
    }
)

# User Class
class User(UserMixin):
    def __init__(self, id, username, email, role):
        self.id = str(id)
        self.username = username
        self.email = email
        self.role = role
    
    @staticmethod
    def get(user_id):
        try:
            conn = get_db_connection()
            
            # Configure cursor/factory based on DB type
            if PSYCOPG2_AVAILABLE and isinstance(conn, psycopg2.extensions.connection):
                cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            else:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
            sql = normalize_query("SELECT * FROM users WHERE id = ?")
            cursor.execute(sql, (user_id,))
            user = cursor.fetchone()
            conn.close()
            if user:
                return User(id=user['id'], username=user['username'], email=user['email'], role=user['role'])
        except Exception as e:
            print(f"Error fetching user: {e}")
        return None

    @staticmethod
    def get_by_email(email):
        try:
            conn = get_db_connection()
            
            if PSYCOPG2_AVAILABLE and isinstance(conn, psycopg2.extensions.connection):
                cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            else:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
            cursor.execute(normalize_query("SELECT * FROM users WHERE email = ?"), (email,))
            user = cursor.fetchone()
            conn.close()
            
            if user:
                return User(id=user['id'], username=user['username'], email=user['email'], role=user['role'])
        except Exception as e:
            print(f"Error fetching user by email: {e}")
        return None

    @staticmethod
    def get_by_username(username):
        try:
            conn = get_db_connection()
            if PSYCOPG2_AVAILABLE and isinstance(conn, psycopg2.extensions.connection):
                cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            else:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
            cursor.execute(normalize_query("SELECT * FROM users WHERE username = ?"), (username,))
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
    def create(username, email, role='user', password=None):
        try:
            conn = get_db_connection()
            
            if PSYCOPG2_AVAILABLE and isinstance(conn, psycopg2.extensions.connection):
                cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            else:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
            
            password_hash = generate_password_hash(password) if password else None
            
            cursor.execute(normalize_query("INSERT INTO users (username, email, role, password_hash) VALUES (?, ?, ?, ?)"), 
                         (username, email, role, password_hash))
            
            # Handle fetching ID for new user
            if PSYCOPG2_AVAILABLE and isinstance(conn, psycopg2.extensions.connection):
                # For Postgres, fetch the ID by email since lastrowid isn't reliable/supported the same way
                cursor.execute(normalize_query("SELECT id FROM users WHERE email = ?"), (email,))
                row = cursor.fetchone()
                user_id = row[0] if row else None
            else:
                user_id = cursor.lastrowid
                
            conn.commit()
            conn.close()
            return User(id=user_id, username=username, email=email, role=role)
        except Exception as e:
            print(f"Error creating user: {e}")
        return None

@login_manager.user_loader
def load_user(user_id):
    if user_id == 'dev_mode_user_id':
        return User(id='dev_mode_user_id', username='مطور النظام (Dev)', email='dev@gmail.com', role='admin')
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
    <p>Google Client ID: {app.config.get('GOOGLE_CLIENT_ID')[:10]}...</p>
    """

@app.route('/')
def welcome():
    # Pass mock status to template
    return render_template('welcome.html', user=current_user, mock_oauth=MOCK_OAUTH)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user_data = User.get_by_username(username)
        
        if user_data and user_data.get('password_hash') and check_password_hash(user_data['password_hash'], password):
            user = User(id=user_data['id'], username=user_data['username'], email=user_data['email'], role=user_data['role'])
            login_user(user)
            return redirect(url_for('dashboard'))
        else:
            flash('اسم المستخدم أو كلمة المرور غير صحيحة', 'danger')
            
    return render_template('welcome.html', mock_oauth=MOCK_OAUTH)

@app.route('/login/google')
def login_google():
    if MOCK_OAUTH:
        # Mock login for development/demo when keys are missing
        # This solves the "invalid_client" error by bypassing Google
        print("WARNING: Using Mock Login because Google Keys are missing.")
        
        # Bypass Database for Dev Mode to avoid locking issues
        user = User(id='dev_mode_user_id', username='مطور النظام (Dev)', email='dev@gmail.com', role='admin')
            
        print(f"DEBUG: Logging in user: {user.username} ({user.id})")
        login_user(user)
        return redirect(url_for('dashboard'))

    # Dynamic redirect_uri based on the actual request
    # This ensures it matches exactly what's in the browser (port 80 or 5000)
    # url_for('authorize', _external=True) would also work, but manual construction is clearer for debugging
    scheme = request.scheme
    host = request.host
    redirect_uri = f"{scheme}://{host}/authorize"

    print(f"DEBUG: Sending redirect_uri to Google: {redirect_uri}")
    
    return google.authorize_redirect(redirect_uri)

@app.route('/authorize')
def authorize():
    try:
        token = google.authorize_access_token()
        user_info = token.get('userinfo')
        if not user_info:
            # Fallback if userinfo not in token
            resp = google.get('https://www.googleapis.com/oauth2/v3/userinfo')
            user_info = resp.json()
            
        email = user_info.get('email')
        name = user_info.get('name') or email.split('@')[0]
        
        # Check if user exists
        user = User.get_by_email(email)
        if not user:
            # Create new user automatically
            user = User.create(username=name, email=email)
        
        if user:
            login_user(user)
            return redirect(url_for('dashboard'))
        else:
            return "Failed to create or login user."
            
    except Exception as e:
        traceback.print_exc()
        return f"Authorization failed: {e}"

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('welcome'))

@app.route('/dashboard')
@login_required
def dashboard():
    return index_logic(view_type='dashboard')

@app.route('/data')
@login_required
def data_table():
    return index_logic(view_type='table')

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
        today = datetime.now()
        today = datetime(today.year, today.month, today.day) # Strip time for accurate day calculation
        today_str = today.strftime('%Y-%m-%d')
        
        for r in rows:
            # تطبيع الحالة: تحويل القيمة الفارغة إلى نص فارغ
            raw_status = (r.get('user_status') or '').strip()
            # استبعاد الضمانات النقدية (cash_flag = 1) بناء على طلب المستخدم
            is_cash = (r.get('cash_flag') == 1)
            
            # تحديد الحالة
            is_expired = (raw_status == 'منتهي')
            is_pending = (raw_status == 'انتهى في انتظار التأكيد')
            
            # الشرط: نستبعد 'منتهي' فقط، ونشمل الكل (نقدي، ساري، غير مسجل، انتظار تأكيد)
            if not is_expired:
                
                # منطق تحديد الحالة للعرض (Status Chart)
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
                active_rows.append(r)
        
        # 2. الإجماليات الرئيسية
        total_count = len(rows) # العدد الكلي المطلق
        net_active_count = len(active_rows)
        net_total_amount = sum(r['amount'] for r in active_rows if r['amount'] is not None)
        
        if view_type == 'table':
            return render_template('table.html', 
                                 guarantees=rows, 
                                 today_date=today_str)

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
        # متغيرات لحساب الإحصائيات المطلوبة (قارب على الانتهاء & انتظار البنك)
        near_expiry_count = 0
        near_expiry_amount = 0.0
        pending_bank_count = 0
        pending_bank_amount = 0.0

        for r in active_rows:
            # حساب الإحصائيات المطلوبة
            status = r.get('display_status')
            amount_val = r.get('amount') or 0.0
            
            if status == 'قارب على الانتهاء':
                near_expiry_count += 1
                near_expiry_amount += amount_val
            elif status == 'انتهى في انتظار التأكيد':
                pending_bank_count += 1
                pending_bank_amount += amount_val

            # استبعاد النقدي من إحصائيات المبالغ فقط
            if r.get('cash_flag') == 1:
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
                             near_expiry_count=near_expiry_count,
                             near_expiry_amount=near_expiry_amount,
                             pending_bank_count=pending_bank_count,
                             pending_bank_amount=pending_bank_amount,
                             status_stats=status_stats,
                             bank_stats_top5=bank_stats_top5,
                             dept_stats=dept_stats,
                             today_date=today_str)

    except Exception as e:
        error_trace = traceback.format_exc()
        print(f"ERROR: {error_trace}")
        return f"<h1>حدث خطأ أثناء الاتصال بقاعدة البيانات:</h1><p>{e}</p><pre>{error_trace}</pre>"

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