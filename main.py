"""
Hospital Management System Pro
Python + MySQL (WAMP) | Educational/demo project

Setup:
  pip install mysql-connector-python
  Update DB_CONFIG below if your WAMP MySQL username/password/port differs.
  Run: python main.py

This is a classroom demo, not a production clinical system. Do not use real patient data.
"""
import os
import sys
import csv
import hashlib
import hmac
import secrets
import re
from contextlib import contextmanager
import getpass
from datetime import datetime, date
from decimal import Decimal, InvalidOperation

try:
    import mysql.connector
    from mysql.connector import Error
except ImportError:
    print("Missing dependency. Run: pip install mysql-connector-python")
    raise SystemExit(1)

DB_CONFIG = {
    "host": "127.0.0.1",
    "user": "root",
    "password": "",          # Add your WAMP MySQL password if you set one
    "port": 3306,             # Check WAMP if your MySQL port differs
    "database": "hospital_management"
}

def pause():
    input("\\nPress Enter to continue...")

def line():
    print("-" * 76)

def heading(title):
    print("\\n" + "=" * 76)
    print(title.center(76))
    print("=" * 76)

def ask(prompt, required=True):
    while True:
        value = input(prompt).strip()
        if value or not required:
            return value
        print("This field is required.")

def ask_int(prompt, minimum=0, allow_blank=False):
    while True:
        raw = input(prompt).strip()
        if allow_blank and not raw:
            return None
        try:
            value = int(raw)
            if value < minimum:
                print(f"Enter a number >= {minimum}.")
                continue
            return value
        except ValueError:
            print("Enter a valid whole number.")

def ask_money(prompt, allow_blank=False):
    while True:
        raw = input(prompt).strip()
        if allow_blank and not raw:
            return None
        try:
            value = Decimal(raw)
            if not value.is_finite() or value < 0 or value > Decimal("99999999.99"):
                print("Enter a non-negative finite amount up to 99999999.99.")
                continue
            return value.quantize(Decimal("0.01"))
        except (InvalidOperation, ValueError):
            print("Enter a valid amount, e.g. 1250.00")

def ask_date(prompt, allow_blank=False):
    while True:
        raw = input(prompt).strip()
        if allow_blank and not raw:
            return None
        try:
            return datetime.strptime(raw, "%Y-%m-%d").date()
        except ValueError:
            print("Use YYYY-MM-DD format, e.g. 2026-10-29.")

def ask_phone(prompt, allow_blank=True):
    while True:
        val = ask(prompt, required=not allow_blank)
        if not val and allow_blank:
            return None
        if re.fullmatch(r"[+]?[0-9]{10,15}", val):
            return val
        print("Enter 10-15 digits, optionally prefixed with +.")

def ask_choice(prompt, choices, allow_blank=True):
    while True:
        val = ask(prompt, required=not allow_blank)
        if not val and allow_blank:
            return None
        match = next((c for c in choices if c.lower() == val.lower()), None)
        if match is not None:
            return match
        print("Choose: " + ", ".join(choices))

def ask_page():
    return ask_int("Page number (25 per page): ", 1)

def confirm(prompt="Are you sure? (y/n): "):
    return input(prompt).strip().lower() in ("y", "yes")

def print_rows(rows):
    if not rows:
        print("No records found.")
        return
    for row in rows:
        print("-" * 76)
        for key, value in row.items():
            print(f"{key}: {value}")
    line()

class HospitalApp:
    def __init__(self):
        self.conn = None
        self.user = None
        self.role = None
        self._in_transaction = False

    def connect(self):
        try:
            # First connect without selecting a database, then create it if needed.
            cfg = dict(DB_CONFIG)
            db_name = cfg.pop("database")
            temp = mysql.connector.connect(**cfg)
            cur = temp.cursor()
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{db_name}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
            cur.close()
            temp.close()
            self.conn = mysql.connector.connect(**DB_CONFIG)
            self.conn.autocommit = False
            self.create_tables()
            self.seed_admin()
            return True
        except Error as exc:
            print("\\nCould not connect to MySQL.")
            print("Check that WAMP is running and DB_CONFIG has the correct port/user/password.")
            print("MySQL error:", exc)
            return False

    def query(self, sql, params=(), fetch=False, many=False):
        cur = self.conn.cursor(dictionary=True)
        try:
            if many:
                cur.executemany(sql, params)
            else:
                cur.execute(sql, params)
            result = cur.fetchall() if fetch else cur.lastrowid
            if not self._in_transaction:
                self.conn.commit()
            return result
        except Exception:
            if not self._in_transaction:
                self.conn.rollback()
            raise
        finally:
            cur.close()

    @contextmanager
    def transaction(self):
        if self._in_transaction:
            raise RuntimeError("Nested transactions are not supported")
        self.conn.commit()  # end a prior read-only transaction before starting a locked operation
        self.conn.start_transaction()
        self._in_transaction = True
        try:
            yield
            self.conn.commit()
        except BaseException:
            self.conn.rollback()
            raise
        finally:
            self._in_transaction = False

    def require_admin(self):
        if self.role != "admin":
            print("Access denied: administrator privileges required.")
            return False
        return True

    def require_row(self, sql, params=()):
        rows = self.query(sql, params, fetch=True)
        if not rows:
            raise ValueError("Record not found or not eligible for this action")
        return rows[0]

    def doctor_available(self, days, appointment_date):
        if not days:
            return True  # no restriction configured
        short = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        name = short[appointment_date.weekday()]
        tokens = [x.strip() for x in re.split(r"[,/;]", days) if x.strip()]
        allowed = set()
        for token in tokens:
            if "-" in token:
                a, b = [part.strip().title()[:3] for part in token.split("-", 1)]
                if a not in short or b not in short:
                    raise ValueError("Doctor's available_days must use Mon-Fri or Mon,Wed,Fri")
                start, stop = short.index(a), short.index(b)
                allowed.update(short[i % 7] for i in range(start, start + ((stop - start) % 7) + 1))
            elif token.strip().title()[:3] in short:
                allowed.add(token.strip().title()[:3])
            else:
                raise ValueError("Doctor's available_days must use Mon-Fri or Mon,Wed,Fri")
        return name in allowed

    def create_tables(self):
        statements = [
        """CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(50) UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            role ENUM('admin','staff') NOT NULL DEFAULT 'staff',
            active TINYINT(1) NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""",
        """CREATE TABLE IF NOT EXISTS departments (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(100) UNIQUE NOT NULL,
            description VARCHAR(255)
        )""",
        """CREATE TABLE IF NOT EXISTS patients (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(120) NOT NULL,
            age INT,
            gender VARCHAR(20),
            phone VARCHAR(25),
            address VARCHAR(255),
            blood_group VARCHAR(5),
            emergency_contact VARCHAR(25),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""",
        """CREATE TABLE IF NOT EXISTS doctors (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(120) NOT NULL,
            department_id INT NULL,
            specialization VARCHAR(100),
            phone VARCHAR(25),
            consultation_fee DECIMAL(10,2) NOT NULL DEFAULT 0,
            available_days VARCHAR(100),
            active TINYINT(1) NOT NULL DEFAULT 1,
            FOREIGN KEY (department_id) REFERENCES departments(id) ON DELETE SET NULL
        )""",
        """CREATE TABLE IF NOT EXISTS appointments (
            id INT AUTO_INCREMENT PRIMARY KEY,
            patient_id INT NOT NULL,
            doctor_id INT NOT NULL,
            appointment_date DATE NOT NULL,
            appointment_time TIME NOT NULL,
            reason VARCHAR(255),
            status ENUM('Booked','Completed','Cancelled','No-show') NOT NULL DEFAULT 'Booked',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (patient_id) REFERENCES patients(id),
            FOREIGN KEY (doctor_id) REFERENCES doctors(id)
        )""",
        """CREATE TABLE IF NOT EXISTS bills (
            id INT AUTO_INCREMENT PRIMARY KEY,
            patient_id INT NOT NULL,
            appointment_id INT NULL,
            description VARCHAR(255) NOT NULL,
            total_amount DECIMAL(10,2) NOT NULL,
            paid_amount DECIMAL(10,2) NOT NULL DEFAULT 0,
            payment_method VARCHAR(30),
            bill_status ENUM('Pending','Partially Paid','Paid') NOT NULL DEFAULT 'Pending',
            bill_date DATE NOT NULL,
            FOREIGN KEY (patient_id) REFERENCES patients(id),
            FOREIGN KEY (appointment_id) REFERENCES appointments(id) ON DELETE SET NULL
        )""",
        """CREATE TABLE IF NOT EXISTS bill_payments (
            id INT AUTO_INCREMENT PRIMARY KEY,
            bill_id INT NOT NULL,
            amount DECIMAL(10,2) NOT NULL,
            payment_method VARCHAR(30),
            paid_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (bill_id) REFERENCES bills(id)
        )""",
        """CREATE TABLE IF NOT EXISTS medicine_issues (
            id INT AUTO_INCREMENT PRIMARY KEY,
            medicine_id INT NOT NULL,
            patient_id INT NULL,
            quantity INT NOT NULL,
            issued_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (medicine_id) REFERENCES medicines(id),
            FOREIGN KEY (patient_id) REFERENCES patients(id)
        )""",
        """CREATE TABLE IF NOT EXISTS medicines (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(120) NOT NULL,
            batch_no VARCHAR(60),
            quantity INT NOT NULL DEFAULT 0,
            reorder_level INT NOT NULL DEFAULT 10,
            unit_price DECIMAL(10,2) NOT NULL DEFAULT 0,
            expiry_date DATE NULL,
            supplier VARCHAR(120)
        )""",
        """CREATE TABLE IF NOT EXISTS lab_tests (
            id INT AUTO_INCREMENT PRIMARY KEY,
            patient_id INT NOT NULL,
            test_name VARCHAR(120) NOT NULL,
            requested_by INT NULL,
            test_date DATE NOT NULL,
            result_text TEXT,
            status ENUM('Requested','In Progress','Completed') NOT NULL DEFAULT 'Requested',
            charge DECIMAL(10,2) NOT NULL DEFAULT 0,
            FOREIGN KEY (patient_id) REFERENCES patients(id),
            FOREIGN KEY (requested_by) REFERENCES doctors(id) ON DELETE SET NULL
        )""",
        """CREATE TABLE IF NOT EXISTS wards (
            id INT AUTO_INCREMENT PRIMARY KEY,
            ward_name VARCHAR(100) NOT NULL,
            bed_number VARCHAR(20) NOT NULL,
            bed_type VARCHAR(50) DEFAULT 'General',
            daily_charge DECIMAL(10,2) NOT NULL DEFAULT 0,
            status ENUM('Available','Occupied','Maintenance') NOT NULL DEFAULT 'Available',
            UNIQUE KEY unique_bed (ward_name, bed_number)
        )""",
        """CREATE TABLE IF NOT EXISTS admissions (
            id INT AUTO_INCREMENT PRIMARY KEY,
            patient_id INT NOT NULL,
            bed_id INT NOT NULL,
            admission_date DATE NOT NULL,
            discharge_date DATE NULL,
            diagnosis VARCHAR(255),
            status ENUM('Admitted','Discharged') NOT NULL DEFAULT 'Admitted',
            FOREIGN KEY (patient_id) REFERENCES patients(id),
            FOREIGN KEY (bed_id) REFERENCES wards(id)
        )""",
        """CREATE TABLE IF NOT EXISTS medical_records (
            id INT AUTO_INCREMENT PRIMARY KEY,
            patient_id INT NOT NULL,
            doctor_id INT NULL,
            visit_date DATE NOT NULL,
            symptoms TEXT,
            diagnosis TEXT,
            prescription TEXT,
            notes TEXT,
            FOREIGN KEY (patient_id) REFERENCES patients(id),
            FOREIGN KEY (doctor_id) REFERENCES doctors(id) ON DELETE SET NULL
        )""",
        """CREATE TABLE IF NOT EXISTS audit_logs (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(50),
            action_text VARCHAR(255) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )"""
        ]
        cur = self.conn.cursor()
        for statement in statements:
            cur.execute(statement)
        # Upgrades older demo databases without deleting existing users.
        cur.execute("ALTER TABLE users MODIFY password_hash VARCHAR(255) NOT NULL")
        self.conn.commit()
        cur.close()

    @staticmethod
    def hash_password(password):
        salt = secrets.token_bytes(16)
        iterations = 600000
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        return f"pbkdf2_sha256${iterations}${salt.hex()}${digest.hex()}"

    @staticmethod
    def verify_password(password, saved):
        if saved.startswith("pbkdf2_sha256$"):
            try:
                _, rounds, salt, digest = saved.split("$")
                candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), int(rounds))
                return hmac.compare_digest(candidate, bytes.fromhex(digest))
            except (ValueError, TypeError):
                return False
        # Existing SHA-256 demo accounts are upgraded on successful login.
        return hmac.compare_digest(hashlib.sha256(password.encode("utf-8")).hexdigest(), saved)

    def seed_admin(self):
        existing = self.query("SELECT id FROM users WHERE username=%s", ("admin",), fetch=True)
        if not existing:
            password = secrets.token_urlsafe(18)
            self.query(
                "INSERT INTO users(username,password_hash,role) VALUES(%s,%s,'admin')",
                ("admin", self.hash_password(password))
            )
            print("First-run administrator username: admin")
            print("First-run administrator password:", password)
            print("Change this password before any real use.")

    def log(self, action):
        if self.user:
            self.query("INSERT INTO audit_logs(username,action_text) VALUES(%s,%s)",
                       (self.user, action))

    def login(self):
        heading("HOSPITAL MANAGEMENT SYSTEM PRO")
        print("Sign in to continue. Initial admin credentials appear only on first setup.")
        for _ in range(3):
            username = ask("Username: ")
            password = getpass.getpass("Password: ")
            rows = self.query(
                "SELECT username, password_hash, role FROM users WHERE username=%s AND active=1",
                (username,), fetch=True
            )
            if rows and self.verify_password(password, rows[0]["password_hash"]):
                if not rows[0]["password_hash"].startswith("pbkdf2_sha256$"):
                    self.query("UPDATE users SET password_hash=%s WHERE username=%s", (self.hash_password(password), username))
                self.user, self.role = rows[0]["username"], rows[0]["role"]
                self.log("Logged in")
                print(f"Welcome, {self.user} ({self.role})")
                return True
            print("Invalid username/password.")
        return False

    def list_departments(self):
        rows = self.query("SELECT * FROM departments ORDER BY name", fetch=True)
        print_rows(rows)

    def department_menu(self):
        if not self.require_admin(): return
        while True:
            heading("DEPARTMENT MANAGEMENT")
            print("1. Add department\\n2. View departments\\n3. Back")
            ch = ask("Choose: ")
            if ch == "1":
                name = ask("Department name: ")
                desc = ask("Description (optional): ", False)
                try:
                    self.query("INSERT INTO departments(name,description) VALUES(%s,%s)", (name, desc or None))
                    self.log(f"Added department: {name}")
                    print("Department added.")
                except (Error, ValueError) as e: print("Could not add department:", e)
                pause()
            elif ch == "2":
                self.list_departments(); pause()
            elif ch == "3": return
            else: print("Invalid option.")

    def patient_menu(self):
        while True:
            heading("PATIENT MANAGEMENT")
            print("1. Register patient\\n2. View/search patients\\n3. Update patient\\n4. Delete patient\\n5. Back")
            ch = ask("Choose: ")
            try:
                if ch == "1":
                    name = ask("Full name: ")
                    age = ask_int("Age (0 if unknown): ", 0)
                    if age > 125: raise ValueError("Age cannot exceed 125")
                    gender = ask_choice("Gender (Male/Female/Other): ", ["Male","Female","Other"])
                    phone = ask_phone("Phone (10-15 digits): ")
                    address = ask("Address: ", False)
                    blood = ask_choice("Blood group (A+/A-/B+/B-/AB+/AB-/O+/O-/Unknown): ", ["A+","A-","B+","B-","AB+","AB-","O+","O-","Unknown"])
                    emergency = ask_phone("Emergency contact (10-15 digits): ")
                    pid = self.query("""INSERT INTO patients(name,age,gender,phone,address,blood_group,emergency_contact)
                        VALUES(%s,%s,%s,%s,%s,%s,%s)""",
                        (name, age or None, gender or None, phone or None, address or None, blood or None, emergency or None))
                    self.log(f"Registered patient ID {pid}")
                    print("Patient registered. Patient ID:", pid)
                elif ch == "2":
                    term = ask("Search name/phone or press Enter for all: ", False)
                    page = ask_page()
                    rows = self.query("""SELECT id,name,age,gender,phone,blood_group,created_at FROM patients
                        WHERE name LIKE %s OR phone LIKE %s ORDER BY id DESC LIMIT 25 OFFSET %s""",
                        (f"%{term}%", f"%{term}%", (page-1)*25), fetch=True)
                    print_rows(rows)
                elif ch == "3":
                    pid = ask_int("Patient ID: ", 1)
                    rows = self.query("SELECT * FROM patients WHERE id=%s", (pid,), fetch=True)
                    if not rows: print("Patient not found.")
                    else:
                        p = rows[0]
                        name = ask(f"Name [{p['name']}]: ", False) or p["name"]
                        phone = ask_phone(f"Phone [{p['phone'] or ''}]: ") or p["phone"]
                        address = ask(f"Address [{p['address'] or ''}]: ", False) or p["address"]
                        self.query("UPDATE patients SET name=%s,phone=%s,address=%s WHERE id=%s",
                                   (name, phone, address, pid))
                        self.log(f"Updated patient ID {pid}"); print("Patient updated.")
                elif ch == "4":
                    if not self.require_admin():
                        pause(); continue
                    pid = ask_int("Patient ID to delete: ", 1)
                    if confirm("Delete this patient? Related records may prevent deletion (y/n): "):
                        self.query("DELETE FROM patients WHERE id=%s", (pid,))
                        self.log(f"Attempted patient deletion ID {pid}"); print("Delete request completed if no linked records.")
                elif ch == "5": return
                else: print("Invalid option.")
            except (Error, ValueError) as e: print("Database operation failed:", e)
            pause()

    def doctor_menu(self):
        if not self.require_admin(): return
        while True:
            heading("DOCTOR & STAFF MANAGEMENT")
            print("1. Add doctor\\n2. View doctors\\n3. Update doctor availability/fee\\n4. Back")
            ch = ask("Choose: ")
            try:
                if ch == "1":
                    name = ask("Doctor name: ")
                    self.list_departments()
                    dept = ask_int("Department ID (0 if none): ", 0)
                    spec = ask("Specialization: ", False)
                    phone = ask_phone("Phone (10-15 digits): ")
                    fee = ask_money("Consultation fee: ")
                    days = ask("Available days (e.g. Mon-Fri): ", False)
                    did = self.query("""INSERT INTO doctors(name,department_id,specialization,phone,consultation_fee,available_days)
                        VALUES(%s,%s,%s,%s,%s,%s)""",
                        (name, dept or None, spec or None, phone or None, fee, days or None))
                    self.log(f"Added doctor ID {did}"); print("Doctor added. ID:", did)
                elif ch == "2":
                    rows = self.query("""SELECT d.id,d.name,d.specialization,d.phone,d.consultation_fee,d.available_days,
                        dep.name AS department,d.active FROM doctors d LEFT JOIN departments dep ON d.department_id=dep.id
                        ORDER BY d.id DESC""", fetch=True)
                    print_rows(rows)
                elif ch == "3":
                    did = ask_int("Doctor ID: ", 1)
                    fee = ask_money("New consultation fee (blank to keep): ", True)
                    days = ask("New available days (blank to keep): ", False)
                    active = ask("Active? y/n (blank to keep): ", False).lower()
                    updates, params = [], []
                    if fee is not None: updates.append("consultation_fee=%s"); params.append(fee)
                    if days: updates.append("available_days=%s"); params.append(days)
                    if active in ("y","n"): updates.append("active=%s"); params.append(1 if active=="y" else 0)
                    if updates:
                        params.append(did)
                        self.query(f"UPDATE doctors SET {','.join(updates)} WHERE id=%s", tuple(params))
                        self.log(f"Updated doctor ID {did}")
                    print("Doctor update complete.")
                elif ch == "4": return
                else: print("Invalid option.")
            except (Error, ValueError) as e: print("Database operation failed:", e)
            pause()

    def appointment_menu(self):
        while True:
            heading("APPOINTMENT MANAGEMENT")
            print("1. Book appointment\\n2. View appointments\\n3. Change status\\n4. Back")
            ch = ask("Choose: ")
            try:
                if ch == "1":
                    self.patient_menu_hint()
                    pid = ask_int("Patient ID: ", 1)
                    rows = self.query("SELECT id,name FROM doctors WHERE active=1 ORDER BY id", fetch=True)
                    print_rows(rows)
                    did = ask_int("Doctor ID: ", 1)
                    adate = ask_date("Date (YYYY-MM-DD): ")
                    atime = ask("Time (HH:MM, 24-hour): ")
                    parsed_time = datetime.strptime(atime, "%H:%M").time()
                    if datetime.combine(adate, parsed_time) <= datetime.now():
                        raise ValueError("Appointment must be in the future")
                    reason = ask("Reason for visit: ", False)
                    with self.transaction():
                        doctor = self.require_row("SELECT id,available_days FROM doctors WHERE id=%s AND active=1 FOR UPDATE", (did,))
                        self.require_row("SELECT id FROM patients WHERE id=%s", (pid,))
                        if not self.doctor_available(doctor["available_days"], adate):
                            raise ValueError("Doctor is unavailable on that weekday")
                        conflict = self.query("""SELECT id FROM appointments WHERE doctor_id=%s AND appointment_date=%s
                        AND appointment_time=%s AND status='Booked'""", (did, adate, atime), fetch=True)
                        if conflict:
                            raise ValueError("Doctor already booked at this time")
                        aid = self.query("""INSERT INTO appointments(patient_id,doctor_id,appointment_date,appointment_time,reason)
                            VALUES(%s,%s,%s,%s,%s)""", (pid,did,adate,atime,reason or None))
                    self.log(f"Booked appointment ID {aid}"); print("Appointment booked. ID:", aid)
                elif ch == "2":
                    page = ask_page()
                    rows = self.query("""SELECT a.id,p.name AS patient,d.name AS doctor,a.appointment_date,
                        a.appointment_time,a.reason,a.status FROM appointments a JOIN patients p ON a.patient_id=p.id
                        JOIN doctors d ON a.doctor_id=d.id ORDER BY a.appointment_date DESC,a.appointment_time DESC LIMIT 25 OFFSET %s""", ((page-1)*25,), fetch=True)
                    print_rows(rows)
                elif ch == "3":
                    aid = ask_int("Appointment ID: ", 1)
                    print("Statuses: Booked / Completed / Cancelled / No-show")
                    status = ask("New status: ")
                    if status not in ("Booked","Completed","Cancelled","No-show"):
                        print("Invalid status.")
                    else:
                        with self.transaction():
                            ap = self.require_row("SELECT doctor_id,appointment_date,appointment_time FROM appointments WHERE id=%s", (aid,))
                            doctor = self.require_row("SELECT id,active,available_days FROM doctors WHERE id=%s FOR UPDATE", (ap["doctor_id"],))
                            if status == "Booked":
                                if not doctor["active"] or datetime.combine(ap["appointment_date"], (datetime.min + ap["appointment_time"]).time() if hasattr(ap["appointment_time"], "total_seconds") else ap["appointment_time"]) <= datetime.now():
                                    raise ValueError("Cannot rebook a past appointment or inactive doctor")
                                if not self.doctor_available(doctor["available_days"], ap["appointment_date"]):
                                    raise ValueError("Doctor unavailable on this date")
                                conflict = self.query("SELECT id FROM appointments WHERE doctor_id=%s AND appointment_date=%s AND appointment_time=%s AND status='Booked' AND id<>%s", (ap["doctor_id"],ap["appointment_date"],ap["appointment_time"],aid), fetch=True)
                                if conflict: raise ValueError("Doctor already booked at this time")
                            self.query("UPDATE appointments SET status=%s WHERE id=%s", (status,aid))
                        self.log(f"Changed appointment {aid} to {status}"); print("Status updated.")
                elif ch == "4": return
                else: print("Invalid option.")
            except (Error, ValueError) as e: print("Operation failed:", e)
            pause()

    def patient_menu_hint(self):
        rows = self.query("SELECT id,name,phone FROM patients ORDER BY id DESC LIMIT 20", fetch=True)
        print("Recent patients:"); print_rows(rows)

    def billing_menu(self):
        if not self.require_admin(): return
        while True:
            heading("BILLING & PAYMENTS")
            print("1. Create bill\n2. Record payment\n3. View bills\n4. Payment history\n5. Back")
            ch = ask("Choose: ")
            try:
                if ch == "1":
                    self.patient_menu_hint()
                    pid = ask_int("Patient ID: ", 1)
                    aid = ask_int("Appointment ID (0 if not linked): ", 0)
                    desc = ask("Bill description: ")
                    total = ask_money("Total amount (INR): ")
                    paid = ask_money("Amount paid now: ")
                    if paid > total: raise ValueError("Initial payment exceeds total bill")
                    if paid and not total: raise ValueError("Cannot take payment for zero bill")
                    method = ask("Payment method (Cash/UPI/Card/Insurance/Other): ", False) if paid else None
                    status = "Paid" if paid == total else ("Partially Paid" if paid > 0 else "Pending")
                    with self.transaction():
                        self.require_row("SELECT id FROM patients WHERE id=%s", (pid,))
                        if aid:
                            self.require_row("SELECT id FROM appointments WHERE id=%s AND patient_id=%s", (aid,pid))
                        bid = self.query("""INSERT INTO bills(patient_id,appointment_id,description,total_amount,paid_amount,payment_method,bill_status,bill_date)
                            VALUES(%s,%s,%s,%s,%s,%s,%s,%s)""", (pid,aid or None,desc,total,paid,method,status,date.today()))
                        if paid > 0:
                            self.query("INSERT INTO bill_payments(bill_id,amount,payment_method) VALUES(%s,%s,%s)", (bid,paid,method))
                    self.log(f"Created bill ID {bid}"); print("Bill created. ID:", bid)
                elif ch == "2":
                    bid = ask_int("Bill ID: ", 1)
                    amount = ask_money("Payment amount: ")
                    if amount == 0: raise ValueError("Payment must be greater than zero")
                    method = ask("Payment method: ")
                    with self.transaction():
                        bill = self.require_row("SELECT total_amount,paid_amount FROM bills WHERE id=%s FOR UPDATE", (bid,))
                        paid = bill["paid_amount"] + amount
                        if paid > bill["total_amount"]: raise ValueError("Payment exceeds outstanding balance")
                        status = "Paid" if paid == bill["total_amount"] else "Partially Paid"
                        self.query("UPDATE bills SET paid_amount=%s,bill_status=%s,payment_method=%s WHERE id=%s", (paid,status,method,bid))
                        self.query("INSERT INTO bill_payments(bill_id,amount,payment_method) VALUES(%s,%s,%s)", (bid,amount,method))
                    self.log(f"Recorded payment on bill ID {bid}"); print("Payment recorded.")
                elif ch == "3":
                    page = ask_page()
                    rows = self.query("""SELECT b.id,p.name AS patient,b.description,b.total_amount,b.paid_amount,
                        (b.total_amount-b.paid_amount) AS due,b.payment_method,b.bill_status,b.bill_date
                        FROM bills b JOIN patients p ON b.patient_id=p.id ORDER BY b.id DESC LIMIT 25 OFFSET %s""", ((page-1)*25,),fetch=True)
                    print_rows(rows)
                elif ch == "4":
                    bid = ask_int("Bill ID: ", 1)
                    print_rows(self.query("SELECT id,amount,payment_method,paid_at FROM bill_payments WHERE bill_id=%s ORDER BY id",(bid,),fetch=True))
                elif ch == "5": return
                else: print("Invalid option.")
            except (Error,ValueError) as e: print("Billing operation failed:", e)
            pause()

    def pharmacy_menu(self):
        if not self.require_admin(): return
        while True:
            heading("PHARMACY & MEDICINE INVENTORY")
            print("1. Add medicine/stock\\n2. View inventory\\n3. Restock medicine\\n4. Low-stock/expired report\\n5. Issue medicine\\n6. Back")
            ch = ask("Choose: ")
            try:
                if ch == "1":
                    name = ask("Medicine name: ")
                    batch = ask("Batch number: ", False)
                    qty = ask_int("Quantity: ", 0)
                    reorder = ask_int("Low-stock threshold: ", 0)
                    price = ask_money("Unit price: ")
                    exp = ask_date("Expiry date YYYY-MM-DD (blank if unknown): ", True)
                    supplier = ask("Supplier: ", False)
                    mid = self.query("""INSERT INTO medicines(name,batch_no,quantity,reorder_level,unit_price,expiry_date,supplier)
                        VALUES(%s,%s,%s,%s,%s,%s,%s)""",
                        (name,batch or None,qty,reorder,price,exp,supplier or None))
                    self.log(f"Added medicine ID {mid}"); print("Medicine added. ID:", mid)
                elif ch == "2":
                    print_rows(self.query("SELECT * FROM medicines ORDER BY name", fetch=True))
                elif ch == "3":
                    mid = ask_int("Medicine ID: ", 1)
                    qty = ask_int("Quantity to add: ", 1)
                    with self.transaction():
                        self.require_row("SELECT id FROM medicines WHERE id=%s FOR UPDATE",(mid,))
                        self.query("UPDATE medicines SET quantity=quantity+%s WHERE id=%s", (qty,mid))
                    self.log(f"Restocked medicine ID {mid} by {qty}"); print("Stock updated.")
                elif ch == "4":
                    rows = self.query("""SELECT id,name,batch_no,quantity,reorder_level,expiry_date FROM medicines
                        WHERE quantity<=reorder_level OR (expiry_date IS NOT NULL AND expiry_date<CURDATE()) ORDER BY quantity""", fetch=True)
                    print_rows(rows)
                elif ch == "5":
                    mid = ask_int("Medicine ID: ", 1)
                    pid = ask_int("Patient ID (0 for non-patient issue): ", 0)
                    qty = ask_int("Quantity to issue: ", 1)
                    with self.transaction():
                        medicine = self.require_row("SELECT quantity,expiry_date FROM medicines WHERE id=%s FOR UPDATE", (mid,))
                        if medicine["expiry_date"] and medicine["expiry_date"] < date.today():
                            raise ValueError("Medicine batch has expired")
                        if medicine["quantity"] < qty: raise ValueError("Insufficient stock")
                        if pid: self.require_row("SELECT id FROM patients WHERE id=%s", (pid,))
                        self.query("UPDATE medicines SET quantity=quantity-%s WHERE id=%s", (qty,mid))
                        self.query("INSERT INTO medicine_issues(medicine_id,patient_id,quantity) VALUES(%s,%s,%s)",(mid,pid or None,qty))
                    self.log(f"Issued {qty} units of medicine {mid}"); print("Medicine issued; stock deducted.")
                elif ch == "6": return
                else: print("Invalid option.")
            except (Error, ValueError) as e: print("Pharmacy operation failed:", e)
            pause()

    def lab_menu(self):
        while True:
            heading("LABORATORY & TEST REPORTS")
            print("1. Request test\\n2. View tests\\n3. Add/update result\\n4. Back")
            ch = ask("Choose: ")
            try:
                if ch == "1":
                    self.patient_menu_hint()
                    pid = ask_int("Patient ID: ", 1)
                    test = ask("Test name: ")
                    did = ask_int("Requested by doctor ID (0 if unknown): ", 0)
                    dt = ask_date("Test date YYYY-MM-DD: ")
                    charge = ask_money("Test charge: ")
                    tid = self.query("""INSERT INTO lab_tests(patient_id,test_name,requested_by,test_date,charge)
                        VALUES(%s,%s,%s,%s,%s)""", (pid,test,did or None,dt,charge))
                    self.log(f"Requested lab test ID {tid}"); print("Test requested. ID:", tid)
                elif ch == "2":
                    print_rows(self.query("""SELECT l.id,p.name AS patient,l.test_name,d.name AS doctor,l.test_date,
                        l.status,l.charge,l.result_text FROM lab_tests l JOIN patients p ON l.patient_id=p.id
                        LEFT JOIN doctors d ON l.requested_by=d.id ORDER BY l.id DESC""", fetch=True))
                elif ch == "3":
                    tid = ask_int("Test ID: ", 1)
                    result = ask("Result text: ")
                    status = ask("Status (In Progress/Completed): ")
                    if status not in ("In Progress","Completed"): print("Invalid status.")
                    else:
                        self.query("UPDATE lab_tests SET result_text=%s,status=%s WHERE id=%s", (result,status,tid))
                        self.log(f"Updated lab test ID {tid}"); print("Result updated.")
                elif ch == "4": return
                else: print("Invalid option.")
            except (Error, ValueError) as e: print("Lab operation failed:", e)
            pause()

    def ward_menu(self):
        if not self.require_admin(): return
        while True:
            heading("WARD, BED & ADMISSION MANAGEMENT")
            print("1. Add bed\\n2. View beds\\n3. Admit patient\\n4. Discharge patient\\n5. View admissions\\n6. Back")
            ch = ask("Choose: ")
            try:
                if ch == "1":
                    ward = ask("Ward name: ")
                    bed = ask("Bed number: ")
                    typ = ask("Bed type (General/ICU/Private): ", False) or "General"
                    charge = ask_money("Daily charge: ")
                    self.query("INSERT INTO wards(ward_name,bed_number,bed_type,daily_charge) VALUES(%s,%s,%s,%s)",
                               (ward,bed,typ,charge))
                    self.log(f"Added bed {ward}-{bed}"); print("Bed added.")
                elif ch == "2":
                    print_rows(self.query("SELECT * FROM wards ORDER BY ward_name,bed_number", fetch=True))
                elif ch == "3":
                    self.patient_menu_hint()
                    pid = ask_int("Patient ID: ", 1)
                    print_rows(self.query("SELECT * FROM wards WHERE status='Available' ORDER BY ward_name,bed_number", fetch=True))
                    bedid = ask_int("Available bed ID: ", 1)
                    diag = ask("Admission diagnosis/reason: ", False)
                    with self.transaction():
                        self.require_row("SELECT id FROM patients WHERE id=%s", (pid,))
                        bed = self.require_row("SELECT status FROM wards WHERE id=%s FOR UPDATE", (bedid,))
                        if bed["status"] != "Available": raise ValueError("Selected bed is not available")
                        if self.query("SELECT id FROM admissions WHERE bed_id=%s AND status='Admitted'", (bedid,), fetch=True):
                            raise ValueError("Bed already has an active admission")
                        aid = self.query("INSERT INTO admissions(patient_id,bed_id,admission_date,diagnosis) VALUES(%s,%s,%s,%s)",
                                         (pid,bedid,date.today(),diag or None))
                        self.query("UPDATE wards SET status='Occupied' WHERE id=%s", (bedid,))
                    self.log(f"Admitted patient {pid}, admission ID {aid}"); print("Admission recorded.")
                elif ch == "4":
                    aid = ask_int("Admission ID: ", 1)
                    with self.transaction():
                        admission = self.require_row("SELECT bed_id,patient_id FROM admissions WHERE id=%s AND status='Admitted' FOR UPDATE", (aid,))
                        self.require_row("SELECT id FROM wards WHERE id=%s FOR UPDATE", (admission["bed_id"],))
                        # The demo schema has no bill-to-admission link: conservatively block
                        # discharge on *any* unsettled bill for this patient.
                        dues = self.query("SELECT id FROM bills WHERE patient_id=%s AND paid_amount<total_amount LIMIT 1",(admission["patient_id"],),fetch=True)
                        if dues: raise ValueError("Outstanding patient bill(s): clear all dues before discharge")
                        self.query("UPDATE admissions SET status='Discharged',discharge_date=%s WHERE id=%s AND status='Admitted'", (date.today(),aid))
                        self.query("UPDATE wards SET status='Available' WHERE id=%s", (admission["bed_id"],))
                    self.log(f"Discharged admission ID {aid}"); print("Patient discharged and bed released.")
                elif ch == "5":
                    print_rows(self.query("""SELECT a.id,p.name AS patient,w.ward_name,w.bed_number,a.admission_date,
                        a.discharge_date,a.diagnosis,a.status FROM admissions a JOIN patients p ON a.patient_id=p.id
                        JOIN wards w ON a.bed_id=w.id ORDER BY a.id DESC""", fetch=True))
                elif ch == "6": return
                else: print("Invalid option.")
            except (Error, ValueError) as e: print("Ward operation failed:", e)
            pause()

    def records_menu(self):
        if not self.require_admin(): return
        while True:
            heading("ELECTRONIC MEDICAL RECORDS")
            print("1. Add visit record\\n2. View patient history\\n3. Back")
            ch = ask("Choose: ")
            try:
                if ch == "1":
                    self.patient_menu_hint()
                    pid = ask_int("Patient ID: ", 1)
                    did = ask_int("Doctor ID (0 if unknown): ", 0)
                    visit = ask_date("Visit date YYYY-MM-DD: ")
                    symptoms = ask("Symptoms: ", False)
                    diagnosis = ask("Diagnosis: ", False)
                    prescription = ask("Prescription: ", False)
                    notes = ask("Clinical notes: ", False)
                    rid = self.query("""INSERT INTO medical_records(patient_id,doctor_id,visit_date,symptoms,diagnosis,prescription,notes)
                        VALUES(%s,%s,%s,%s,%s,%s,%s)""",
                        (pid,did or None,visit,symptoms or None,diagnosis or None,prescription or None,notes or None))
                    self.log(f"Added medical record ID {rid}"); print("Medical record saved.")
                elif ch == "2":
                    pid = ask_int("Patient ID: ", 1)
                    print_rows(self.query("""SELECT m.id,p.name AS patient,d.name AS doctor,m.visit_date,m.symptoms,
                        m.diagnosis,m.prescription,m.notes FROM medical_records m JOIN patients p ON m.patient_id=p.id
                        LEFT JOIN doctors d ON m.doctor_id=d.id WHERE p.id=%s ORDER BY m.visit_date DESC""", (pid,), fetch=True))
                elif ch == "3": return
                else: print("Invalid option.")
            except (Error, ValueError) as e: print("Medical record operation failed:", e)
            pause()

    def reports_menu(self):
        if not self.require_admin(): return
        while True:
            heading("REPORTS & ANALYTICS")
            print("1. Hospital overview\\n2. Revenue summary\\n3. Appointment summary\\n4. Bed occupancy\\n5. Export patients to CSV\\n6. Recent audit log\\n7. Back")
            ch = ask("Choose: ")
            try:
                if ch == "1":
                    for label, sql in [
                        ("Total patients","SELECT COUNT(*) AS value FROM patients"),
                        ("Active doctors","SELECT COUNT(*) AS value FROM doctors WHERE active=1"),
                        ("Appointments today","SELECT COUNT(*) AS value FROM appointments WHERE appointment_date=CURDATE()"),
                        ("Currently admitted","SELECT COUNT(*) AS value FROM admissions WHERE status='Admitted'"),
                        ("Medicines at/below reorder level","SELECT COUNT(*) AS value FROM medicines WHERE quantity<=reorder_level"),
                        ("Pending/part-paid bills","SELECT COUNT(*) AS value FROM bills WHERE bill_status<>'Paid'")
                    ]:
                        print(f"{label}: {self.query(sql, fetch=True)[0]['value']}")
                elif ch == "2":
                    rows = self.query("""SELECT COUNT(*) AS bill_count,COALESCE(SUM(total_amount),0) AS billed,
                        COALESCE(SUM(paid_amount),0) AS collected,COALESCE(SUM(total_amount-paid_amount),0) AS outstanding
                        FROM bills""", fetch=True)
                    print_rows(rows)
                elif ch == "3":
                    print_rows(self.query("SELECT status,COUNT(*) AS count FROM appointments GROUP BY status", fetch=True))
                    print("\\nMonthly appointments:")
                    print_rows(self.query("""SELECT DATE_FORMAT(appointment_date,'%Y-%m') AS month,COUNT(*) AS total
                        FROM appointments GROUP BY DATE_FORMAT(appointment_date,'%Y-%m') ORDER BY month DESC LIMIT 12""", fetch=True))
                elif ch == "4":
                    print_rows(self.query("SELECT status,COUNT(*) AS beds FROM wards GROUP BY status", fetch=True))
                elif ch == "5":
                    rows = self.query("SELECT id,name,age,gender,phone,address,blood_group,created_at FROM patients ORDER BY id", fetch=True)
                    filename = f"patients_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
                    if rows:
                        with open(filename, "w", newline="", encoding="utf-8-sig") as f:
                            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
                            writer.writeheader()
                            writer.writerows(rows)
                        print("Exported:", os.path.abspath(filename))
                    else: print("No patient records to export.")
                elif ch == "6":
                    print_rows(self.query("SELECT * FROM audit_logs ORDER BY id DESC LIMIT 50", fetch=True))
                elif ch == "7": return
                else: print("Invalid option.")
            except (Error, ValueError) as e: print("Report failed:", e)
            pause()

    def user_menu(self):
        while True:
            heading("USER & ACCESS MANAGEMENT")
            print("1. Create staff login\\n2. Activate/deactivate account\\n3. Change my password\\n4. Back")
            ch = ask("Choose: ")
            try:
                if ch == "1":
                    if not self.require_admin(): continue
                    username = ask("New username: ")
                    password = getpass.getpass("Temporary password (min 8 characters): ")
                    if len(password) < 8: print("Password must be at least 8 characters.")
                    else:
                        role = ask("Role (admin/staff): ").lower()
                        if role not in ("admin","staff"): print("Invalid role.")
                        else:
                            self.query("INSERT INTO users(username,password_hash,role) VALUES(%s,%s,%s)",
                                       (username,self.hash_password(password),role))
                            self.log(f"Created user {username}"); print("User created.")
                elif ch == "2":
                    if not self.require_admin(): continue
                    print_rows(self.query("SELECT id,username,role,active,created_at FROM users", fetch=True))
                    uid = ask_int("User ID: ", 1)
                    active = 1 if confirm("Activate this account? (y/n): ") else 0
                    self.query("UPDATE users SET active=%s WHERE id=%s AND username<>%s", (active,uid,self.user))
                    self.log(f"Changed active state for user ID {uid}"); print("Account status updated if permitted.")
                elif ch == "3":
                    old = getpass.getpass("Current password: ")
                    rows = self.query("SELECT password_hash FROM users WHERE username=%s", (self.user,), fetch=True)
                    if not rows or not self.verify_password(old, rows[0]["password_hash"]):
                        print("Current password does not match.")
                    else:
                        new = getpass.getpass("New password (min 8 characters): ")
                        if len(new) < 8: print("Password must be at least 8 characters.")
                        else:
                            self.query("UPDATE users SET password_hash=%s WHERE username=%s",
                                       (self.hash_password(new),self.user))
                            print("Password changed.")
                elif ch == "4": return
                else: print("Invalid option.")
            except (Error, ValueError) as e: print("User operation failed:", e)
            pause()

    def main_menu(self):
        while True:
            heading("HOSPITAL MANAGEMENT SYSTEM PRO")
            print(f"Signed in: {self.user} | Role: {self.role}")
            print("""
 1. Patient Management
 2. Doctor & Staff Management
 3. Appointment Management
 4. Billing & Payments
 5. Pharmacy & Medicine Inventory
 6. Laboratory & Test Reports
 7. Ward, Bed & Admission Management
 8. Electronic Medical Records
 9. Department Management
10. Reports & Analytics
11. User & Access Management
12. Logout
 0. Exit
""")
            ch = ask("Select module: ")
            routes = {
                "1": self.patient_menu, "2": self.doctor_menu,
                "3": self.appointment_menu, "4": self.billing_menu,
                "5": self.pharmacy_menu, "6": self.lab_menu,
                "7": self.ward_menu, "8": self.records_menu,
                "9": self.department_menu, "10": self.reports_menu,
                "11": self.user_menu
            }
            if ch in routes:
                if self.role != "admin" and ch in ("2","4","5","7","8","9","10"):
                    print("Access denied for staff account.")
                    pause()
                    continue
                routes[ch]()
            elif ch == "12":
                self.log("Logged out")
                self.user = self.role = None
                if not self.login(): return
            elif ch == "0":
                if confirm("Exit the system? (y/n): "):
                    self.log("Exited application")
                    print("Thank you for using Hospital Management System Pro.")
                    return
            else:
                print("Invalid option. Please choose from the menu.")

    def run(self):
        if not self.connect():
            return
        try:
            if self.login():
                self.main_menu()
        except KeyboardInterrupt:
            print("\\nApplication stopped.")
        finally:
            if self.conn and self.conn.is_connected():
                self.conn.close()

if __name__ == "__main__":
    HospitalApp().run()
