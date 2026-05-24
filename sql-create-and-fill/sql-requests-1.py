import sqlite3
import csv

connection = sqlite3.connect("baza.db")
cursor = connection.cursor()

# Создание таблиц
cursor.execute("""
    CREATE TABLE IF NOT EXISTS job_titles (
        id_job_title INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL UNIQUE,
        name         TEXT NOT NULL
    );
""")

cursor.execute("""
    CREATE TABLE IF NOT EXISTS employees (
        id           INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL UNIQUE,
        surname      TEXT NOT NULL,
        name         TEXT NOT NULL,
        phone        TEXT,
        id_job_title INTEGER NOT NULL,
        FOREIGN KEY(id_job_title) REFERENCES job_titles(id_job_title)
    );
""")

cursor.execute("""
    CREATE TABLE IF NOT EXISTS customers (
        id_customer  INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL UNIQUE,
        company      TEXT NOT NULL,
        phone        TEXT
    );
""")

cursor.execute("""
    CREATE TABLE IF NOT EXISTS orders (
        id_order        INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL UNIQUE,
        id_customer     INTEGER NOT NULL,
        id              INTEGER NOT NULL,
        total           REAL NOT NULL,
        completion_date TEXT,
        completeness    INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY(id)          REFERENCES employees(id),
        FOREIGN KEY(id_customer) REFERENCES customers(id_customer)
    );
""")

# job_titles.csv
with open('job_titles.csv', 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        cursor.execute("INSERT OR IGNORE INTO job_titles (id_job_title, name) VALUES (?, ?)",
                       (row['id_job_title'], row['name']))

# employees.csv
with open('employees.csv', 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        cursor.execute("INSERT OR IGNORE INTO employees (id, surname, name, phone, id_job_title) VALUES (?, ?, ?, ?, ?)",
                       (row['id'], row['surname'], row['name'], row.get('phone', ''), row['id_job_title']))

# customers.csv
with open('customers.csv', 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        cursor.execute("INSERT OR IGNORE INTO customers (id_customer, company, phone) VALUES (?, ?, ?)",
                       (row['id_customer'], row['company'], row.get('phone', '')))

# orders.csv
with open('orders.csv', 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        completeness = 1 if row['completeness'].lower() == 'true' else 0
        completion_date = row['completion_date'] if row.get('completion_date', '').strip() else None
        cursor.execute("INSERT OR IGNORE INTO orders (id_order, id_customer, id, total, completion_date, completeness) VALUES (?, ?, ?, ?, ?, ?)",
                       (row['id_order'], row['id_customer'], row['id'], row['total'], completion_date, completeness))

connection.commit()

# ПЯТЬ ПРОСТЫХ ЗАПРОСОВ
print("\nПять простых запросов")

# 1. Все сотрудники
cursor.execute("SELECT * FROM employees")
print("1. Все сотрудники:", cursor.fetchall())

# 2. Все должности
cursor.execute("SELECT name FROM job_titles")
print("2. Все должности:", [row[0] for row in cursor.fetchall()])

# 3. Заказы с суммой больше 600000
cursor.execute("SELECT * FROM orders WHERE total > 600000")
print("3. Заказы с суммой > 600000:", cursor.fetchall())

# 4. Компании, начинающиеся на 'M'
cursor.execute("SELECT company FROM customers WHERE company LIKE 'M%'")
print("4. Компании на 'M':", [row[0] for row in cursor.fetchall()])

# 5. Завершённые заказы (completeness = 1)
cursor.execute("SELECT id_order, total FROM orders WHERE completeness = 1")
print("5. Завершённые заказы (id, сумма):", cursor.fetchall())

# ТРИ ЗАПРОСА С АГРЕГАЦИЕЙ
print("\nТри запроса с агрегацией")

# 1. Количество сотрудников по должностям
cursor.execute("""
    SELECT j.name, COUNT(e.id)
    FROM job_titles j
    LEFT JOIN employees e ON j.id_job_title = e.id_job_title
    GROUP BY j.id_job_title
""")
print("1. Количество сотрудников по должностям:", cursor.fetchall())

# 2. Максимальная и средняя сумма заказа
cursor.execute("SELECT MAX(total), AVG(total) FROM orders")
max_total, avg_total = cursor.fetchone()
print(f"2. Максимальная сумма: {max_total}, средняя сумма: {avg_total:.2f}")

# 3. Сумма завершённых заказов по сотрудникам
cursor.execute("""
    SELECT e.surname, e.name, SUM(o.total)
    FROM employees e
    JOIN orders o ON e.id = o.id
    WHERE o.completeness = 1
    GROUP BY e.id
""")
print("3. Сумма завершённых заказов по сотрудникам:", cursor.fetchall())

# ТРИ ЗАПРОСА С JOIN И УСЛОВИЯМИ
print("\nТри запроса с JOIN и условиями")

# 1. Полная информация о заказах
cursor.execute("""
    SELECT o.id_order, c.company, e.surname, e.name, o.total, o.completeness
    FROM orders o
    JOIN customers c ON o.id_customer = c.id_customer
    JOIN employees e ON o.id = e.id
""")
print("1. Детали заказов:", cursor.fetchall())

# 2. Разработчики с заказами > 700000
cursor.execute("""
    SELECT DISTINCT e.surname, e.name
    FROM employees e
    JOIN job_titles j ON e.id_job_title = j.id_job_title
    JOIN orders o ON e.id = o.id
    WHERE j.name = 'Developer' AND o.total > 700000
""")
print("2. Разработчики с заказами > 700000:", cursor.fetchall())

# 3. Компании с незавершёнными заказами (completeness = 0)
cursor.execute("""
    SELECT DISTINCT c.company
    FROM customers c
    JOIN orders o ON c.id_customer = o.id_customer
    WHERE o.completeness = 0
""")
print("3. Компании с незавершёнными заказами:", [row[0] for row in cursor.fetchall()])

connection.close()