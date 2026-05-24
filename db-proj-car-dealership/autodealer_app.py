import sqlite3
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime
from collections import defaultdict
import csv
import os

DB_NAME = 'autodealer.db'
SCHEMA_FILE = 'schema.sql'
INIT_DATA_FILE = 'init_data.csv'

def init_db():
    conn = sqlite3.connect(DB_NAME)
    conn.execute("PRAGMA foreign_keys = ON")

    if os.path.exists(SCHEMA_FILE):
        with open(SCHEMA_FILE, 'r', encoding='utf-8') as f:
            conn.executescript(f.read())
        conn.commit()
    else:
        messagebox.showerror("Ошибка", f"Файл {SCHEMA_FILE} не найден.")
        conn.close()
        raise SystemExit

    # Удаляем старый триггер, если он остался от предыдущих версий
    conn.execute("DROP TRIGGER IF EXISTS deduct_quantity")

    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM cars")
    if cur.fetchone()[0] == 0:
        if os.path.exists(INIT_DATA_FILE):
            load_initial_data(conn, INIT_DATA_FILE)
        else:
            messagebox.showwarning("Предупреждение", f"Файл {INIT_DATA_FILE} отсутствует. Данные не загружены.")

    return conn

def load_initial_data(conn, csv_file):
    """Читает CSV-файл без заголовка и вставляет данные в соответствующие таблицы."""
    table_columns = {
        'job_titles': ['id', 'name'],
        'employees': ['id', 'name', 'surname', 'id_job_title'],
        'customers': ['id', 'first_name', 'last_name', 'phone', 'email'],
        'car_categories': ['id', 'name'],
        'cars': ['id', 'brand', 'model', 'year', 'color', 'vin', 'price', 'quantity', 'id_category',
                 'steering', 'power', 'engine_volume', 'fuel_type', 'transmission', 'drive', 'condition', 'mileage']
    }

    with open(csv_file, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        for row in reader:
            if not row or row[0].startswith('#'):
                continue
            table = row[0].strip()
            values = row[1:]
            if table not in table_columns:
                continue
            cols = table_columns[table]
            if table == 'cars' and len(values) >= len(cols):
                if values[-1] == '' or values[-1] is None:
                    values[-1] = None
                else:
                    values[-1] = int(values[-1])
            if len(values) != len(cols):
                print(f"Пропущена строка для {table}: ожидалось {len(cols)} значений, получено {len(values)}")
                continue
            placeholders = ','.join(['?' for _ in cols])
            sql = f"INSERT OR IGNORE INTO {table} ({','.join(cols)}) VALUES ({placeholders})"
            try:
                conn.execute(sql, values)
            except Exception as e:
                print(f"Ошибка вставки в {table}: {e} (строка: {row})")
    conn.commit()

def get_car_info(conn, car_id):
    row = conn.execute(
        "SELECT brand, model, year, color, price, quantity, steering, power, engine_volume, "
        "fuel_type, transmission, drive, condition, mileage FROM cars WHERE id = ?", (car_id,)
    ).fetchone()
    if row:
        info = {
            "description": f"{row[0]} {row[1]}",
            "year": row[2],
            "color": row[3],
            "price": row[4],
            "stock": row[5],
            "steering": "Левый" if row[6] == 'left' else "Правый",
            "power": row[7],
            "engine_volume": row[8],
            "fuel_type": row[9],
            "transmission": row[10],
            "drive": row[11],
            "condition": "Новый" if row[12] == 'new' else "С пробегом",
            "mileage": row[13],
            "in_stock": row[5] > 0
        }
        return info
    return None

def finalize_sale(conn, cart_items, id_employee, id_customer):
    cur = conn.cursor()
    try:
        # Группируем позиции по car_id
        totals = defaultdict(int)
        for item in cart_items:
            totals[item['car_id']] += item['quantity']

        sale_items = []
        # Проверяем остатки и готовим записи (наличие / предзаказ)
        for car_id, total_qty in totals.items():
            stock, price = cur.execute(
                "SELECT quantity, price FROM cars WHERE id = ?", (car_id,)
            ).fetchone()
            deduct_qty = min(total_qty, stock)
            preorder_qty = total_qty - deduct_qty

            if deduct_qty > 0:
                sale_items.append((car_id, deduct_qty, price, 1))   # в наличии
            if preorder_qty > 0:
                sale_items.append((car_id, preorder_qty, price, 0)) # предзаказ

        total_amount = sum(qty * price for (_, qty, price, _) in sale_items)

        # Создаём продажу
        cur.execute(
            "INSERT INTO sales (sale_date, id_customer, id_employee, total_amount) VALUES (?, ?, ?, ?)",
            (datetime.now().timestamp(), id_customer, id_employee, total_amount)
        )
        sale_id = cur.lastrowid

        # Вставляем детали и списываем остатки только для позиций в наличии
        for car_id, qty, price, in_stock_flag in sale_items:
            cur.execute(
                "INSERT INTO sale_details (id_sale, id_car, quantity, price_at_sale, in_stock_at_sale) "
                "VALUES (?, ?, ?, ?, ?)",
                (sale_id, car_id, qty, price, in_stock_flag)
            )
            if in_stock_flag:
                cur.execute(
                    "UPDATE cars SET quantity = quantity - ? WHERE id = ?",
                    (qty, car_id)
                )

        conn.commit()
        return True, sale_id
    except Exception as e:
        conn.rollback()
        return False, str(e)

def get_report(conn, date_str):
    return conn.execute('''
        SELECT c.brand || ' ' || c.model AS car,
               SUM(sd.quantity) AS qty,
               SUM(sd.quantity * sd.price_at_sale) AS revenue
        FROM sale_details sd
        JOIN cars c ON sd.id_car = c.id
        JOIN sales s ON sd.id_sale = s.id
        WHERE DATE(s.sale_date, 'unixepoch') = ?
        GROUP BY c.id
        ORDER BY revenue DESC
    ''', (date_str,)).fetchall()

def get_sales_list(conn, limit=50):
    return conn.execute('''
        SELECT s.id, 
               datetime(s.sale_date, 'unixepoch', 'localtime') AS date,
               (c.first_name || ' ' || c.last_name) AS customer,
               (e.name || ' ' || e.surname) AS employee,
               s.total_amount,
               (SELECT MIN(sd2.in_stock_at_sale) FROM sale_details sd2 WHERE sd2.id_sale = s.id) AS all_in_stock
        FROM sales s
        JOIN customers c ON s.id_customer = c.id
        JOIN employees e ON s.id_employee = e.id
        ORDER BY s.sale_date DESC
        LIMIT ?
    ''', (limit,)).fetchall()

def get_sale_details(conn, sale_id):
    return conn.execute('''
        SELECT ca.brand, ca.model, ca.year, ca.engine_volume, ca.fuel_type, ca.transmission, ca.drive,
               sd.quantity, sd.price_at_sale,
               (sd.quantity * sd.price_at_sale) AS subtotal,
               sd.id_car, sd.in_stock_at_sale
        FROM sale_details sd
        JOIN cars ca ON sd.id_car = ca.id
        WHERE sd.id_sale = ?
    ''', (sale_id,)).fetchall()


class AutoDealerApp:
    def __init__(self, root):
        self.conn = init_db()
        self.root = root
        self.root.title("Автосалон – Система заказов")
        self.root.geometry("1200x850")
        self.cart = []
        self.cars = {}

        style = ttk.Style()
        style.theme_use('clam')
        style.configure('TNotebook.Tab', padding=[10, 5], font=('Arial', 10, 'bold'))
        style.configure('TLabel', font=('Arial', 10))
        style.configure('TButton', font=('Arial', 10))
        style.configure('Green.TLabel', foreground='green', font=('Arial', 10, 'bold'))
        style.configure('Red.TLabel', foreground='red', font=('Arial', 10, 'bold'))

        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill='both', expand=True, padx=10, pady=10)

        self.tab_sale = tk.Frame(self.notebook)
        self.tab_history = tk.Frame(self.notebook)
        self.notebook.add(self.tab_sale, text="Оформление заказа")
        self.notebook.add(self.tab_history, text="Заказы и отчёты")

        self._build_sale_tab()
        self._build_history_tab()

        self.refresh_employee_list()
        self.refresh_customer_list()
        self.refresh_categories()
        self.refresh_history_table()

    # ==================== Вкладка оформления заказа ====================
    def _build_sale_tab(self):
        # --- Панель сотрудника и клиента ---
        top_frame = ttk.LabelFrame(self.tab_sale, text="Данные заказа", padding=10)
        top_frame.pack(fill='x', padx=10, pady=5)

        ttk.Label(top_frame, text="Менеджер:").grid(row=0, column=0, padx=5, sticky='w')
        self.emp_var = tk.StringVar()
        self.emp_combo = ttk.Combobox(top_frame, textvariable=self.emp_var, state="readonly", width=35)
        self.emp_combo.grid(row=0, column=1, padx=5, pady=2)
        self.emp_combo.bind('<<ComboboxSelected>>', self._on_emp_selected)

        ttk.Label(top_frame, text="Клиент:").grid(row=0, column=2, padx=5, sticky='w')
        self.cust_var = tk.StringVar()
        self.cust_combo = ttk.Combobox(top_frame, textvariable=self.cust_var, state="readonly", width=35)
        self.cust_combo.grid(row=0, column=3, padx=5, pady=2)

        # --- Панель выбора автомобиля ---
        car_frame = ttk.LabelFrame(self.tab_sale, text="Выбор автомобиля", padding=10)
        car_frame.pack(fill='x', padx=10, pady=5)

        ttk.Label(car_frame, text="Категория:").grid(row=0, column=0, padx=5, sticky='w')
        self.cat_var = tk.StringVar()
        self.cat_combo = ttk.Combobox(car_frame, textvariable=self.cat_var, state="readonly", width=30)
        self.cat_combo.grid(row=0, column=1, padx=5, pady=2)
        self.cat_combo.bind('<<ComboboxSelected>>', self.update_car_list)

        self.in_stock_var = tk.BooleanVar(value=False)
        self.in_stock_check = ttk.Checkbutton(car_frame, text="Только в наличии",
                                              variable=self.in_stock_var,
                                              command=self.update_car_list)
        self.in_stock_check.grid(row=0, column=2, padx=20, sticky='w')

        # Дополнительные фильтры
        filter_frame = ttk.LabelFrame(car_frame, text="Дополнительные фильтры", padding=5)
        filter_frame.grid(row=1, column=0, columnspan=3, pady=5, sticky='ew')

        ttk.Label(filter_frame, text="Руль:").grid(row=0, column=0, padx=2, sticky='w')
        self.steering_var = tk.StringVar(value='Все')
        steering_combo = ttk.Combobox(filter_frame, textvariable=self.steering_var,
                                      values=['Все', 'Левый', 'Правый'], state="readonly", width=10)
        steering_combo.grid(row=0, column=1, padx=2)
        steering_combo.bind('<<ComboboxSelected>>', lambda e: self.update_car_list())

        ttk.Label(filter_frame, text="Мощность (л.с.):").grid(row=0, column=2, padx=5, sticky='w')
        self.power_from_var = tk.StringVar()
        self.power_from_entry = ttk.Entry(filter_frame, textvariable=self.power_from_var, width=5)
        self.power_from_entry.grid(row=0, column=3, padx=2)
        ttk.Label(filter_frame, text="—").grid(row=0, column=4)
        self.power_to_var = tk.StringVar()
        self.power_to_entry = ttk.Entry(filter_frame, textvariable=self.power_to_var, width=5)
        self.power_to_entry.grid(row=0, column=5, padx=2)
        self.power_from_entry.bind('<KeyRelease>', lambda e: self.update_car_list())
        self.power_to_entry.bind('<KeyRelease>', lambda e: self.update_car_list())

        ttk.Label(filter_frame, text="Топливо:").grid(row=0, column=6, padx=5, sticky='w')
        self.fuel_var = tk.StringVar(value='Все')
        fuel_combo = ttk.Combobox(filter_frame, textvariable=self.fuel_var,
                                  values=['Все', 'Бензин', 'Дизель', 'Гибрид', 'Электро'],
                                  state="readonly", width=12)
        fuel_combo.grid(row=0, column=7, padx=2)
        fuel_combo.bind('<<ComboboxSelected>>', lambda e: self.update_car_list())

        ttk.Label(filter_frame, text="КПП:").grid(row=1, column=0, padx=2, sticky='w')
        self.transmission_var = tk.StringVar(value='Все')
        trans_combo = ttk.Combobox(filter_frame, textvariable=self.transmission_var,
                                   values=['Все', 'Механика', 'Автомат', 'Робот', 'Вариатор'],
                                   state="readonly", width=12)
        trans_combo.grid(row=1, column=1, padx=2, columnspan=2, sticky='w')
        trans_combo.bind('<<ComboboxSelected>>', lambda e: self.update_car_list())

        ttk.Label(filter_frame, text="Привод:").grid(row=1, column=3, padx=2, sticky='w')
        self.drive_var = tk.StringVar(value='Все')
        drive_combo = ttk.Combobox(filter_frame, textvariable=self.drive_var,
                                   values=['Все', 'Передний', 'Задний', 'Полный'],
                                   state="readonly", width=12)
        drive_combo.grid(row=1, column=4, padx=2, columnspan=2, sticky='w')
        drive_combo.bind('<<ComboboxSelected>>', lambda e: self.update_car_list())

        ttk.Label(filter_frame, text="Состояние:").grid(row=1, column=6, padx=2, sticky='w')
        self.condition_var = tk.StringVar(value='Все')
        cond_combo = ttk.Combobox(filter_frame, textvariable=self.condition_var,
                                  values=['Все', 'Новый', 'С пробегом'],
                                  state="readonly", width=12)
        cond_combo.grid(row=1, column=7, padx=2)
        cond_combo.bind('<<ComboboxSelected>>', lambda e: self.update_car_list())

        # Выбор автомобиля
        ttk.Label(car_frame, text="Автомобиль:").grid(row=2, column=0, padx=5, sticky='w', pady=5)
        self.car_var = tk.StringVar()
        self.car_combo = ttk.Combobox(car_frame, textvariable=self.car_var, state="readonly", width=70)
        self.car_combo.grid(row=2, column=1, columnspan=2, padx=5, pady=5, sticky='ew')
        self.car_combo.bind('<<ComboboxSelected>>', self._on_car_selected)

        # Счётчик найденных автомобилей (новый элемент)
        self.car_count_label = ttk.Label(car_frame, text="", font=('Arial', 9, 'italic'))
        self.car_count_label.grid(row=3, column=0, columnspan=3, pady=(0, 5), sticky='w')

        # Информация об автомобиле
        info_frame = ttk.Frame(car_frame)
        info_frame.grid(row=4, column=0, columnspan=3, pady=5, sticky='w')
        self.lbl_car_info = tk.Text(info_frame, height=6, width=90, font=('Arial', 9), wrap='word', state='disabled')
        self.lbl_car_info.pack(side='left')
        self.lbl_stock_status = ttk.Label(info_frame, text="", font=('Arial', 10, 'bold'))
        self.lbl_stock_status.pack(side='left', padx=15)

        # Добавление в корзину
        add_frame = ttk.Frame(car_frame)
        add_frame.grid(row=5, column=0, columnspan=3, pady=10)
        ttk.Label(add_frame, text="Количество:").pack(side='left', padx=5)
        self.qty_entry = ttk.Entry(add_frame, width=8)
        self.qty_entry.insert(0, "1")
        self.qty_entry.pack(side='left', padx=5)
        ttk.Button(add_frame, text="Добавить в корзину", command=self.add_to_cart).pack(side='left', padx=20)

        # --- Корзина ---
        cart_frame = ttk.LabelFrame(self.tab_sale, text="Корзина", padding=10)
        cart_frame.pack(fill='both', expand=True, padx=10, pady=5)

        self.cart_listbox = tk.Listbox(cart_frame, height=8, width=110, font=('Consolas', 10))
        self.cart_listbox.pack(fill='both', expand=True, pady=5)
        self.cart_listbox.bind('<Double-Button-1>', lambda e: self.remove_selected())

        cart_btn_frame = ttk.Frame(cart_frame)
        cart_btn_frame.pack()
        ttk.Button(cart_btn_frame, text="Удалить выбранное", command=self.remove_selected).pack(side='left', padx=5)
        ttk.Button(cart_btn_frame, text="Очистить корзину", command=self.clear_cart).pack(side='left', padx=5)

        # Кнопка оформления заказа
        ttk.Button(self.tab_sale, text="Оформить заказ", command=self.finalize_purchase).pack(pady=10)

    # ==================== Вкладка истории заказов ====================
    def _build_history_tab(self):
        columns = ('id', 'date', 'customer', 'employee', 'amount', 'status')
        self.history_tree = ttk.Treeview(self.tab_history, columns=columns, show='headings', height=15)
        self.history_tree.heading('id', text='№')
        self.history_tree.heading('date', text='Дата и время')
        self.history_tree.heading('customer', text='Клиент')
        self.history_tree.heading('employee', text='Менеджер')
        self.history_tree.heading('amount', text='Сумма')
        self.history_tree.heading('status', text='Статус')

        self.history_tree.column('id', width=50, anchor='center')
        self.history_tree.column('date', width=150, anchor='center')
        self.history_tree.column('customer', width=180)
        self.history_tree.column('employee', width=180)
        self.history_tree.column('amount', width=120, anchor='e')
        self.history_tree.column('status', width=120, anchor='center')

        self.history_tree.pack(fill='both', expand=True, padx=5, pady=5)

        scrollbar = ttk.Scrollbar(self.tab_history, orient='vertical', command=self.history_tree.yview)
        self.history_tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right', fill='y')

        btn_frame = ttk.Frame(self.tab_history)
        btn_frame.pack(pady=5)
        ttk.Button(btn_frame, text="Обновить", command=self.refresh_history_table).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="Детали заказа", command=self.show_sale_details).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="Топ продаж", command=self.show_top_sales).pack(side='left', padx=5)
        self.history_tree.bind('<Double-1>', lambda e: self.show_sale_details())
        # --- Загрузка CSV и отчёты ---
        report_frame = ttk.LabelFrame(self.tab_history, text="Отчёты и загрузка данных", padding=10)
        report_frame.pack(fill='x', padx=10, pady=5)

        ttk.Button(report_frame, text="Загрузить автомобили из CSV",
                   command=self.load_cars_from_csv).pack(side='left', padx=5)

        report_date_frame = ttk.Frame(report_frame)
        report_date_frame.pack(side='left', padx=20)

        ttk.Button(report_date_frame, text="Сегодня",
                   command=lambda: self._display_report(datetime.now().strftime("%Y-%m-%d"))
                   ).pack(side='left', padx=2)
        ttk.Label(report_date_frame, text="Дата (ГГГГ-ММ-ДД):").pack(side='left', padx=2)
        self.date_entry = ttk.Entry(report_date_frame, width=12)
        self.date_entry.pack(side='left', padx=2)
        ttk.Button(report_date_frame, text="Показать",
                   command=lambda: self._display_report(self.date_entry.get().strip())
                   ).pack(side='left', padx=2)

        self.text_area = tk.Text(self.tab_history, height=8, width=100, font=('Consolas', 9))
        self.text_area.pack(fill='x', padx=10, pady=5)

    def refresh_history_table(self):
        for row in self.history_tree.get_children():
            self.history_tree.delete(row)
        sales = get_sales_list(self.conn)
        for sale in sales:
            sale_id, date, cust, emp, amount, all_in_stock = sale
            # Определяем статус заказа
            if all_in_stock is None:
                status = "—"
            elif all_in_stock == 1:
                status = "Готов к выдаче"
            else:
                status = "Предзаказ"
            self.history_tree.insert('', 'end', values=(
                sale_id, date, cust, emp, f"{amount:,.2f} руб.", status
            ))

    def show_sale_details(self):
        selection = self.history_tree.selection()
        if not selection:
            messagebox.showinfo("Информация", "Выберите заказ в таблице.")
            return
        sale_id = self.history_tree.item(selection[0])['values'][0]
        details = get_sale_details(self.conn, sale_id)
        if not details:
            messagebox.showinfo("Заказ", "Нет данных о составе.")
            return

        win = tk.Toplevel(self.root)
        win.title(f"Детали заказа №{sale_id}")
        win.geometry("1050x400")

        # Колонки с расширенной информацией
        columns = ('brand', 'model', 'year', 'engine', 'fuel', 'trans', 'drive',
                   'qty', 'price', 'subtotal', 'status', 'id_car')
        tree = ttk.Treeview(win, columns=columns, show='headings')
        tree.heading('brand', text='Марка')
        tree.heading('model', text='Модель')
        tree.heading('year', text='Год')
        tree.heading('engine', text='Двигатель')
        tree.heading('fuel', text='Топливо')
        tree.heading('trans', text='КПП')
        tree.heading('drive', text='Привод')
        tree.heading('qty', text='Кол-во')
        tree.heading('price', text='Цена за ед.')
        tree.heading('subtotal', text='Сумма')
        tree.heading('status', text='Статус')
        tree.heading('id_car', text='')  # скрытый

        tree.column('brand', width=100)
        tree.column('model', width=100)
        tree.column('year', width=50, anchor='center')
        tree.column('engine', width=80, anchor='center')
        tree.column('fuel', width=80, anchor='center')
        tree.column('trans', width=80, anchor='center')
        tree.column('drive', width=80, anchor='center')
        tree.column('qty', width=60, anchor='center')
        tree.column('price', width=100, anchor='e')
        tree.column('subtotal', width=100, anchor='e')
        tree.column('status', width=100, anchor='center')
        tree.column('id_car', width=0, stretch=False)

        for d in details:
            brand, model, year, eng, fuel, trans, drive, qty, price, subtotal, car_id, in_stock = d
            engine_str = f"{eng} л" if eng else "—"
            fuel_str = {"petrol": "Бензин", "diesel": "Дизель", "hybrid": "Гибрид", "electric": "Электро"}.get(fuel, fuel)
            trans_str = {"manual": "Механика", "automatic": "Автомат", "robot": "Робот", "variator": "Вариатор"}.get(trans, trans)
            drive_str = {"front": "Передний", "rear": "Задний", "all": "Полный"}.get(drive, drive)
            status_str = "В наличии" if in_stock else "Предзаказ"
            tree.insert('', 'end', values=(
                brand, model, year, engine_str, fuel_str, trans_str, drive_str,
                qty, f"{price:,.2f}", f"{subtotal:,.2f}", status_str, car_id
            ))

        tree.pack(fill='both', expand=True, padx=5, pady=5)
        tree.bind('<Double-1>', lambda e: self._on_detail_double_click(tree))

    def _on_detail_double_click(self, tree):
        selection = tree.selection()
        if not selection:
            return
        values = tree.item(selection[0])['values']
        car_id = values[-1]
        self.show_car_details(car_id)

    def show_car_details(self, car_id):
        info = get_car_info(self.conn, car_id)
        if not info:
            messagebox.showerror("Ошибка", "Автомобиль не найден.")
            return

        win = tk.Toplevel(self.root)
        win.title(f"Информация об автомобиле: {info['description']}")
        win.geometry("500x300")

        text = tk.Text(win, wrap='word', font=('Arial', 11))
        text.pack(fill='both', expand=True, padx=10, pady=10)

        lines = [
            f"Марка/Модель: {info['description']}",
            f"Год выпуска: {info['year']}",
            f"Цвет: {info['color']}",
            f"Цена: {info['price']:,.2f} руб.",
            f"Руль: {info['steering']}",
            f"Мощность: {info['power']} л.с.",
            f"Объём двигателя: {info['engine_volume']} л" if info['engine_volume'] else "Объём двигателя: не указан",
            f"Топливо: {info['fuel_type']}",
            f"Коробка передач: {info['transmission']}",
            f"Привод: {info['drive']}",
            f"Состояние: {info['condition']}" + (f", пробег: {info['mileage']} км" if info['mileage'] else ""),
            f"Остаток на складе: {info['stock']} шт.",
            f"Статус: {'✔ В наличии' if info['in_stock'] else '✘ Нет в наличии'}"
        ]
        text.insert(tk.END, "\n".join(lines))
        text.config(state='disabled')

    def show_top_sales(self):
        query = '''
            SELECT c.brand, c.model,
                   SUM(sd.quantity) AS total_qty,
                   SUM(sd.quantity * sd.price_at_sale) AS total_revenue
            FROM sale_details sd
            JOIN cars c ON sd.id_car = c.id
            GROUP BY c.id
            ORDER BY total_qty DESC
            LIMIT 10
        '''
        rows = self.conn.execute(query).fetchall()
        if not rows:
            messagebox.showinfo("Топ продаж", "Пока нет данных о продажах.")
            return

        win = tk.Toplevel(self.root)
        win.title("Топ-10 продаваемых автомобилей")
        win.geometry("700x350")

        tree = ttk.Treeview(win, columns=('brand', 'model', 'qty', 'revenue'), show='headings')
        tree.heading('brand', text='Марка')
        tree.heading('model', text='Модель')
        tree.heading('qty', text='Продано, шт.')
        tree.heading('revenue', text='Выручка, руб.')

        tree.column('brand', width=150)
        tree.column('model', width=150)
        tree.column('qty', width=100, anchor='center')
        tree.column('revenue', width=150, anchor='e')

        for row in rows:
            brand, model, qty, revenue = row
            tree.insert('', 'end', values=(brand, model, qty, f"{revenue:,.2f}"))

        tree.pack(fill='both', expand=True, padx=5, pady=5)

    # ==================== Общие методы ====================
    def refresh_employee_list(self):
        rows = self.conn.execute('''
            SELECT e.id, e.name, e.surname, j.name
            FROM employees e JOIN job_titles j ON e.id_job_title = j.id
        ''').fetchall()
        self.emp_map = {f"{n} {s} ({j})": eid for eid, n, s, j in rows}
        self.emp_combo['values'] = list(self.emp_map.keys())
        if self.emp_map:
            self.emp_combo.current(0)
        self._on_emp_selected()

    def _on_emp_selected(self, _event=None):
        self.current_emp_id = self.emp_map.get(self.emp_var.get())

    def refresh_customer_list(self):
        rows = self.conn.execute(
            "SELECT id, first_name, last_name, phone FROM customers ORDER BY last_name"
        ).fetchall()
        self.cust_map = {f"{fn} {ln} ({ph})": cid for cid, fn, ln, ph in rows}
        self.cust_combo['values'] = list(self.cust_map.keys())
        if self.cust_map:
            self.cust_combo.current(0)

    def refresh_categories(self):
        rows = self.conn.execute(
            "SELECT id, name FROM car_categories ORDER BY name"
        ).fetchall()
        self.cat_map = {name: cid for cid, name in rows}
        self.cat_combo['values'] = list(self.cat_map.keys())
        if self.cat_map:
            self.cat_combo.current(0)
            self.update_car_list()
        else:
            self.car_combo['values'] = []
            self.cars = {}

    def update_car_list(self, _event=None):
        """Обновляет список автомобилей с учётом всех фильтров и показывает остатки."""
        cid = self.cat_map.get(self.cat_var.get()) if self.cat_var.get() else None
        conditions = []
        params = []

        # Фильтр по категории
        if cid:
            conditions.append("id_category = ?")
            params.append(cid)

        # Наличие
        if self.in_stock_var.get():
            conditions.append("quantity > 0")

        # Руль
        steering = self.steering_var.get()
        if steering == 'Левый':
            conditions.append("steering = 'left'")
        elif steering == 'Правый':
            conditions.append("steering = 'right'")

        # Мощность
        power_from = self.power_from_var.get().strip()
        power_to = self.power_to_var.get().strip()
        if power_from:
            try:
                p_from = int(power_from)
                conditions.append("power >= ?")
                params.append(p_from)
            except ValueError:
                pass
        if power_to:
            try:
                p_to = int(power_to)
                conditions.append("power <= ?")
                params.append(p_to)
            except ValueError:
                pass

        # Топливо
        fuel = self.fuel_var.get()
        fuel_map = {'Бензин': 'petrol', 'Дизель': 'diesel', 'Гибрид': 'hybrid', 'Электро': 'electric'}
        if fuel in fuel_map:
            conditions.append("fuel_type = ?")
            params.append(fuel_map[fuel])

        # КПП
        trans = self.transmission_var.get()
        trans_map = {'Механика': 'manual', 'Автомат': 'automatic', 'Робот': 'robot', 'Вариатор': 'variator'}
        if trans in trans_map:
            conditions.append("transmission = ?")
            params.append(trans_map[trans])

        # Привод
        drive = self.drive_var.get()
        drive_map = {'Передний': 'front', 'Задний': 'rear', 'Полный': 'all'}
        if drive in drive_map:
            conditions.append("drive = ?")
            params.append(drive_map[drive])

        # Состояние
        cond = self.condition_var.get()
        cond_map = {'Новый': 'new', 'С пробегом': 'used'}
        if cond in cond_map:
            conditions.append("condition = ?")
            params.append(cond_map[cond])

        query = "SELECT id, brand, model, year, price, quantity FROM cars"
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY quantity DESC, brand ASC"

        rows = self.conn.execute(query, params).fetchall()
        self.cars = {}
        for row in rows:
            car_id, brand, model, year, price, stock = row
            if stock > 0:
                stock_text = f"В наличии: {stock} шт."
            else:
                stock_text = "Нет в наличии"
            label = f"{brand} {model} ({year}) — {price:,.0f} руб. [{stock_text}]"
            self.cars[label] = car_id

        self.car_combo['values'] = list(self.cars.keys())
        # Счётчик найденных автомобилей
        self.car_count_label.config(text=f"Найдено автомобилей: {len(self.cars)}")

        if self.cars:
            self.car_combo.current(0)
            self._on_car_selected()
        else:
            self.car_combo.set('')
            self._update_car_info_display(None)
            self.lbl_stock_status.config(text="")

    def _on_car_selected(self, event=None):
        selected = self.car_var.get()
        if selected not in self.cars:
            self._update_car_info_display(None)
            self.lbl_stock_status.config(text="")
            return
        car_id = self.cars[selected]
        info = get_car_info(self.conn, car_id)
        self._update_car_info_display(info)
        if info:
            if info['in_stock']:
                self.lbl_stock_status.config(text="✔ В наличии", style='Green.TLabel')
            else:
                self.lbl_stock_status.config(text="✘ Нет в наличии", style='Red.TLabel')
        else:
            self.lbl_stock_status.config(text="")

    def _update_car_info_display(self, info):
        """Обновляет текстовое поле с информацией об автомобиле."""
        self.lbl_car_info.config(state='normal')
        self.lbl_car_info.delete(1.0, tk.END)
        if info:
            lines = [
                f"Марка/Модель: {info['description']}",
                f"Год: {info['year']}, Цвет: {info['color']}, Цена: {info['price']:,.0f} руб.",
                f"Руль: {info['steering']}, Мощность: {info['power']} л.с., Объём: {info['engine_volume']} л",
                f"Топливо: {info['fuel_type']}, КПП: {info['transmission']}, Привод: {info['drive']}",
                f"Состояние: {info['condition']}" + (f", Пробег: {info['mileage']} км" if info['mileage'] else ""),
            ]
            self.lbl_car_info.insert(tk.END, "\n".join(lines))
        else:
            self.lbl_car_info.insert(tk.END, "Автомобиль не выбран")
        self.lbl_car_info.config(state='disabled')

    def add_to_cart(self):
        if not self.cars:
            messagebox.showerror("Ошибка", "Нет доступных автомобилей в категории.")
            return
        selected = self.car_var.get()
        if selected not in self.cars:
            messagebox.showerror("Ошибка", "Выберите автомобиль.")
            return
        try:
            qty = int(self.qty_entry.get())
            if qty <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Ошибка", "Количество должно быть целым положительным числом.")
            return

        car_id = self.cars[selected]
        info = get_car_info(self.conn, car_id)
        if not info:
            return

        self.cart.append({
            'car_id': car_id,
            'description': info['description'],
            'quantity': qty,
            'price_at_sale': info['price'],
            'in_stock': info['in_stock']
        })
        self.update_cart_display()
        self.qty_entry.delete(0, tk.END)
        self.qty_entry.insert(0, "1")

    def update_cart_display(self):
        self.cart_listbox.delete(0, tk.END)
        grouped = defaultdict(lambda: {'desc': '', 'qty': 0, 'price': 0.0, 'in_stock': True})
        for item in self.cart:
            g = grouped[item['car_id']]
            g['desc'] = item['description']
            g['qty'] += item['quantity']
            g['price'] = item['price_at_sale']
            g['in_stock'] = g['in_stock'] and item['in_stock']

        total = 0.0
        for g in grouped.values():
            subtotal = g['qty'] * g['price']
            status = "✔" if g['in_stock'] else "✘ (предзаказ)"
            self.cart_listbox.insert(tk.END,
                f"{status} {g['desc']}  × {g['qty']} = {subtotal:,.2f} руб.")
            total += subtotal
        self.cart_listbox.insert(tk.END, f"--- ИТОГО: {total:,.2f} руб. ---")

    def remove_selected(self):
        sel = self.cart_listbox.curselection()
        if sel and sel[0] < len(self.cart):
            del self.cart[sel[0]]
            self.update_cart_display()

    def clear_cart(self):
        self.cart.clear()
        self.update_cart_display()

    def finalize_purchase(self):
        if not getattr(self, 'current_emp_id', None):
            messagebox.showerror("Ошибка", "Выберите менеджера.")
            return
        cust_key = self.cust_var.get()
        if not cust_key or cust_key not in self.cust_map:
            messagebox.showerror("Ошибка", "Выберите клиента из списка.")
            return
        customer_id = self.cust_map[cust_key]
        if not self.cart:
            messagebox.showerror("Ошибка", "Корзина пуста.")
            return

        ok, msg = finalize_sale(self.conn, self.cart, self.current_emp_id, customer_id)
        if ok:
            messagebox.showinfo("Успех", f"Заказ №{msg} оформлен. Спасибо!")
            self.cart.clear()
        else:
            messagebox.showerror("Ошибка", msg)
        self.update_cart_display()
        self.refresh_categories()
        self.refresh_history_table()

    def load_cars_from_csv(self):
        filepath = filedialog.askopenfilename(filetypes=[("CSV files", "*.csv")])
        if not filepath:
            return
        cur = self.conn.cursor()
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    brand = row.get('brand', '').strip()
                    model = row.get('model', '').strip()
                    if not brand or not model:
                        continue
                    try:
                        year = int(row['year'])
                        color = row.get('color', '').strip()
                        vin = row['vin'].strip()
                        price = float(row['price'])
                        qty = int(row['quantity'])
                        cat_name = row['category'].strip()
                        steering = row.get('steering', 'left').strip().lower()
                        power = int(row['power'])
                        engine_volume = float(row['engine_volume']) if row.get('engine_volume') else None
                        fuel_type = row.get('fuel_type', '').strip().lower()
                        transmission = row.get('transmission', '').strip().lower()
                        drive = row.get('drive', '').strip().lower()
                        condition = row.get('condition', 'new').strip().lower()
                        mileage = int(row['mileage']) if row.get('mileage') and row['mileage'].strip() else None
                    except (KeyError, ValueError) as e:
                        continue

                    cat_row = cur.execute(
                        "SELECT id FROM car_categories WHERE name = ?", (cat_name,)
                    ).fetchone()
                    if cat_row:
                        cat_id = cat_row[0]
                    else:
                        cur.execute("INSERT INTO car_categories (name) VALUES (?)", (cat_name,))
                        cat_id = cur.lastrowid

                    exist = cur.execute(
                        "SELECT id, quantity FROM cars WHERE vin = ?", (vin,)
                    ).fetchone()
                    if exist:
                        cur.execute(
                            "UPDATE cars SET price=?, quantity=quantity+?, id_category=?, steering=?, "
                            "power=?, engine_volume=?, fuel_type=?, transmission=?, drive=?, "
                            "condition=?, mileage=? WHERE id=?",
                            (price, qty, cat_id, steering, power, engine_volume, fuel_type,
                             transmission, drive, condition, mileage, exist[0])
                        )
                    else:
                        cur.execute(
                            "INSERT INTO cars (brand, model, year, color, vin, price, quantity, id_category, "
                            "steering, power, engine_volume, fuel_type, transmission, drive, condition, mileage) "
                            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            (brand, model, year, color, vin, price, qty, cat_id,
                             steering, power, engine_volume, fuel_type, transmission, drive, condition, mileage)
                        )
            self.conn.commit()
            messagebox.showinfo("Успех", "Автомобили загружены из CSV.")
            self.refresh_categories()
        except Exception as e:
            messagebox.showerror("Ошибка", f"Ошибка загрузки:\n{e}")

    def _display_report(self, date_str):
        if not date_str:
            messagebox.showerror("Ошибка", "Введите дату в формате ГГГГ-ММ-ДД")
            return
        data = get_report(self.conn, date_str)
        self.text_area.delete(1.0, tk.END)
        if not data:
            self.text_area.insert(tk.END, f"За {date_str} заказов нет.")
            return
        total = sum(rev for _, _, rev in data)
        lines = [f"Отчёт за {date_str}:\n"]
        lines += [f"{desc}: {qty} шт. → {rev:,.2f} руб." for desc, qty, rev in data]
        lines += [f"\nИтого выручка: {total:,.2f} руб."]
        self.text_area.insert(tk.END, "\n".join(lines))

    def __del__(self):
        if hasattr(self, 'conn'):
            self.conn.close()

if __name__ == "__main__":
    root = tk.Tk()
    app = AutoDealerApp(root)
    root.mainloop()