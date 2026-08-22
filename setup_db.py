import os
import mysql.connector
from dotenv import load_dotenv

load_dotenv()

def run_setup():
    print("Connecting to MySQL...")
    db = mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", "")
    )
    cursor = db.cursor()
    
    db_name = os.getenv("DB_NAME", "dayflow_hrms")
    print(f"Ensuring database '{db_name}' exists...")
    cursor.execute(f"CREATE DATABASE IF NOT EXISTS {db_name}")
    cursor.execute(f"USE {db_name}")
    
    # 1. Create company table
    print("Creating 'company' table if not exists...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS company (
            company_id INT AUTO_INCREMENT PRIMARY KEY,
            company_name VARCHAR(100) NOT NULL,
            company_logo VARCHAR(255),
            phone VARCHAR(20),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB;
    """)
    
    # Helper to check if column exists
    def column_exists(table, column):
        cursor.execute(f"SHOW COLUMNS FROM {table} LIKE '{column}'")
        return cursor.fetchone() is not None

    # 2. Alter users table
    print("Checking 'users' table columns...")
    if not column_exists("users", "company_id"):
        print("Adding 'company_id' column to 'users' table...")
        cursor.execute("""
            ALTER TABLE users 
            ADD COLUMN company_id INT,
            ADD CONSTRAINT fk_users_company FOREIGN KEY (company_id) REFERENCES company(company_id) ON DELETE SET NULL;
        """)

    # 3. Alter employees table
    print("Checking 'employees' table columns...")
    if not column_exists("employees", "company_id"):
        print("Adding 'company_id' column to 'employees' table...")
        cursor.execute("""
            ALTER TABLE employees 
            ADD COLUMN company_id INT,
            ADD CONSTRAINT fk_employees_company FOREIGN KEY (company_id) REFERENCES company(company_id) ON DELETE SET NULL;
        """)
        
    # 4. Create notifications table
    print("Creating 'notifications' table if not exists...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            notification_id INT AUTO_INCREMENT PRIMARY KEY,
            employee_id INT NOT NULL,
            message TEXT NOT NULL,
            is_read BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (employee_id) REFERENCES employees(employee_id) ON DELETE CASCADE
        ) ENGINE=InnoDB;
    """)

    db.commit()
    print("Database upgrade successfully completed!")
    
    cursor.close()
    db.close()

if __name__ == "__main__":
    run_setup()
