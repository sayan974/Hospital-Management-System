-- Optional database initialization for WAMP MySQL/MariaDB.
-- main.py creates and upgrades the application tables automatically on startup.
CREATE DATABASE IF NOT EXISTS hospital_management CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE hospital_management;
-- Run: python main.py (initializes all tables, including bill_payments and medicine_issues).
