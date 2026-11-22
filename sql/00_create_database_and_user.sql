-- 00_create_database_and_user.sql
-- Run ONCE as the MySQL administrator (root), before the first `python run_pipeline.py`.
-- Creates the project database and the project account used by the Python code (.env: MYSQL_USER / MYSQL_PASSWORD).
--
-- Before running: replace change_me below with your own password, and put the SAME password in .env
-- (MYSQL_PASSWORD=...). Never commit .env.
--
-- macOS / Linux terminal:   mysql -u root -p < sql/00_create_database_and_user.sql
-- Windows (PowerShell):     Get-Content sql\00_create_database_and_user.sql | mysql -u root -p
-- MySQL Workbench:          File > Open SQL Script, then Execute (lightning icon).
--
-- Safe to run again: nothing is dropped; the password is reset to the value below.

CREATE DATABASE IF NOT EXISTS restaurant_intelligence
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_0900_ai_ci;

CREATE USER IF NOT EXISTS 'ri_app'@'localhost' IDENTIFIED BY 'change_me';
CREATE USER IF NOT EXISTS 'ri_app'@'127.0.0.1' IDENTIFIED BY 'change_me';
ALTER USER 'ri_app'@'localhost' IDENTIFIED BY 'change_me';
ALTER USER 'ri_app'@'127.0.0.1' IDENTIFIED BY 'change_me';

-- The pipeline creates/replaces its own tables and views, so the account needs full rights on this one database only.
GRANT ALL PRIVILEGES ON restaurant_intelligence.* TO 'ri_app'@'localhost';
GRANT ALL PRIVILEGES ON restaurant_intelligence.* TO 'ri_app'@'127.0.0.1';
FLUSH PRIVILEGES;

SELECT 'Database restaurant_intelligence and user ri_app are ready.' AS status;
