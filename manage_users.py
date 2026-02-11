import sys
import os
import sqlite3

# Fix for Qt platform plugin "windows" not found error
# Must be set before importing PyQt5
qt_plugin_path = os.path.join(sys.prefix, 'Lib', 'site-packages', 'PyQt5', 'Qt5', 'plugins')
if os.path.exists(qt_plugin_path):
    os.environ['QT_QPA_PLATFORM_PLUGIN_PATH'] = qt_plugin_path

from PyQt5 import QtWidgets, QtCore, QtGui
from werkzeug.security import generate_password_hash

# Ensure we can import db_adapter
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
try:
    from db_adapter import connect_db, check_and_migrate_db, PSYCOPG2_AVAILABLE
    if PSYCOPG2_AVAILABLE:
        import psycopg2
        import psycopg2.extras
except ImportError:
    # Fallback if db_adapter is not found (standalone mode)
    def connect_db():
        return sqlite3.connect("guarantees.db")
    def check_and_migrate_db():
        pass
    PSYCOPG2_AVAILABLE = False

class UserDialog(QtWidgets.QDialog):
    def __init__(self, parent=None, user_data=None):
        super().__init__(parent)
        self.setWindowTitle("بيانات المستخدم" if user_data else "إضافة مستخدم")
        self.setLayoutDirection(QtCore.Qt.RightToLeft)
        self.resize(400, 300)
        
        layout = QtWidgets.QVBoxLayout(self)
        
        # Username
        layout.addWidget(QtWidgets.QLabel("اسم المستخدم:"))
        self.txt_username = QtWidgets.QLineEdit()
        if user_data:
            self.txt_username.setText(user_data['username'])
            self.txt_username.setReadOnly(True) # Don't allow changing username for existing users to avoid ID mismatch issues
        layout.addWidget(self.txt_username)
        
        # Email
        layout.addWidget(QtWidgets.QLabel("البريد الإلكتروني:"))
        self.txt_email = QtWidgets.QLineEdit()
        if user_data:
            self.txt_email.setText(user_data.get('email', ''))
        layout.addWidget(self.txt_email)
        
        # Password
        layout.addWidget(QtWidgets.QLabel("كلمة المرور (اتركها فارغة لعدم التغيير):" if user_data else "كلمة المرور:"))
        self.txt_password = QtWidgets.QLineEdit()
        self.txt_password.setEchoMode(QtWidgets.QLineEdit.Password)
        layout.addWidget(self.txt_password)
        
        # Show Password Checkbox
        self.cb_show_password = QtWidgets.QCheckBox("إظهار كلمة المرور")
        self.cb_show_password.stateChanged.connect(self.toggle_password_visibility)
        layout.addWidget(self.cb_show_password)
        
        # Role
        layout.addWidget(QtWidgets.QLabel("الصلاحية:"))
        self.cmb_role = QtWidgets.QComboBox()
        self.cmb_role.addItems(["user", "admin"])
        if user_data:
            self.cmb_role.setCurrentText(user_data['role'])
        layout.addWidget(self.cmb_role)
        
        # Buttons
        btn_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)
        
        self.user_data = user_data

    def toggle_password_visibility(self, state):
        if state == QtCore.Qt.Checked:
            self.txt_password.setEchoMode(QtWidgets.QLineEdit.Normal)
        else:
            self.txt_password.setEchoMode(QtWidgets.QLineEdit.Password)

    def get_data(self):
        return {
            'username': self.txt_username.text(),
            'email': self.txt_email.text(),
            'password': self.txt_password.text(),
            'role': self.cmb_role.currentText()
        }

class UsersManager(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("إدارة المستخدمين")
        self.resize(800, 600)
        self.setLayoutDirection(QtCore.Qt.RightToLeft)
        
        # Central Widget
        central_widget = QtWidgets.QWidget()
        self.setCentralWidget(central_widget)
        layout = QtWidgets.QVBoxLayout(central_widget)
        
        # Toolbar
        toolbar = QtWidgets.QHBoxLayout()
        
        btn_add = QtWidgets.QPushButton("إضافة مستخدم")
        btn_add.clicked.connect(self.add_user)
        toolbar.addWidget(btn_add)
        
        btn_edit = QtWidgets.QPushButton("تعديل")
        btn_edit.clicked.connect(self.edit_user)
        toolbar.addWidget(btn_edit)
        
        btn_del = QtWidgets.QPushButton("حذف")
        btn_del.clicked.connect(self.delete_user)
        toolbar.addWidget(btn_del)
        
        btn_refresh = QtWidgets.QPushButton("تحديث")
        btn_refresh.clicked.connect(self.load_users)
        toolbar.addWidget(btn_refresh)
        
        toolbar.addStretch()
        layout.addLayout(toolbar)
        
        # Table
        self.table = QtWidgets.QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["ID", "اسم المستخدم", "البريد الإلكتروني", "الصلاحية", "الحالة"])
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.doubleClicked.connect(self.edit_user)
        layout.addWidget(self.table)
        
        # Load data
        self.load_users()

    def get_db_cursor(self):
        self.conn = connect_db()
        if PSYCOPG2_AVAILABLE and isinstance(self.conn, psycopg2.extensions.connection):
             return self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        else:
             self.conn.row_factory = sqlite3.Row
             return self.conn.cursor()

    def load_users(self):
        try:
            check_and_migrate_db()
            cursor = self.get_db_cursor()
            
            # Handle different DB types for query
            query = "SELECT * FROM users ORDER BY id"
            cursor.execute(query)
            users = cursor.fetchall()
            
            self.table.setRowCount(0)
            for row_idx, user in enumerate(users):
                self.table.insertRow(row_idx)
                
                # Convert row to dict to support .get() method (needed for sqlite3.Row)
                user_data = dict(user)
                
                u_id = str(user_data.get('id', ''))
                u_name = user_data.get('username', '')
                u_email = user_data.get('email', '') or ''
                u_role = user_data.get('role', 'user')
                u_active = "نشط" if user_data.get('active', 1) else "غير نشط"
                
                self.table.setItem(row_idx, 0, QtWidgets.QTableWidgetItem(u_id))
                self.table.setItem(row_idx, 1, QtWidgets.QTableWidgetItem(u_name))
                self.table.setItem(row_idx, 2, QtWidgets.QTableWidgetItem(u_email))
                self.table.setItem(row_idx, 3, QtWidgets.QTableWidgetItem(u_role))
                self.table.setItem(row_idx, 4, QtWidgets.QTableWidgetItem(u_active))
                
            self.conn.close()
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "خطأ", f"حدث خطأ أثناء تحميل البيانات:\n{str(e)}")

    def add_user(self):
        dlg = UserDialog(self)
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            data = dlg.get_data()
            if not data['username'] or not data['password']:
                QtWidgets.QMessageBox.warning(self, "تنبيه", "يجب إدخال اسم المستخدم وكلمة المرور")
                return
                
            try:
                cursor = self.get_db_cursor()
                pwd_hash = generate_password_hash(data['password'])
                
                # Check if exists
                cursor.execute("SELECT id FROM users WHERE username = ?", (data['username'],))
                if cursor.fetchone():
                    QtWidgets.QMessageBox.warning(self, "تنبيه", "اسم المستخدم موجود مسبقاً")
                    self.conn.close()
                    return
                
                # Insert
                cursor.execute(
                    "INSERT INTO users (username, email, password_hash, role, active) VALUES (?, ?, ?, ?, 1)",
                    (data['username'], data['email'], pwd_hash, data['role'])
                )
                self.conn.commit()
                self.conn.close()
                self.load_users()
                QtWidgets.QMessageBox.information(self, "نجاح", "تم إضافة المستخدم بنجاح")
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "خطأ", f"فشل الحفظ:\n{str(e)}")

    def edit_user(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
            
        row = rows[0].row()
        user_id = self.table.item(row, 0).text()
        username = self.table.item(row, 1).text()
        email = self.table.item(row, 2).text()
        role = self.table.item(row, 3).text()
        
        user_data = {'id': user_id, 'username': username, 'email': email, 'role': role}
        
        dlg = UserDialog(self, user_data)
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            data = dlg.get_data()
            
            try:
                cursor = self.get_db_cursor()
                
                # Check if demoting admin
                if data['username'].lower() == 'admin' and data['role'] != 'admin':
                    reply = QtWidgets.QMessageBox.question(
                        self, "تنبيه", 
                        "هل أنت متأكد من تغيير صلاحية المدير 'admin' إلى مستخدم عادي؟\nقد تفقد صلاحيات الوصول للإدارة.",
                        QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
                    )
                    if reply == QtWidgets.QMessageBox.No:
                        return

                if data['password']:
                    pwd_hash = generate_password_hash(data['password'])
                    cursor.execute(
                        "UPDATE users SET email=?, role=?, password_hash=? WHERE id=?",
                        (data['email'], data['role'], pwd_hash, user_id)
                    )
                else:
                    cursor.execute(
                        "UPDATE users SET email=?, role=? WHERE id=?",
                        (data['email'], data['role'], user_id)
                    )
                    
                self.conn.commit()
                self.conn.close()
                self.load_users()
                QtWidgets.QMessageBox.information(self, "نجاح", "تم تحديث البيانات بنجاح")
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "خطأ", f"فشل التحديث:\n{str(e)}")

    def delete_user(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
            
        row = rows[0].row()
        user_id = self.table.item(row, 0).text()
        username = self.table.item(row, 1).text()
        
        if username.lower() == 'admin':
             QtWidgets.QMessageBox.warning(self, "تنبيه", "لا يمكن حذف المدير الرئيسي")
             return

        reply = QtWidgets.QMessageBox.question(
            self, "تأكيد الحذف", 
            f"هل أنت متأكد من حذف المستخدم {username}؟",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )
        
        if reply == QtWidgets.QMessageBox.Yes:
            try:
                cursor = self.get_db_cursor()
                cursor.execute("DELETE FROM users WHERE id=?", (user_id,))
                self.conn.commit()
                self.conn.close()
                self.load_users()
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "خطأ", f"فشل الحذف:\n{str(e)}")

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    
    # Set style
    app.setStyle("Fusion")
    
    window = UsersManager()
    window.show()
    sys.exit(app.exec_())
