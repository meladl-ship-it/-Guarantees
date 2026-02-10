import sys
import os
import sqlite3

# Ensure we can import db_adapter from current directory
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from db_adapter import connect_db

def count_stats():
    conn = connect_db()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM guarantees")
    rows = cursor.fetchall()
    conn.close()
    
    total = len(rows)
    print(f"Total Rows: {total}")
    
    # Counters
    active_non_cash = 0
    expired_non_cash = 0
    pending_non_cash = 0
    others_non_cash = 0
    
    cash_active = 0
    cash_expired = 0
    
    for r in rows:
        status = (r['user_status'] or '').strip()
        is_cash = (r['cash_flag'] == 1)
        end_date_str = r['end_date']
        
        is_expired_status = (status == 'منتهي')
        is_pending = (status == 'انتهى في انتظار التأكيد')
        
        # Check date expiry
        is_date_expired = False
        if end_date_str:
            try:
                from datetime import datetime
                ed = datetime.strptime(str(end_date_str), '%Y-%m-%d')
                if ed < datetime.now():
                    is_date_expired = True
            except:
                pass

        if is_cash:
            print(f"DEBUG: Cash Guarantee Found: {r['g_no']} - Status: '{status}'")
            if not is_expired_status:
                cash_active += 1
                if is_date_expired:
                    print(f"WARNING: Active Cash Guarantee Expired by Date: {r['g_no']} - {end_date_str}")
            else:
                cash_expired += 1
        else:
            # Non-Cash
            if is_expired_status:
                expired_non_cash += 1
            elif is_pending:
                pending_non_cash += 1
            else:
                # Active (Empty, 'ساري', 'ضمان غير مسجل', etc.)
                if status == 'ضمان غير مسجل':
                    print(f"DEBUG: Non-Cash Unregistered Found: {r['g_no']}")
                    
                active_non_cash += 1
                if is_date_expired:
                    print(f"WARNING: Active Non-Cash Guarantee Expired by Date: {r['g_no']} - {end_date_str}")
                
    print("-" * 30)
    print(f"Non-Cash Active (Standard Logic): {active_non_cash}")
    print(f"Non-Cash Pending (Included in Web Active): {pending_non_cash}")
    print(f"Web App Active Total (Active + Pending): {active_non_cash + pending_non_cash}")
    print(f"Non-Cash Expired: {expired_non_cash}")
    print("-" * 30)
    print(f"Cash Active: {cash_active}")
    print(f"Cash Expired: {cash_expired}")
    print("-" * 30)
    print(f"Hypothesis 1 (Web + Cash Active): {active_non_cash + pending_non_cash + cash_active}")

if __name__ == "__main__":
    count_stats()