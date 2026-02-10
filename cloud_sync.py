import sqlite3
import requests
import json
import os
import sys

# Ensure we can import db_adapter from current directory
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from db_adapter import db_path, connect_db

def load_env():
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()

load_env()

CLOUD_URL = os.environ.get("CLOUD_SYNC_URL", "http://127.0.0.1:5000/api/sync")
API_KEY = os.environ.get("API_KEY", "bb16e983-3950-4b9a-8aa0-a7f9d0f2ac32")

def sync_to_cloud(progress_callback=None):
    """
    Reads all guarantees from local DB and pushes to cloud.
    progress_callback: function(str) to report status.
    """
    try:
        if progress_callback:
            progress_callback("جاري الاتصال بقاعدة البيانات المحلية...")
            
        conn = connect_db()
        # Ensure we are using sqlite3 row factory or dict conversion
        # Check if it's sqlite
        try:
            conn.row_factory = sqlite3.Row 
        except:
            pass # Might be Postgres but unlikely for local desktop app
            
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM guarantees")
        rows = cursor.fetchall()
        
        # Convert to list of dicts
        # If it's sqlite3.Row, dict() works. If it's tuple, we need description.
        if rows and isinstance(rows[0], sqlite3.Row):
            data = [dict(row) for row in rows]
        elif rows:
            # Fallback for tuple rows
            cols = [c[0] for c in cursor.description]
            data = [dict(zip(cols, row)) for row in rows]
        else:
            data = []
            
        conn.close()
        
        # === Fetch Users ===
        conn = connect_db()
        try:
            conn.row_factory = sqlite3.Row
        except:
            pass
            
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users")
        user_rows = cursor.fetchall()
        
        if user_rows and isinstance(user_rows[0], sqlite3.Row):
            users_data = [dict(row) for row in user_rows]
        elif user_rows:
            cols = [c[0] for c in cursor.description]
            users_data = [dict(zip(cols, row)) for row in user_rows]
        else:
            users_data = []
        conn.close()
        
        if progress_callback:
            progress_callback(f"تم قراءة {len(data)} ضمان و {len(users_data)} مستخدم. جاري الرفع للسحابة...")
            
        payload = {"guarantees": data, "users": users_data}
        headers = {"X-API-Key": API_KEY, "Content-Type": "application/json"}
        
        # Use a longer timeout for large data
        response = requests.post(CLOUD_URL, json=payload, headers=headers, timeout=120)
        
        if response.status_code == 200:
            msg = f"تم تحديث {len(data)} ضمان بنجاح!"
            if progress_callback:
                progress_callback(msg)
            return True, msg
        else:
            err = f"خطأ من الخادم: {response.status_code} - {response.text[:100]}"
            if progress_callback:
                progress_callback(err)
            return False, err
            
    except Exception as e:
        err = f"فشل الاتصال: {str(e)}"
        if progress_callback:
            progress_callback(err)
        return False, err

if __name__ == "__main__":
    print(sync_to_cloud(print))
