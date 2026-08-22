import os
import random
import string
from datetime import datetime, date, timedelta
from flask import Flask, render_template, request, redirect, session, jsonify, send_from_directory
import mysql.connector
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dayflow-ultra-secret-2026")
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=31)

# Configure upload folders
UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'uploads')
LOGOS_FOLDER = os.path.join(UPLOAD_FOLDER, 'logos')
PROFILES_FOLDER = os.path.join(UPLOAD_FOLDER, 'profiles')
LEAVES_FOLDER = os.path.join(UPLOAD_FOLDER, 'leaves')
DOCS_FOLDER = os.path.join(UPLOAD_FOLDER, 'documents')

# Ensure directories exist
for folder in [LOGOS_FOLDER, PROFILES_FOLDER, LEAVES_FOLDER, DOCS_FOLDER]:
    os.makedirs(folder, exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'doc', 'docx'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_db():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "dayflow_hrms")
    )

# Helper: Add notification
def add_notification(employee_id, message):
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute(
            "INSERT INTO notifications (employee_id, message) VALUES (%s, %s)",
            (employee_id, message)
        )
        db.commit()
    except Exception as e:
        print(f"Notification error: {e}")
    finally:
        cursor.close()
        db.close()

# ============================================
# MIDDLEWARE / AUTH CHECKS
# ============================================
def get_current_user():
    if "user_id" not in session:
        return None
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute(
        """
        SELECT u.*, e.employee_id, e.employee_code, e.first_name, e.last_name, e.profile_picture, c.company_name, c.company_logo
        FROM users u
        LEFT JOIN employees e ON u.user_id = e.user_id
        LEFT JOIN company c ON u.company_id = c.company_id
        WHERE u.user_id = %s
        """,
        (session["user_id"],)
    )
    user = cursor.fetchone()
    cursor.close()
    db.close()
    return user

# ============================================
# LOGIN / SIGNUP / LOGOUT
# ============================================

@app.route("/")
def index():
    if "user_id" in session:
        if session.get("role") == "HR":
            return redirect("/hr-dashboard")
        return redirect("/employee-dashboard")
    return render_template("login.html")

@app.route("/login", methods=["POST"])
def login():
    username = request.form["email"]  # Can be email or employee_code
    password = request.form["password"]

    db = get_db()
    cursor = db.cursor(dictionary=True)
    
    # Query allows login via email or Employee ID
    cursor.execute(
        """
        SELECT u.*, e.employee_id, e.employee_code, e.first_name, e.last_name, c.company_name, c.company_logo
        FROM users u
        LEFT JOIN employees e ON u.user_id = e.user_id
        LEFT JOIN company c ON u.company_id = c.company_id
        WHERE u.email = %s OR e.employee_code = %s
        """,
        (username, username)
    )
    user = cursor.fetchone()
    cursor.close()
    db.close()

    if user and check_password_hash(user["password_hash"], password):
        session.permanent = True
        session["user_id"] = user["user_id"]
        session["role"] = user["role"]
        session["employee_id"] = user["employee_id"]
        session["employee_code"] = user["employee_code"]
        session["company_id"] = user["company_id"]
        session["company_name"] = user["company_name"]
        session["company_logo"] = user["company_logo"]
        return redirect("/")
    
    return render_template("login.html", error="Invalid credentials. Please try again.")

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "GET":
        return render_template("signup.html")

    signup_type = request.form.get("signup_type", "hr")

    if signup_type == "employee":
        employee_code = request.form["employee_code"].strip().upper()
        email = request.form["email"].strip()
        address = request.form.get("address", "").strip()
        password = request.form["password"]

        db = get_db()
        cursor = db.cursor(dictionary=True)

        try:
            # Query if employee exists with employee_code and email
            cursor.execute(
                """
                SELECT e.*, u.user_id, u.password_hash 
                FROM employees e 
                JOIN users u ON e.user_id = u.user_id 
                WHERE e.employee_code = %s AND u.email = %s
                """,
                (employee_code, email)
            )
            user_record = cursor.fetchone()

            if not user_record:
                return render_template(
                    "signup.html", 
                    error="No employee record found matching this ID and Email. Please contact your HR.",
                    signup_type=signup_type
                )

            # Check if password matches the one created by HR
            from werkzeug.security import check_password_hash
            if not check_password_hash(user_record["password_hash"], password):
                return render_template(
                    "signup.html",
                    error="Incorrect password. Please enter the temporary password provided by your HR.",
                    signup_type=signup_type
                )

            # Update Employee's address in database
            cursor.execute(
                "UPDATE employees SET address = %s WHERE employee_id = %s",
                (address, user_record["employee_id"])
            )
            db.commit()

            # Redirect to login page with a success message
            return render_template("login.html", success="Verification successful! You can now sign in using your Corporate ID.")

        except Exception as e:
            db.rollback()
            return render_template("signup.html", error=f"Database error during activation: {e}", signup_type=signup_type)
        finally:
            cursor.close()
            db.close()

    else:
        # HR Company signup
        company_name = request.form["company_name"]
        first_name = request.form["first_name"]
        last_name = request.form["last_name"]
        email = request.form["email"]
        phone = request.form["phone"]
        joining_date = request.form.get("joining_date")
        address = request.form.get("address")
        password = request.form["password"]
        confirm_password = request.form["confirm_password"]

        if not joining_date:
            joining_date = str(date.today())

        if password != confirm_password:
            return render_template("signup.html", error="Passwords do not match.", signup_type=signup_type)

        # Upload Logo
        logo_filename = None
        if 'company_logo' in request.files:
            file = request.files['company_logo']
            if file and file.filename != '' and allowed_file(file.filename):
                logo_filename = secure_filename(f"logo_{int(datetime.now().timestamp())}_{file.filename}")
                file.save(os.path.join(LOGOS_FOLDER, logo_filename))

        db = get_db()
        cursor = db.cursor()

        try:
            # 1. Insert Company
            cursor.execute(
                "INSERT INTO company (company_name, company_logo, phone) VALUES (%s, %s, %s)",
                (company_name, logo_filename, phone)
            )
            company_id = cursor.lastrowid

            # 2. Generate HR Employee ID
            company_prefix = "".join([w[0] for w in company_name.split() if w])[:2].upper()
            if len(company_prefix) < 2:
                company_prefix = (company_name[:2]).upper()
            
            first = first_name
            last = last_name if last_name else "HR"
            initials = (first[:2] + last[:2]).upper()
            year = datetime.now().year
            employee_code = f"{company_prefix}{initials}{year}0001"

            # 3. Create User
            password_hash = generate_password_hash(password)
            cursor.execute(
                "INSERT INTO users (email, password_hash, role, company_id) VALUES (%s, %s, 'HR', %s)",
                (email, password_hash, company_id)
            )
            user_id = cursor.lastrowid

            # 4. Create Employee record for the HR admin
            cursor.execute(
                """
                INSERT INTO employees (user_id, employee_code, first_name, last_name, phone, company_id, designation, department, address, joining_date)
                VALUES (%s, %s, %s, %s, %s, %s, 'HR Officer', 'HR & Admin', %s, %s)
                """,
                (user_id, employee_code, first, last, phone, company_id, address, joining_date)
            )
            employee_id = cursor.lastrowid

            # 5. Create Payroll entry for HR
            cursor.execute(
                "INSERT INTO payroll (employee_id, basic_salary, allowances, deductions, net_salary) VALUES (%s, 0, 0, 0, 0)",
                (employee_id,)
            )

            db.commit()

            # Log in user automatically
            session.permanent = True
            session["user_id"] = user_id
            session["role"] = "HR"
            session["employee_id"] = employee_id
            session["employee_code"] = employee_code
            session["company_id"] = company_id
            session["company_name"] = company_name
            session["company_logo"] = logo_filename
            
            return redirect("/")

        except mysql.connector.Error as e:
            db.rollback()
            return render_template("signup.html", error=f"Database error during registration: {e}", signup_type=signup_type)
        finally:
            cursor.close()
            db.close()

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# ============================================
# HR PORTAL ROUTING
# ============================================

@app.route("/hr-dashboard")
def hr_dashboard():
    user = get_current_user()
    if not user or user["role"] != "HR":
        return redirect("/")

    db = get_db()
    cursor = db.cursor(dictionary=True)

    # 1. Fetch all employees in this company
    cursor.execute(
        """
        SELECT e.*, u.email, p.basic_salary, p.allowances, p.deductions, p.net_salary
        FROM employees e
        JOIN users u ON e.user_id = u.user_id
        LEFT JOIN payroll p ON e.employee_id = p.employee_id
        WHERE e.company_id = %s
        """,
        (user["company_id"],)
    )
    employees = cursor.fetchall()

    # 2. Get today's attendance status for each employee
    today = date.today()
    cursor.execute(
        "SELECT * FROM attendance WHERE attendance_date = %s AND employee_id IN (SELECT employee_id FROM employees WHERE company_id = %s)",
        (today, user["company_id"])
    )
    attendances_today = {a["employee_id"]: a for a in cursor.fetchall()}

    # Check for active/approved leaves today
    cursor.execute(
        """
        SELECT employee_id FROM leave_requests 
        WHERE status = 'APPROVED' AND %s BETWEEN start_date AND end_date
        AND employee_id IN (SELECT employee_id FROM employees WHERE company_id = %s)
        """,
        (today, user["company_id"])
    )
    leaves_today = {l["employee_id"] for l in cursor.fetchall()}

    # Attach dynamic status to employee records
    present_count = 0
    leave_count = 0
    for emp in employees:
        emp_id = emp["employee_id"]
        if emp_id in leaves_today:
            emp["today_status"] = "LEAVE"
            leave_count += 1
        elif emp_id in attendances_today:
            emp["today_status"] = attendances_today[emp_id]["status"]
            if emp["today_status"] in ["PRESENT", "HALF_DAY"]:
                present_count += 1
        else:
            emp["today_status"] = "ABSENT"

    total_employees = len(employees)
    absent_count = total_employees - present_count - leave_count

    # 3. Fetch all leave requests
    cursor.execute(
        """
        SELECT lr.*, e.first_name, e.last_name, e.employee_code
        FROM leave_requests lr
        JOIN employees e ON lr.employee_id = e.employee_id
        WHERE e.company_id = %s
        ORDER BY lr.applied_at DESC
        """,
        (user["company_id"],)
    )
    leaves = cursor.fetchall()

    # 4. Fetch all attendance records for ongoing month
    start_of_month = date.today().replace(day=1)
    cursor.execute(
        """
        SELECT a.*, e.first_name, e.last_name, e.employee_code
        FROM attendance a
        JOIN employees e ON a.employee_id = e.employee_id
        WHERE e.company_id = %s AND a.attendance_date >= %s
        ORDER BY a.attendance_date DESC, a.check_in DESC
        """,
        (user["company_id"], start_of_month)
    )
    attendances = cursor.fetchall()

    # 5. Fetch payroll details
    cursor.execute(
        """
        SELECT p.*, e.first_name, e.last_name, e.employee_code, e.department
        FROM payroll p
        JOIN employees e ON p.employee_id = e.employee_id
        WHERE e.company_id = %s
        """,
        (user["company_id"],)
    )
    payrolls = cursor.fetchall()
    total_payroll_cost = sum(float(p["net_salary"] or 0) for p in payrolls)

    cursor.close()
    db.close()

    return render_template(
        "hr_dashboard.html",
        user=user,
        employees=employees,
        leaves=leaves,
        attendances=attendances,
        payrolls=payrolls,
        total_payroll_cost=total_payroll_cost,
        present_count=present_count,
        leave_count=leave_count,
        absent_count=absent_count,
        total_employees=total_employees,
        today_date=str(date.today()),
        date_today=str(date.today())
    )

# ============================================
# EMPLOYEE PORTAL ROUTING
# ============================================

@app.route("/employee-dashboard")
def employee_dashboard():
    user = get_current_user()
    if not user:
        return redirect("/")

    db = get_db()
    cursor = db.cursor(dictionary=True)

    # 1. Fetch ongoing month attendance records
    start_of_month = date.today().replace(day=1)
    cursor.execute(
        "SELECT * FROM attendance WHERE employee_id = %s AND attendance_date >= %s ORDER BY attendance_date DESC",
        (user["employee_id"], start_of_month)
    )
    attendances = cursor.fetchall()

    # Calculate stats
    days_present = sum(1 for a in attendances if a["status"] in ["PRESENT", "HALF_DAY"])
    
    # Leaves count approved
    cursor.execute(
        "SELECT COUNT(*) as count FROM leave_requests WHERE employee_id = %s AND status = 'APPROVED' AND start_date >= %s",
        (user["employee_id"], start_of_month)
    )
    days_leave = cursor.fetchone()["count"]
    
    # Simple estimate of total working days so far
    total_working = days_present + days_leave

    # 2. Fetch leave requests
    cursor.execute(
        "SELECT * FROM leave_requests WHERE employee_id = %s ORDER BY applied_at DESC",
        (user["employee_id"],)
    )
    leaves = cursor.fetchall()

    # 3. Fetch payroll structure
    cursor.execute(
        "SELECT * FROM payroll WHERE employee_id = %s",
        (user["employee_id"],)
    )
    payroll = cursor.fetchone()

    # 4. Fetch notifications
    cursor.execute(
        "SELECT * FROM notifications WHERE employee_id = %s ORDER BY created_at DESC LIMIT 10",
        (user["employee_id"],)
    )
    notifications = cursor.fetchall()

    # 5. Fetch documents
    cursor.execute(
        "SELECT * FROM documents WHERE employee_id = %s ORDER BY uploaded_at DESC",
        (user["employee_id"],)
    )
    documents = cursor.fetchall()

    cursor.close()
    db.close()

    return render_template(
        "employee_dashboard.html",
        user=user,
        attendances=attendances,
        leaves=leaves,
        payroll=payroll,
        notifications=notifications,
        documents=documents,
        days_present=days_present,
        days_leave=days_leave,
        total_working=total_working,
        today_date=str(date.today())
    )

# ============================================
# API / ASYNC ACTIONS
# ============================================

# 1. API Check-In
@app.route("/api/check-in", methods=["POST"])
def api_check_in():
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "message": "Unauthorized"}), 401

    today = date.today()
    now_time = datetime.now().time()

    db = get_db()
    cursor = db.cursor()

    try:
        # Check if already checked in today
        cursor.execute(
            "SELECT * FROM attendance WHERE employee_id = %s AND attendance_date = %s",
            (user["employee_id"], today)
        )
        if cursor.fetchone():
            return jsonify({"success": False, "message": "Already checked in today."})

        # Insert check-in record
        cursor.execute(
            "INSERT INTO attendance (employee_id, attendance_date, check_in, status) VALUES (%s, %s, %s, 'PRESENT')",
            (user["employee_id"], today, now_time)
        )
        db.commit()
        return jsonify({"success": True, "message": "Check-in successful!"})
    except Exception as e:
        db.rollback()
        return jsonify({"success": False, "message": str(e)})
    finally:
        cursor.close()
        db.close()

# 2. API Check-Out
@app.route("/api/check-out", methods=["POST"])
def api_check_out():
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "message": "Unauthorized"}), 401

    today = date.today()
    now_time = datetime.now().time()

    db = get_db()
    cursor = db.cursor(dictionary=True)

    try:
        # Find check-in row
        cursor.execute(
            "SELECT * FROM attendance WHERE employee_id = %s AND attendance_date = %s",
            (user["employee_id"], today)
        )
        record = cursor.fetchone()
        
        if not record:
            return jsonify({"success": False, "message": "No active check-in record found for today."})
        if record["check_out"]:
            return jsonify({"success": False, "message": "Already checked out today."})

        # Compute hours
        check_in_dt = datetime.combine(today, record["check_in"])
        check_out_dt = datetime.now()
        duration = check_out_dt - check_in_dt
        work_hours = round(duration.total_seconds() / 3600.0, 2)

        # Extra hours (overtime)
        extra_hours = max(0.0, round(work_hours - 8.0, 2))

        # Status rules: half day if less than 4 hours
        status = "PRESENT"
        if work_hours < 4.0:
            status = "HALF_DAY"

        # Update row
        cursor.execute(
            """
            UPDATE attendance 
            SET check_out = %s, work_hours = %s, status = %s
            WHERE attendance_id = %s
            """,
            (now_time, work_hours, status, record["attendance_id"])
        )
        db.commit()
        return jsonify({
            "success": True, 
            "message": f"Checked out! Hours worked: {work_hours} (OT: {extra_hours})"
        })
    except Exception as e:
        db.rollback()
        return jsonify({"success": False, "message": str(e)})
    finally:
        cursor.close()
        db.close()

# 3. GET Current Status
@app.route("/api/attendance-status")
def api_attendance_status():
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "message": "Unauthorized"}), 401

    today = date.today()
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute(
        "SELECT * FROM attendance WHERE employee_id = %s AND attendance_date = %s",
        (user["employee_id"], today)
    )
    status = cursor.fetchone()
    cursor.close()
    db.close()

    if status:
        return jsonify({
            "checked_in": True,
            "check_in": str(status["check_in"]),
            "check_out": str(status["check_out"]) if status["check_out"] else None,
            "status": status["status"]
        })
    return jsonify({"checked_in": False})

# 4. HR: Add new employee (Generates code & temp password)
@app.route("/api/employees/add", methods=["POST"])
def api_employees_add():
    user = get_current_user()
    if not user or user["role"] != "HR":
        return jsonify({"success": False, "message": "Access denied"}), 403

    first_name = request.form["first_name"]
    last_name = request.form["last_name"]
    email = request.form["email"]
    phone = request.form["phone"]
    department = request.form["department"]
    designation = request.form["designation"]
    joining_date = request.form.get("joining_date", str(date.today()))
    basic_salary = float(request.form.get("basic_salary", 0))
    allowances = float(request.form.get("allowances", 0))
    deductions = float(request.form.get("deductions", 0))

    db = get_db()
    cursor = db.cursor(dictionary=True)

    try:
        # Check if email already exists
        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        if cursor.fetchone():
            return jsonify({"success": False, "message": "Email already registered."})

        # 1. Generate Employee Code
        # Prefix from company name
        company_prefix = "".join([w[0] for w in user["company_name"].split() if w])[:2].upper()
        if len(company_prefix) < 2:
            company_prefix = (user["company_name"][:2]).upper()
        
        # Initials
        initials = (first_name[:2] + (last_name[:2] if last_name else "XX")).upper()
        
        # Year
        join_year = datetime.strptime(joining_date, "%Y-%m-%d").year if joining_date else datetime.now().year
        
        # Find serial number
        cursor.execute(
            "SELECT COUNT(*) as count FROM employees WHERE company_id = %s AND YEAR(joining_date) = %s",
            (user["company_id"], join_year)
        )
        serial = cursor.fetchone()["count"] + 1
        employee_code = f"{company_prefix}{initials}{join_year}{serial:04d}"

        # 2. Generate temporary password
        first_char = first_name[0].upper() if first_name else "E"
        last_name_part = (last_name.strip() if last_name else "Employee").capitalize()
        temp_pass = f"{first_char}{last_name_part}@{random.randint(100, 999)}"
        pass_hash = generate_password_hash(temp_pass)

        # 3. Insert User
        cursor.execute(
            "INSERT INTO users (email, password_hash, role, company_id) VALUES (%s, %s, 'EMPLOYEE', %s)",
            (email, pass_hash, user["company_id"])
        )
        user_id = cursor.lastrowid

        # 4. Insert Employee
        cursor.execute(
            """
            INSERT INTO employees (user_id, employee_code, first_name, last_name, phone, company_id, designation, department, joining_date)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (user_id, employee_code, first_name, last_name, phone, user["company_id"], designation, department, joining_date)
        )
        employee_id = cursor.lastrowid

        # 5. Insert Payroll
        net_salary = basic_salary + allowances - deductions
        cursor.execute(
            """
            INSERT INTO payroll (employee_id, basic_salary, allowances, deductions, net_salary, effective_from)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (employee_id, basic_salary, allowances, deductions, net_salary, joining_date)
        )

        db.commit()

        # Add initial welcome notification
        add_notification(employee_id, f"Welcome {first_name} to the system! Your ID is {employee_code}.")

        return jsonify({
            "success": True, 
            "employee_code": employee_code, 
            "temp_password": temp_pass,
            "message": "Employee created successfully!"
        })

    except Exception as e:
        db.rollback()
        return jsonify({"success": False, "message": str(e)})
    finally:
        cursor.close()
        db.close()

# 5. HR: Edit Employee
@app.route("/api/employees/edit/<int:emp_id>", methods=["POST"])
def api_employees_edit(emp_id):
    user = get_current_user()
    if not user or user["role"] != "HR":
        return jsonify({"success": False, "message": "Access denied"}), 403

    first_name = request.form["first_name"]
    last_name = request.form["last_name"]
    phone = request.form["phone"]
    department = request.form["department"]
    designation = request.form["designation"]
    joining_date = request.form.get("joining_date")
    address = request.form.get("address", "")
    
    basic_salary = float(request.form.get("basic_salary", 0))
    allowances = float(request.form.get("allowances", 0))
    deductions = float(request.form.get("deductions", 0))

    db = get_db()
    cursor = db.cursor()

    try:
        # Update employee personal details
        cursor.execute(
            """
            UPDATE employees 
            SET first_name = %s, last_name = %s, phone = %s, department = %s, designation = %s, joining_date = %s, address = %s
            WHERE employee_id = %s AND company_id = %s
            """,
            (first_name, last_name, phone, department, designation, joining_date, address, emp_id, user["company_id"])
        )

        # Upload profile picture if provided
        if 'profile_picture' in request.files:
            file = request.files['profile_picture']
            if file and file.filename != '' and allowed_file(file.filename):
                filename = secure_filename(f"avatar_{emp_id}_{file.filename}")
                file.save(os.path.join(PROFILES_FOLDER, filename))
                cursor.execute(
                    "UPDATE employees SET profile_picture = %s WHERE employee_id = %s",
                    (filename, emp_id)
                )

        # Update payroll
        net_salary = basic_salary + allowances - deductions
        cursor.execute(
            """
            UPDATE payroll 
            SET basic_salary = %s, allowances = %s, deductions = %s, net_salary = %s
            WHERE employee_id = %s
            """,
            (basic_salary, allowances, deductions, net_salary, emp_id)
        )

        db.commit()
        add_notification(emp_id, "Your profile/salary details were updated by the HR Admin.")
        return jsonify({"success": True, "message": "Employee profile updated successfully!"})
    except Exception as e:
        db.rollback()
        return jsonify({"success": False, "message": str(e)})
    finally:
        cursor.close()
        db.close()

# 6. Apply Leave
@app.route("/leave/apply", methods=["POST"])
def leave_apply():
    user = get_current_user()
    if not user:
        return redirect("/")

    leave_type = request.form["leave_type"]
    start_date = request.form["start_date"]
    end_date = request.form["end_date"]
    remarks = request.form.get("remarks", "")

    # Attachment Upload
    attachment_filename = None
    if 'attachment' in request.files:
        file = request.files['attachment']
        if file and file.filename != '' and allowed_file(file.filename):
            attachment_filename = secure_filename(f"leave_{user['employee_id']}_{int(datetime.now().timestamp())}_{file.filename}")
            file.save(os.path.join(LEAVES_FOLDER, attachment_filename))

    db = get_db()
    cursor = db.cursor()

    try:
        cursor.execute(
            """
            INSERT INTO leave_requests (employee_id, leave_type, start_date, end_date, remarks, attachment, status)
            VALUES (%s, %s, %s, %s, %s, %s, 'PENDING')
            """,
            (user["employee_id"], leave_type, start_date, end_date, remarks, attachment_filename)
        )
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"Leave application error: {e}")
    finally:
        cursor.close()
        db.close()

    return redirect("/")

# 7. HR: Approve/Reject Leave
@app.route("/leave/review/<int:leave_id>", methods=["POST"])
def leave_review(leave_id):
    user = get_current_user()
    if not user or user["role"] != "HR":
        return jsonify({"success": False, "message": "Access denied"}), 403

    status = request.form["status"]  # APPROVED / REJECTED
    hr_comment = request.form.get("hr_comment", "")

    db = get_db()
    cursor = db.cursor(dictionary=True)

    try:
        # Fetch leave details first
        cursor.execute("SELECT * FROM leave_requests WHERE leave_id = %s", (leave_id,))
        leave = cursor.fetchone()
        if not leave:
            return jsonify({"success": False, "message": "Leave request not found."})

        # Update leave status
        cursor.execute(
            """
            UPDATE leave_requests 
            SET status = %s, hr_comment = %s, reviewed_at = CURRENT_TIMESTAMP
            WHERE leave_id = %s
            """,
            (status, hr_comment, leave_id)
        )

        # If approved, generate attendance markers for leave days
        if status == "APPROVED":
            start = leave["start_date"]
            end = leave["end_date"]
            curr = start
            while curr <= end:
                # Add or update attendance record for each day in range
                cursor.execute(
                    """
                    INSERT INTO attendance (employee_id, attendance_date, status, work_hours)
                    VALUES (%s, %s, 'LEAVE', 0)
                    ON DUPLICATE KEY UPDATE status='LEAVE', work_hours=0
                    """,
                    (leave["employee_id"], curr)
                )
                curr += timedelta(days=1)

        db.commit()
        
        # Add Notification to employee
        add_notification(
            leave["employee_id"], 
            f"Your leave request ({leave['start_date']} to {leave['end_date']}) was {status.lower()} by HR."
        )

        return jsonify({"success": True, "message": f"Leave request {status.lower()} successfully!"})
    except Exception as e:
        db.rollback()
        return jsonify({"success": False, "message": str(e)})
    finally:
        cursor.close()
        db.close()

# 8. Employee Profile/Password update
@app.route("/profile/update", methods=["POST"])
def profile_update():
    user = get_current_user()
    if not user:
        return redirect("/")

    first_name = request.form.get("first_name")
    last_name = request.form.get("last_name")
    phone = request.form.get("phone")
    address = request.form.get("address")
    password = request.form.get("password")
    new_password = request.form.get("new_password")

    db = get_db()
    cursor = db.cursor()

    try:
        # Update details
        cursor.execute(
            "UPDATE employees SET first_name = %s, last_name = %s, phone = %s, address = %s WHERE employee_id = %s",
            (first_name, last_name, phone, address, user["employee_id"])
        )

        # Upload profile picture
        if 'profile_picture' in request.files:
            file = request.files['profile_picture']
            if file and file.filename != '' and allowed_file(file.filename):
                filename = secure_filename(f"avatar_{user['employee_id']}_{file.filename}")
                file.save(os.path.join(PROFILES_FOLDER, filename))
                cursor.execute(
                    "UPDATE employees SET profile_picture = %s WHERE employee_id = %s",
                    (filename, user["employee_id"])
                )

        # Change Password
        if password and new_password:
            # Recheck hash
            cursor.close()
            cursor = db.cursor(dictionary=True)
            cursor.execute("SELECT password_hash FROM users WHERE user_id = %s", (user["user_id"],))
            db_pass = cursor.fetchone()["password_hash"]
            cursor.close()
            cursor = db.cursor()
            
            if check_password_hash(db_pass, password):
                new_hash = generate_password_hash(new_password)
                cursor.execute("UPDATE users SET password_hash = %s WHERE user_id = %s", (new_hash, user["user_id"]))
            else:
                return "Incorrect current password" # For simple error handling, or render template with error

        db.commit()
    except Exception as e:
        db.rollback()
        print(f"Profile update error: {e}")
    finally:
        cursor.close()
        db.close()

    return redirect("/")

# 9. Upload Document (Employee)
@app.route("/documents/upload", methods=["POST"])
def upload_document():
    user = get_current_user()
    if not user:
        return redirect("/")

    doc_name = request.form.get("document_name", "Uploaded Doc")
    
    if 'document_file' in request.files:
        file = request.files['document_file']
        if file and file.filename != '' and allowed_file(file.filename):
            filename = secure_filename(f"doc_{user['employee_id']}_{int(datetime.now().timestamp())}_{file.filename}")
            file.save(os.path.join(DOCS_FOLDER, filename))

            db = get_db()
            cursor = db.cursor()
            try:
                cursor.execute(
                    """
                    INSERT INTO documents (employee_id, document_name, document_type, file_path)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (user["employee_id"], doc_name, file.filename.rsplit('.', 1)[1].lower(), filename)
                )
                db.commit()
            except Exception as e:
                db.rollback()
                print(f"Document upload error: {e}")
            finally:
                cursor.close()
                db.close()

    return redirect("/")

# 10. Download/View uploads
@app.route("/uploads/<folder>/<filename>")
def serve_upload(folder, filename):
    safe_folders = ['logos', 'profiles', 'leaves', 'documents']
    if folder not in safe_folders:
        return "Not found", 404
    return send_from_directory(os.path.join(UPLOAD_FOLDER, folder), filename)

# 11. Payslip calculations API (dynamic parsing based on attendance)
@app.route("/api/payslip/<int:emp_id>")
def api_payslip(emp_id):
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "message": "Unauthorized"}), 401
    
    # Check if HR or if requested for oneself
    if user["role"] != "HR" and user["employee_id"] != emp_id:
        return jsonify({"success": False, "message": "Access denied"}), 403

    db = get_db()
    cursor = db.cursor(dictionary=True)

    try:
        # Fetch employee and payroll
        cursor.execute(
            """
            SELECT e.*, p.basic_salary, p.allowances, p.deductions
            FROM employees e
            JOIN payroll p ON e.employee_id = p.employee_id
            WHERE e.employee_id = %s
            """,
            (emp_id,)
        )
        emp_payroll = cursor.fetchone()
        if not emp_payroll:
            return jsonify({"success": False, "message": "Payroll not found."})

        # Calculate payable days for current month
        start_of_month = date.today().replace(day=1)
        end_of_month = (start_of_month + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        
        # Count working days (Mon-Fri)
        total_working_days = 0
        curr = start_of_month
        while curr <= end_of_month:
            if curr.weekday() < 5: # Monday to Friday
                total_working_days += 1
            curr += timedelta(days=1)

        # Find unpaid leave count and absent count in current month
        # Unpaid leaves: approved leave_requests of type UNPAID
        cursor.execute(
            """
            SELECT SUM(DATEDIFF(LEAST(end_date, %s), GREATEST(start_date, %s)) + 1) as count
            FROM leave_requests
            WHERE employee_id = %s AND status = 'APPROVED' AND leave_type = 'UNPAID'
            AND (start_date <= %s AND end_date >= %s)
            """,
            (end_of_month, start_of_month, emp_id, end_of_month, start_of_month)
        )
        unpaid_row = cursor.fetchone()
        unpaid_days = float(unpaid_row["count"] or 0)

        # Count present/paid-leave days to determine absent days
        # Absent: days in the month (Mon-Fri) where there is no attendance check-in AND no approved leave request
        # We can calculate: Payable Days = Total Working Days - Unpaid Leave Days - Absent Days
        # Absent Days = Total Working Days (Mon-Fri) - (Present Days + Approved Paid/Sick Leave Days)
        cursor.execute(
            """
            SELECT COUNT(DISTINCT attendance_date) as count 
            FROM attendance 
            WHERE employee_id = %s AND attendance_date BETWEEN %s AND %s AND status IN ('PRESENT', 'HALF_DAY', 'LEAVE')
            """,
            (emp_id, start_of_month, end_of_month)
        )
        active_days = cursor.fetchone()["count"]
        
        # Approximate absent days
        absent_days = max(0, total_working_days - active_days - int(unpaid_days))
        payable_days = max(0, total_working_days - int(unpaid_days) - absent_days)

        # Math breakdown
        basic = float(emp_payroll["basic_salary"] or 0)
        allowances = float(emp_payroll["allowances"] or 0)
        deductions = float(emp_payroll["deductions"] or 0)

        # Pro-rated basic salary
        pro_rated_basic = round((basic / total_working_days) * payable_days, 2) if total_working_days > 0 else 0.0
        net_salary = round(pro_rated_basic + allowances - deductions, 2)

        return jsonify({
            "success": True,
            "employee_name": f"{emp_payroll['first_name']} {emp_payroll['last_name'] or ''}",
            "employee_code": emp_payroll["employee_code"],
            "designation": emp_payroll["designation"],
            "department": emp_payroll["department"],
            "month_name": date.today().strftime("%B %Y"),
            "total_working_days": total_working_days,
            "payable_days": payable_days,
            "unpaid_days": unpaid_days,
            "absent_days": absent_days,
            "basic_salary": basic,
            "pro_rated_basic": pro_rated_basic,
            "allowances": allowances,
            "deductions": deductions,
            "net_salary": net_salary
        })

    except Exception as e:
        return jsonify({"success": False, "message": str(e)})
    finally:
        cursor.close()
        db.close()

# ============================================
# LEGACY REDIRECT ROUTING FOR SEAMLESS MAPPING
# ============================================

@app.route("/profile")
def legacy_profile():
    user = get_current_user()
    if not user:
        return redirect("/")
    if user["role"] == "HR":
        return redirect("/hr-dashboard#employees")
    return redirect("/employee-dashboard#profile")

@app.route("/attendance")
def legacy_attendance():
    user = get_current_user()
    if not user:
        return redirect("/")
    if user["role"] == "HR":
        return redirect("/hr-dashboard#attendance")
    return redirect("/employee-dashboard#attendance")

@app.route("/leave")
def legacy_leave():
    user = get_current_user()
    if not user:
        return redirect("/")
    if user["role"] == "HR":
        return redirect("/hr-dashboard#leaves")
    return redirect("/employee-dashboard#leaves")

@app.route("/payroll")
def legacy_payroll():
    user = get_current_user()
    if not user:
        return redirect("/")
    if user["role"] == "HR":
        return redirect("/hr-dashboard#payroll")
    return redirect("/employee-dashboard#payroll")

@app.route("/employees")
def legacy_employees():
    user = get_current_user()
    if not user:
        return redirect("/")
    if user["role"] == "HR":
        return redirect("/hr-dashboard#employees")
    return redirect("/employee-dashboard#profile")


if __name__ == "__main__":
    app.run(debug=True)