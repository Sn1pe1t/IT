import sqlite3
import csv

# Чтение данных из файлов (пропускаем заголовки)
def read_csv_file(filename):
    with open(filename, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        next(reader)  # пропускаем заголовок
        return [tuple(row) for row in reader]

students_data = read_csv_file('students.txt')
profile_data = read_csv_file('profile.txt')
level_data = read_csv_file('education_level.txt')
type_data = read_csv_file('education_type.txt')

# Подключение к БД
conn = sqlite3.connect('students.db')
cursor = conn.cursor()

# Создание таблиц
cursor.executescript('''
    CREATE TABLE IF NOT EXISTS education_level (
        id_level INTEGER PRIMARY KEY,
        name VARCHAR
    );
    CREATE TABLE IF NOT EXISTS profile (
        id_profile INTEGER PRIMARY KEY,
        name VARCHAR
    );
    CREATE TABLE IF NOT EXISTS education_type (
        id_educ_type INTEGER PRIMARY KEY,
        name VARCHAR
    );
    CREATE TABLE IF NOT EXISTS students (
        id_student INTEGER PRIMARY KEY,
        id_level INTEGER,
        id_profile INTEGER,
        id_educ_type INTEGER,
        lastname VARCHAR,
        firstname VARCHAR,
        patronymic VARCHAR,
        average_score INTEGER,
        FOREIGN KEY (id_level) REFERENCES education_level(id_level),
        FOREIGN KEY (id_profile) REFERENCES profile(id_profile),
        FOREIGN KEY (id_educ_type) REFERENCES education_type(id_educ_type)
    );
''')

# Заполнение таблиц
cursor.executemany('INSERT OR REPLACE INTO education_level VALUES (?, ?)', level_data)
cursor.executemany('INSERT OR REPLACE INTO profile VALUES (?, ?)', profile_data)
cursor.executemany('INSERT OR REPLACE INTO education_type VALUES (?, ?)', type_data)
cursor.executemany('''
    INSERT OR REPLACE INTO students
    (id_student, id_level, id_profile, id_educ_type, lastname, firstname, patronymic, average_score)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
''', students_data)

conn.commit()

# 1. Общее количество студентов
cursor.execute('SELECT COUNT(*) FROM students')
total_students = cursor.fetchone()[0]
print(f"Общее количество студентов: {total_students}")

# 2. Количество студентов по направлениям
cursor.execute('''
    SELECT p.name, COUNT(s.id_student)
    FROM students s
    JOIN profile p ON s.id_profile = p.id_profile
    GROUP BY s.id_profile
    ORDER BY p.name
''')
print("\nКоличество студентов по направлениям:")
for name, cnt in cursor.fetchall():
    print(f"  {name}: {cnt}")

# 3. Количество студентов по формам обучения
cursor.execute('''
    SELECT et.name, COUNT(s.id_student)
    FROM students s
    JOIN education_type et ON s.id_educ_type = et.id_educ_type
    GROUP BY s.id_educ_type
''')
print("\nКоличество студентов по формам обучения:")
for name, cnt in cursor.fetchall():
    print(f"  {name}: {cnt}")

# 4. Максимальный, минимальный, средний баллы по направлениям
cursor.execute('''
    SELECT p.name,
           MAX(s.average_score),
           MIN(s.average_score),
           AVG(s.average_score)
    FROM students s
    JOIN profile p ON s.id_profile = p.id_profile
    GROUP BY s.id_profile
    ORDER BY p.name
''')
print("\nМакс, мин, средний балл по направлениям:")
for name, max_score, min_score, avg_score in cursor.fetchall():
    print(f"  {name}: макс={max_score}, мин={min_score}, средний={avg_score:.2f}")

# 5. Средний балл по направлениям, уровням и формам обучения
cursor.execute('''
    SELECT p.name, el.name, et.name, AVG(s.average_score)
    FROM students s
    JOIN profile p ON s.id_profile = p.id_profile
    JOIN education_level el ON s.id_level = el.id_level
    JOIN education_type et ON s.id_educ_type = et.id_educ_type
    GROUP BY s.id_profile, s.id_level, s.id_educ_type
    ORDER BY p.name, el.name, et.name
''')
print("\nСредний балл по направлениям, уровням и формам обучения:")
for pname, lname, tname, avg_score in cursor.fetchall():
    print(f"  {pname}, {lname}, {tname}: {avg_score:.2f}")

# 6. 5 студентов направления "Информатика" очной формы с лучшим баллом
cursor.execute('''
    SELECT s.lastname, s.firstname, s.patronymic, s.average_score
    FROM students s
    JOIN profile p ON s.id_profile = p.id_profile
    JOIN education_type et ON s.id_educ_type = et.id_educ_type
    WHERE p.name = 'Информатика' AND et.name = 'Очная'
    ORDER BY s.average_score DESC
    LIMIT 5
''')
print("\nСтуденты направления 'Информатика' очной формы (для повышенной стипендии):")
rows = cursor.fetchall()
if rows:
    for last, first, patron, score in rows:
        print(f"  {last} {first} {patron}, средний балл: {score}")
else:
    print("  Нет таких студентов.")

# 7. Количество однофамильцев (студентов, у которых фамилия встречается более одного раза)
cursor.execute('''
    SELECT COUNT(*) FROM students
    WHERE lastname IN (
        SELECT lastname FROM students GROUP BY lastname HAVING COUNT(*) > 1
    )
''')
homonyms_count = cursor.fetchone()[0]
print(f"\nКоличество однофамильцев: {homonyms_count}")

# 8. Есть ли полные тёзки (фамилия, имя, отчество совпадают)
cursor.execute('''
    SELECT lastname, firstname, patronymic, COUNT(*)
    FROM students
    GROUP BY lastname, firstname, patronymic
    HAVING COUNT(*) > 1
''')
full_namesakes = cursor.fetchall()
if full_namesakes:
    print("\nНайдены полные тёзки:")
    for last, first, patron, cnt in full_namesakes:
        print(f"  {last} {first} {patron} - {cnt} учащихся")
else:
    print("\nПолных тёзок среди студентов нет.")

conn.close()