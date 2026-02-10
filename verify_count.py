import sqlite3
import os
import sys

# Ensure we can import db_adapter
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
try:
    from db_adapter import db_path
    path = db_path()
    print(f"DB Path from adapter: {path}")
    
    if not os.path.exists(path):
        print(f"WARNING: DB path does not exist: {path}")
        # Try to find it in common locations
        candidates = [
            'guarantees.db',
            'data/guarantees.db',
            '../guarantees.db'
        ]
        for c in candidates:
            if os.path.exists(c):
                print(f"Found candidate: {c}")
                path = c
                break
    
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Check tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in cursor.fetchall()]
    print(f"Tables: {tables}")
    
    if 'guarantees' in tables:
        cursor.execute("SELECT * FROM guarantees")
        rows = cursor.fetchall()
        
        active_count = 0
        excluded_pending = 0
        excluded_expired = 0
        cash_included = 0
        
        for r in rows:
            raw_status = (r['user_status'] or '').strip()
            is_cash = (r['cash_flag'] == 1)
            
            is_expired = (raw_status == 'منتهي')
            is_pending = (raw_status == 'انتهى في انتظار التأكيد')
            
            if not is_expired and not is_pending:
                active_count += 1
                if is_cash:
                    cash_included += 1
            else:
                if is_pending:
                    excluded_pending += 1
                if is_expired:
                    excluded_expired += 1
                    
        print(f"Total Rows: {len(rows)}")
        print(f"Active Count (Calculated): {active_count}")
        print(f"Cash Included in Active: {cash_included}")
        print(f"Excluded Pending: {excluded_pending}")
        print(f"Excluded Expired: {excluded_expired}")
    else:
        print("Table 'guarantees' not found.")

except Exception as e:
    print(f"Error: {e}")
