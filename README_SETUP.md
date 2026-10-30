# Hospital Management System Pro (Python + MySQL/WAMP)

## Modules included
1. Patient management (register, search, update, delete)
2. Doctor management (add, view, update fee/availability/active status)
3. Appointments (book, list, update status, basic double-booking check)
4. Billing and payments (bills, partial payments, outstanding balance)
5. Pharmacy inventory (stock, expiry dates, low-stock report)
6. Laboratory tests (requests, status and result updates)
7. Wards, beds and admissions (availability, admission, discharge)
8. Electronic medical records (visit history, symptoms, diagnosis, prescription, notes)
9. Department management
10. Reports and analytics (counts, revenue, appointments, occupancy, CSV export, audit log)
11. User management (admin/staff accounts, activation, password change)
12. Login/logout

## Requirements
- Windows with WAMP Server
- Python 3.10+ (your installed version can also work if mysql-connector-python supports it)
- MySQL/MariaDB service running in WAMP
- VS Code

## Step-by-step setup
1. Extract this ZIP to a folder, for example `Desktop\Hospital_Management_System_Pro`.
2. Open WAMP and wait until its icon indicates all required services are running.
3. Open WAMP's MySQL console/phpMyAdmin and confirm your MySQL port, username and password.
4. In VS Code, open the extracted folder.
5. Open `main.py`. In `DB_CONFIG`, update:
   - `host`: usually `127.0.0.1`
   - `user`: often `root` on a local WAMP install
   - `password`: often blank on a default local setup, but use your own configured password
   - `port`: commonly `3306`; check your WAMP setup
6. Open VS Code Terminal > New Terminal.
7. Install the connector:
   `python -m pip install mysql-connector-python`
8. Run:
   `python main.py`
9. On first run, the program creates the `hospital_management` database and its tables automatically.
10. First-run administrator username: `admin`. A random password is printed once in the terminal when the database is first initialized. Save it securely. Existing SHA-256 passwords are upgraded automatically after successful login.
11. Add a department first, then add doctors, register patients, and test the other modules.
12. CSV patient exports are saved in the current working directory.

## Recommended demonstration sequence
1. Login
2. Add departments: Cardiology, General Medicine, Orthopedics
3. Add two doctors and register two sample patients
4. Book an appointment and change its status to Completed
5. Create a bill and record a partial payment
6. Add a medicine with low stock and show the alert
7. Add a lab test and enter a result
8. Add a bed, admit a patient, then discharge the patient
9. Add a medical record and show patient history
10. Open Reports & Analytics and export patients to CSV
11. Show the audit log and user management

## Important notes
- Use fictional/sample patient information for your college demonstration.
- This is an educational command-line project, not a production-ready hospital information system.
- Passwords now use salted PBKDF2-SHA256, but production deployment still requires reviewed access policy, encrypted transport and backups, privacy controls and clinical/legal review.
- Appointment booking now locks the doctor row while checking conflicts; keep all future appointment writes on the same locking path.
- Test on a backup database first if you are integrating this with an existing project.

## Updates in this release
- Atomic admission/bed allocation and discharge; duplicate active bed admissions prevented through locked bed checks.
- Discharge blocked when any bill for that patient remains unpaid (conservative because bills do not have an admission ID).
- Initial and additional payments cannot overpay; `bill_payments` stores new payment transactions. Historical payments remain reflected in bill totals but are not retroactively itemized.
- Medicine issue deducts stock with locking and logs `medicine_issues`, rejects expired or insufficient inventory.
- Secure salted PBKDF2 password hashing; earlier SHA-256 account hashes migrate on login.
- Admin-only financial, medical, pharmacy, ward, doctor and reporting modules. Staff retain patient, appointment, lab and personal password changes; patient deletion is admin-only.
- Appointment dates, weekdays, scheduling collisions, and patient-to-appointment links are verified.
- Patient searches, appointment and bill listings are paginated at 25 rows.
- The application creates/migrates tables on startup. Always back up the database before upgrade.
- MySQL integration testing requires a running local WAMP/MySQL server and was not done in this workspace.
