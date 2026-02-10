from flask import Flask, render_template, url_for, redirect, session, flash, request
import sys
import os
import traceback
import sqlite3
import shutil
import tempfile
import json
import openpyxl
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
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

app = Flask(__name__)
app.secret_key = 'super_secret_key_for_session_management' # Change this in production!

# Initialize Login Manager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'welcome'

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

@app.route('/')
def welcome():
    return render_template('welcome.html', user=current_user)

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
            
    return render_template('welcome.html')

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

@app.route('/import', methods=['GET', 'POST'])
@login_required
def import_excel():
    # Only admin should import data
    if current_user.role != 'admin':
        flash('غير مصرح لك بالقيام بهذا الإجراء', 'danger')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        if 'file' not in request.files:
            flash('لم يتم اختيار ملف', 'danger')
            return redirect(request.url)
        
        file = request.files['file']
        if file.filename == '':
            flash('لم يتم اختيار ملف', 'danger')
            return redirect(request.url)
            
        if file and (file.filename.endswith('.xlsx') or file.filename.endswith('.xls')):
            try:
                # Save file securely
                filename = secure_filename(file.filename)
                temp_dir = tempfile.gettempdir()
                file_path = os.path.join(temp_dir, filename)
                file.save(file_path)
                
                # Process Excel
                wb = openpyxl.load_workbook(file_path, data_only=True)
                ws = wb.active
                
                headers = {}
                success_count = 0
                update_count = 0
                
                conn = get_db_connection()
                
                # Configure cursor
                if PSYCOPG2_AVAILABLE and isinstance(conn, psycopg2.extensions.connection):
                    cursor = conn.cursor()
                else:
                    cursor = conn.cursor()
                
                for i, row in enumerate(ws.iter_rows(values_only=True)):
                    if i == 0:
                        # Header mapping
                        for idx, cell in enumerate(row):
                            if cell:
                                headers[str(cell).strip()] = idx
                        continue
                        
                    # Helper to get value by header name or index
                    def get_val(names, idx_fallback):
                        val = None
                        for name in names:
                            if name in headers:
                                val = row[headers[name]]
                                break
                        if val is None and idx_fallback < len(row):
                            # Only use fallback if headers were empty or look like data
                            if not headers or len(headers) < 3: 
                                val = row[idx_fallback]
                        return val

                    g_no = get_val(['رقم الضمان', 'Guarantee No', 'g_no'], 0)
                    if not g_no: continue # Skip empty rows
                    
                    data = {}
                    data['g_no'] = str(g_no).strip()
                    data['beneficiary'] = str(get_val(['المستفيد', 'Beneficiary'], 1) or '')
                    
                    amt = get_val(['المبلغ', 'Amount'], 2)
                    try:
                        data['amount'] = float(str(amt).replace(',', '')) if amt else 0.0
                    except:
                        data['amount'] = 0.0
                        
                    data['currency'] = str(get_val(['العملة', 'Currency'], 3) or 'SAR')
                    
                    # Date parsing
                    def parse_date_val(v):
                        if not v: return None
                        if isinstance(v, datetime): return v.strftime('%Y-%m-%d')
                        # Try string formats
                        for fmt in ['%Y-%m-%d', '%d/%m/%Y', '%Y/%m/%d']:
                            try:
                                return datetime.strptime(str(v), fmt).strftime('%Y-%m-%d')
                            except:
                                pass
                        return str(v) # Fallback

                    data['start_date'] = parse_date_val(get_val(['تاريخ الإصدار', 'Start Date'], 4))
                    data['end_date'] = parse_date_val(get_val(['تاريخ الانتهاء', 'End Date'], 5))
                    
                    data['bank'] = str(get_val(['البنك', 'Bank'], 6) or '')
                    data['department'] = str(get_val(['القسم', 'Department'], 7) or '')
                    data['user_status'] = str(get_val(['الحالة', 'Status'], 8) or '')
                    data['notes'] = str(get_val(['ملاحظات', 'Notes'], 9) or '')
                    
                    # Cash Flag
                    cash_val = str(get_val(['نقدي', 'Cash'], 10) or '')
                    data['cash_flag'] = 1 if 'نعم' in cash_val or '1' in cash_val or 'نقدي' in cash_val else 0
                    
                    data['type'] = str(get_val(['النوع', 'Type'], 11) or 'نهائي')

                    # DB Insert/Update
                    try:
                        # Check existence
                        check_sql = normalize_query("SELECT id FROM guarantees WHERE g_no = ?")
                        cursor.execute(check_sql, (data['g_no'],))
                        existing = cursor.fetchone()
                        
                        if existing:
                            # Update
                            sql = normalize_query('''
                                UPDATE guarantees SET 
                                beneficiary=?, amount=?, currency=?, start_date=?, end_date=?, 
                                bank=?, department=?, user_status=?, notes=?, cash_flag=?, type=?
                                WHERE g_no=?
                            ''')
                            params = (
                                data['beneficiary'], data['amount'], data['currency'], 
                                data['start_date'], data['end_date'], data['bank'], 
                                data['department'], data['user_status'], data['notes'], 
                                data['cash_flag'], data['type'], data['g_no']
                            )
                            cursor.execute(sql, params)
                            update_count += 1
                        else:
                            # Insert
                            sql = normalize_query('''
                                INSERT INTO guarantees (
                                    g_no, beneficiary, amount, currency, start_date, end_date, 
                                    bank, department, user_status, notes, cash_flag, type
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ''')
                            params = (
                                data['g_no'], data['beneficiary'], data['amount'], data['currency'], 
                                data['start_date'], data['end_date'], data['bank'], 
                                data['department'], data['user_status'], data['notes'], 
                                data['cash_flag'], data['type']
                            )
                            cursor.execute(sql, params)
                            success_count += 1
                            
                    except Exception as e:
                        print(f"Error processing row {i}: {e}")
                        continue
                        
                conn.commit()
                conn.close()
                try:
                    os.remove(file_path)
                except:
                    pass
                
                flash(f'تمت العملية بنجاح! تم إضافة {success_count} ضمان وتحديث {update_count} ضمان.', 'success')
                return redirect(url_for('dashboard'))
                
            except Exception as e:
                flash(f'حدث خطأ أثناء معالجة الملف: {e}', 'danger')
                return redirect(request.url)
                
    return render_template('import.html')

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