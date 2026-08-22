-- ============================================
-- DAYFLOW HRMS DATABASE
-- ============================================

CREATE DATABASE IF NOT EXISTS dayflow_hrms;

USE dayflow_hrms;


-- ============================================
-- 1. USERS
-- Login credentials and roles
-- ============================================

CREATE TABLE users (
    user_id INT AUTO_INCREMENT PRIMARY KEY,
    email VARCHAR(100) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role ENUM('EMPLOYEE', 'HR') NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


-- ============================================
-- 2. EMPLOYEES
-- Employee personal and job information
-- ============================================

CREATE TABLE employees (
    employee_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT UNIQUE,
    employee_code VARCHAR(30) NOT NULL UNIQUE,
    first_name VARCHAR(50) NOT NULL,
    last_name VARCHAR(50),
    phone VARCHAR(20),
    address TEXT,
    department VARCHAR(100),
    designation VARCHAR(100),
    joining_date DATE,
    profile_picture VARCHAR(255),

    FOREIGN KEY (user_id)
        REFERENCES users(user_id)
        ON DELETE CASCADE
);


-- ============================================
-- 3. ATTENDANCE
-- Employee check-in/check-out records
-- ============================================

CREATE TABLE attendance (
    attendance_id INT AUTO_INCREMENT PRIMARY KEY,
    employee_id INT NOT NULL,
    attendance_date DATE NOT NULL,
    check_in TIME,
    check_out TIME,
    work_hours DECIMAL(5,2),
    status ENUM(
        'PRESENT',
        'ABSENT',
        'HALF_DAY',
        'LEAVE'
    ) NOT NULL,

    FOREIGN KEY (employee_id)
        REFERENCES employees(employee_id)
        ON DELETE CASCADE,

    UNIQUE (employee_id, attendance_date)
);


-- ============================================
-- 4. LEAVE REQUESTS
-- Employee leave applications
-- ============================================

CREATE TABLE leave_requests (
    leave_id INT AUTO_INCREMENT PRIMARY KEY,
    employee_id INT NOT NULL,

    leave_type ENUM(
        'PAID',
        'SICK',
        'UNPAID'
    ) NOT NULL,

    start_date DATE NOT NULL,
    end_date DATE NOT NULL,

    remarks TEXT,
    attachment VARCHAR(255),

    status ENUM(
        'PENDING',
        'APPROVED',
        'REJECTED'
    ) DEFAULT 'PENDING',

    hr_comment TEXT,

    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    reviewed_at TIMESTAMP NULL,

    FOREIGN KEY (employee_id)
        REFERENCES employees(employee_id)
        ON DELETE CASCADE
);


-- ============================================
-- 5. PAYROLL
-- Employee salary information
-- ============================================

CREATE TABLE payroll (
    payroll_id INT AUTO_INCREMENT PRIMARY KEY,
    employee_id INT NOT NULL,

    basic_salary DECIMAL(12,2) NOT NULL,
    allowances DECIMAL(12,2) DEFAULT 0,
    deductions DECIMAL(12,2) DEFAULT 0,
    net_salary DECIMAL(12,2),

    effective_from DATE,

    FOREIGN KEY (employee_id)
        REFERENCES employees(employee_id)
        ON DELETE CASCADE
);


-- ============================================
-- 6. DOCUMENTS
-- Employee documents
-- ============================================

CREATE TABLE documents (
    document_id INT AUTO_INCREMENT PRIMARY KEY,
    employee_id INT NOT NULL,

    document_name VARCHAR(150) NOT NULL,
    document_type VARCHAR(50),
    file_path VARCHAR(255) NOT NULL,

    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (employee_id)
        REFERENCES employees(employee_id)
        ON DELETE CASCADE
);


-- ============================================
-- CHECK TABLES
-- ============================================

SHOW TABLES;