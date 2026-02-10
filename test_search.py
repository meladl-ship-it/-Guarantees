
import sqlite3
import re

ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

def extract_digits_only(text):
    if not text:
        return ""
    return re.sub(r'\D', '', str(text))

def test_search_logic(search_text):
    conn = sqlite3.connect(":memory:")
    c = conn.cursor()
    c.execute('''CREATE TABLE guarantees (
        department text, bank text, g_no text, g_type text, amount real, 
        insurance_amount real, percent real, beneficiary text, requester text, 
        project_name text, issue_date text, end_date text, user_status text, 
        cash_flag integer, attachment text, delivery_status text, recipient_name text, 
        notes text, entry_number text
    )''')
    
    # Insert dummy data
    c.execute("INSERT INTO guarantees (g_no, beneficiary) VALUES (?, ?)", ("G-100", "Company A"))
    c.execute("INSERT INTO guarantees (g_no, beneficiary) VALUES (?, ?)", ("G-200", "Company B"))
    c.execute("INSERT INTO guarantees (g_no, beneficiary) VALUES (?, ?)", ("G-300", "Company C"))
    
    search = search_text.strip()
    where = []
    args = []
    
    is_numeric_search = False
    search_digits_only = ""
    if search:
        # دعم البحث عن مصطلحات متعددة مفصولة بـ *
        if '*' in search:
            terms = [t.strip() for t in search.split('*') if t.strip()]
        else:
            terms = [search]

        if terms:
            or_clauses = []
            for term in terms:
                s_num = term.translate(ARABIC_DIGITS).replace(",", "").strip()
                like = f"%{term}%"
                try:
                    amt = float(s_num)
                    clause = "(g_no LIKE ? OR beneficiary LIKE ? OR requester LIKE ? OR project_name LIKE ? OR notes LIKE ? OR entry_number LIKE ? OR amount = ? OR insurance_amount = ?)"
                    or_clauses.append(clause)
                    args.extend([like, like, like, like, like, like, amt, amt])
                except Exception:
                    clause = "(g_no LIKE ? OR beneficiary LIKE ? OR requester LIKE ? OR project_name LIKE ? OR notes LIKE ? OR entry_number LIKE ?)"
                    or_clauses.append(clause)
                    args.extend([like, like, like, like, like, like])
            
            if or_clauses:
                where.append(f"({' OR '.join(or_clauses)})")

            # إعداد متغيرات ما بعد المعالجة (post-processing)
            if len(terms) == 1:
                # في حالة البحث المفرد، نحتفظ بالمنطق القديم للبحث الذكي داخل الأرقام
                search_single = terms[0]
                s_num = search_single.translate(ARABIC_DIGITS).replace(",", "").strip()
                search_digits_only = extract_digits_only(search_single)
                try:
                    float(s_num)
                    is_numeric_search = True
                except:
                    is_numeric_search = False
            else:
                # في حالة البحث المتعدد، نعطل الفلترة اللاحقة لتجنب حذف نتائج صحيحة
                is_numeric_search = True
                search_digits_only = ""

    sql = "SELECT g_no FROM guarantees"
    if where:
        sql += " WHERE " + " AND ".join(where)
    
    print(f"Search: '{search_text}'")
    print(f"SQL: {sql}")
    print(f"Args: {args}")
    
    try:
        rows = c.execute(sql, args).fetchall()
        print(f"Rows found: {rows}")
    except Exception as e:
        print(f"Error: {e}")
    
    conn.close()

if __name__ == "__main__":
    test_search_logic("100 * 200")
    test_search_logic("Company A * Company C")
    test_search_logic("G-100")

