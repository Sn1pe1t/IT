import sqlite3
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime
from collections import defaultdict
import csv
import os

DB_NAME = 'store.db'

SCHEMA = '''
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS jobs_titles (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS emploees (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    surnaame TEXT NOT NULL,
    id_job_title INTEGER NOT NULL,
    FOREIGN KEY (id_job_title) REFERENCES jobs_titles(id)
);
CREATE TABLE IF NOT EXISTS categories (
    id_category INTEGER PRIMARY KEY, name_category TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS producrs (
    id_product INTEGER PRIMARY KEY,
    name_of_product TEXT NOT NULL,
    price REAL NOT NULL,
    id_category INTEGER NOT NULL,
    quantity_at_storage REAL NOT NULL,
    FOREIGN KEY (id_category) REFERENCES categories(id_category)
);
CREATE TABLE IF NOT EXISTS reseipts (
    id_check INTEGER PRIMARY KEY,
    created_at REAL NOT NULL,
    id_cashier INTEGER NOT NULL,
    FOREIGN KEY (id_cashier) REFERENCES emploees(id)
);
CREATE TABLE IF NOT EXISTS sale_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    id_check INTEGER NOT NULL,
    id_product INTEGER NOT NULL,
    quantity REAL NOT NULL,
    price_at_sale REAL NOT NULL,
    FOREIGN KEY (id_check) REFERENCES reseipts(id_check),
    FOREIGN KEY (id_product) REFERENCES producrs(id_product)
);
'''

def init_db():
    conn = sqlite3.connect(DB_NAME)
    conn.executescript(SCHEMA)
    conn.execute("INSERT OR IGNORE INTO jobs_titles (name) VALUES ('Кассир')")
    conn.commit()
    return conn

def get_product_info(conn, product_id):
    row = conn.execute(
        "SELECT name_of_product, price, quantity_at_storage FROM producrs WHERE id_product = ?",
        (product_id,)
    ).fetchone()
    return {"name": row[0], "price": row[1], "stock": row[2]} if row else None

def finalize_sale(conn, cart_items, id_cashier):
    cur = conn.cursor()
    try:
        totals = defaultdict(float)
        for item in cart_items:
            totals[item['product_id']] += item['quantity']

        for pid, needed in totals.items():
            stock, name = cur.execute(
                "SELECT quantity_at_storage, name_of_product FROM producrs WHERE id_product = ?", (pid,)
            ).fetchone()
            if needed > stock:
                return False, f"Недостаточно товара: {name} (доступно {stock})"

        id_check = cur.execute(
            "INSERT INTO reseipts (created_at, id_cashier) VALUES (?, ?)",
            (datetime.now().timestamp(), id_cashier)
        ).lastrowid

        for item in cart_items:
            cur.execute(
                "INSERT INTO sale_items (id_check, id_product, quantity, price_at_sale) VALUES (?, ?, ?, ?)",
                (id_check, item['product_id'], item['quantity'], item['price_at_sale'])
            )
            cur.execute(
                "UPDATE producrs SET quantity_at_storage = quantity_at_storage - ? WHERE id_product = ?",
                (item['quantity'], item['product_id'])
            )

        conn.commit()
        return True, id_check
    except Exception as e:
        conn.rollback()
        return False, str(e)

def get_report(conn, date_str):
    return conn.execute('''
        SELECT p.name_of_product, SUM(si.quantity), SUM(si.quantity * si.price_at_sale)
        FROM sale_items si
        JOIN producrs p ON si.id_product = p.id_product
        JOIN reseipts r ON si.id_check = r.id_check
        WHERE DATE(r.created_at, 'unixepoch') = ?
        GROUP BY p.id_product
        ORDER BY p.name_of_product
    ''', (date_str,)).fetchall()

class StoreApp:
    def __init__(self, root):
        self.conn = init_db()
        self.root = root
        self.root.title("Продажи в магазине")
        self.root.geometry("850x650")
        self.cart = []
        self.products = {}
        
        # Автоматическая загрузка кассиров (если есть файл cashiers.csv)
        self.auto_load_cashiers()
        
        # Построение интерфейса (все виджеты)
        self._build_ui()
        
        # Обновление списков (кассиры, категории)
        self.refresh_cashier_list()
        self.refresh_categories()

    def _build_ui(self):
        # Кассир
        frame_cashier = tk.Frame(self.root)
        frame_cashier.pack(pady=5)
        tk.Label(frame_cashier, text="Кассир:").grid(row=0, column=0, padx=5)
        self.cashier_var = tk.StringVar()
        self.cashier_combo = ttk.Combobox(frame_cashier, textvariable=self.cashier_var,
                                          state="readonly", width=50)
        self.cashier_combo.grid(row=0, column=1, padx=5)
        self.cashier_combo.bind('<<ComboboxSelected>>', self._on_cashier_selected)

        # Выбор товара
        frame_select = tk.Frame(self.root)
        frame_select.pack(pady=10)
        tk.Label(frame_select, text="Категория:").grid(row=0, column=0, padx=5)
        self.category_var = tk.StringVar()
        self.category_combo = ttk.Combobox(frame_select, textvariable=self.category_var,
                                           state="readonly", width=50)
        self.category_combo.grid(row=0, column=1, padx=5)
        self.category_combo.bind('<<ComboboxSelected>>', self.on_category_selected)

        tk.Label(frame_select, text="Товар:").grid(row=1, column=0, padx=5, pady=5)
        self.product_var = tk.StringVar()
        self.product_combo = ttk.Combobox(frame_select, textvariable=self.product_var,
                                          state="readonly", width=50)
        self.product_combo.grid(row=1, column=1, padx=5, pady=5)
        tk.Label(frame_select, text="Кол-во:").grid(row=1, column=2, padx=5)
        self.qty_entry = tk.Entry(frame_select, width=10)
        self.qty_entry.insert(0, "1")
        self.qty_entry.grid(row=1, column=3, padx=5)
        tk.Button(frame_select, text="Добавить в корзину",
                  command=self.add_to_cart).grid(row=1, column=4, padx=5)

        # Корзина
        tk.Label(self.root, text="Корзина (дважды кликните для удаления):",
                 font=('Arial', 10, 'bold')).pack(pady=(10, 0))
        self.cart_listbox = tk.Listbox(self.root, height=10, width=90)
        self.cart_listbox.pack(pady=5)
        self.cart_listbox.bind('<Double-Button-1>', lambda e: self.remove_selected())

        frame_cart_buttons = tk.Frame(self.root)
        frame_cart_buttons.pack(pady=5)
        tk.Button(frame_cart_buttons, text="Удалить выбранный",
                  command=self.remove_selected).pack(side=tk.LEFT, padx=5)
        tk.Button(frame_cart_buttons, text="Очистить корзину",
                  command=self.clear_cart).pack(side=tk.LEFT, padx=5)

        # Кнопки: Оформить покупку и Загрузить товары
        btn_frame = tk.Frame(self.root)
        btn_frame.pack(pady=10)
        tk.Button(btn_frame, text="Оформить покупку", command=self.finalize_purchase,
                  bg="green", fg="white", font=('Arial', 10, 'bold')).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Загрузить товары из CSV", 
                  command=self.load_products_from_csv).pack(side=tk.LEFT, padx=5)

        # Отчёты
        frame_reports = tk.Frame(self.root)
        frame_reports.pack(pady=10)
        tk.Button(frame_reports, text="Отчёт за сегодня",
                  command=lambda: self._display_report(datetime.now().strftime("%Y-%m-%d"))
                  ).pack(side=tk.LEFT, padx=5)
        tk.Label(frame_reports, text="Дата (ГГГГ-ММ-ДД):").pack(side=tk.LEFT, padx=5)
        self.date_entry = tk.Entry(frame_reports, width=12)
        self.date_entry.pack(side=tk.LEFT, padx=5)
        tk.Button(frame_reports, text="Показать отчёт",
                  command=lambda: self._display_report(self.date_entry.get().strip())
                  ).pack(side=tk.LEFT, padx=5)

        self.text_area = tk.Text(self.root, height=10, width=100)
        self.text_area.pack(pady=10)

    # --- Автозагрузка кассиров (только если файл есть) ---
    def auto_load_cashiers(self):
        if not os.path.exists('cashiers.csv'):
            return
        job_row = self.conn.execute("SELECT id FROM jobs_titles WHERE name = 'Кассир'").fetchone()
        if not job_row:
            return
        job_id = job_row[0]
        added = 0
        try:
            with open('cashiers.csv', 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    name = row.get('name', '').strip()
                    surname = row.get('surnaame', row.get('surname', '')).strip()
                    if not name or not surname:
                        continue
                    exists = self.conn.execute(
                        "SELECT id FROM emploees WHERE name = ? AND surnaame = ?",
                        (name, surname)
                    ).fetchone()
                    if not exists:
                        self.conn.execute(
                            "INSERT INTO emploees (name, surnaame, id_job_title) VALUES (?, ?, ?)",
                            (name, surname, job_id)
                        )
                        added += 1
            self.conn.commit()
            if added:
                print(f"[INFO] Автоматически загружено {added} кассиров из cashiers.csv")
        except Exception as e:
            print(f"[WARN] Не удалось загрузить кассиров: {e}")

    # --- Ручная загрузка товаров из CSV (кнопка) ---
    def load_products_from_csv(self):
        filepath = filedialog.askopenfilename(filetypes=[("CSV files", "*.csv")])
        if not filepath:
            return
        self._load_products_from_file(filepath)

    def _load_products_from_file(self, filepath):
        cur = self.conn.cursor()
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                for row in csv.DictReader(f):
                    name = row.get('name_of_product', '').strip()
                    if not name:
                        continue
                    try:
                        price = float(row['price'])
                        cat = row['category_name'].strip()
                        qty = float(row['quantity_at_storage'])
                    except (KeyError, ValueError):
                        continue

                    cat_row = cur.execute(
                        "SELECT id_category FROM categories WHERE name_category = ?", (cat,)
                    ).fetchone()
                    if cat_row:
                        cat_id = cat_row[0]
                    else:
                        cur.execute("INSERT INTO categories (name_category) VALUES (?)", (cat,))
                        cat_id = cur.lastrowid

                    exist = cur.execute(
                        "SELECT id_product, quantity_at_storage FROM producrs WHERE name_of_product = ?", (name,)
                    ).fetchone()
                    if exist:
                        cur.execute(
                            "UPDATE producrs SET price=?, id_category=?, quantity_at_storage=? WHERE id_product=?",
                            (price, cat_id, exist[1] + qty, exist[0])
                        )
                    else:
                        cur.execute(
                            "INSERT INTO producrs (name_of_product, price, id_category, quantity_at_storage) VALUES (?,?,?,?)",
                            (name, price, cat_id, qty)
                        )
            self.conn.commit()
            messagebox.showinfo("Успех", "Товары загружены")
            self.refresh_categories()
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось загрузить файл:\n{e}")

    # --- Обновление списков ---
    def refresh_cashier_list(self):
        rows = self.conn.execute('''
            SELECT e.id, e.name, e.surnaame, j.name
            FROM emploees e JOIN jobs_titles j ON e.id_job_title = j.id
        ''').fetchall()
        self.cashier_map = {f"{n} {s} ({j})": cid for cid, n, s, j in rows}
        self.cashier_combo['values'] = list(self.cashier_map.keys())
        if self.cashier_map:
            self.cashier_combo.current(0)
        self._on_cashier_selected()

    def _on_cashier_selected(self, _event=None):
        self.current_cashier_id = self.cashier_map.get(self.cashier_var.get())

    def refresh_categories(self):
        rows = self.conn.execute(
            "SELECT id_category, name_category FROM categories ORDER BY name_category"
        ).fetchall()
        self.category_map = {name: cid for cid, name in rows}
        self.category_combo['values'] = list(self.category_map.keys())
        if self.category_map:
            self.category_combo.current(0)
            self.on_category_selected()
        else:
            self.product_combo['values'] = []
            self.products = {}

    def on_category_selected(self, _event=None):
        cid = self.category_map.get(self.category_var.get())
        if not cid:
            self.product_combo['values'] = []
            self.products = {}
            return
        rows = self.conn.execute(
            "SELECT id_product, name_of_product, quantity_at_storage FROM producrs WHERE id_category = ?",
            (cid,)
        ).fetchall()
        self.products = {f"{name} (остаток: {stock})": pid for pid, name, stock in rows}
        self.product_combo['values'] = list(self.products.keys())
        if self.products:
            self.product_combo.current(0)

    # --- Корзина ---
    def add_to_cart(self):
        if not self.products:
            messagebox.showerror("Ошибка", "Нет доступных товаров.")
            return
        selected = self.product_var.get()
        if selected not in self.products:
            messagebox.showerror("Ошибка", "Выберите товар")
            return
        try:
            qty = float(self.qty_entry.get())
            if qty <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Ошибка", "Введите положительное количество")
            return

        product_id = self.products[selected]
        info = get_product_info(self.conn, product_id)
        if not info:
            return

        in_cart = sum(i['quantity'] for i in self.cart if i['product_id'] == product_id)
        if in_cart + qty > info['stock']:
            messagebox.showerror("Ошибка",
                f"Нельзя добавить {qty} шт. '{info['name']}'\n"
                f"В корзине: {in_cart}, на складе: {info['stock']}")
            return

        self.cart.append({'product_id': product_id, 'name': info['name'],
                          'quantity': qty, 'price_at_sale': info['price']})
        self.update_cart_display()
        self.qty_entry.delete(0, tk.END)
        self.qty_entry.insert(0, "1")

    def update_cart_display(self):
        self.cart_listbox.delete(0, tk.END)
        grouped = defaultdict(lambda: {'name': '', 'quantity': 0.0, 'price': 0.0})
        for item in self.cart:
            g = grouped[item['product_id']]
            g['name'] = item['name']
            g['quantity'] += item['quantity']
            g['price'] = item['price_at_sale']

        total = 0.0
        for g in grouped.values():
            subtotal = g['quantity'] * g['price']
            self.cart_listbox.insert(tk.END, f"{g['name']}  × {g['quantity']} = {subtotal:.2f} руб.")
            total += subtotal
        self.cart_listbox.insert(tk.END, f"--- ИТОГО: {total:.2f} руб. ---")

    def remove_selected(self):
        sel = self.cart_listbox.curselection()
        if sel and sel[0] < len(self.cart):
            del self.cart[sel[0]]
            self.update_cart_display()

    def clear_cart(self):
        self.cart.clear()
        self.update_cart_display()

    def finalize_purchase(self):
        if not getattr(self, 'current_cashier_id', None):
            messagebox.showerror("Ошибка", "Выберите кассира.")
            return
        if not self.cart:
            messagebox.showerror("Ошибка", "Корзина пуста")
            return
        ok, msg = finalize_sale(self.conn, self.cart, self.current_cashier_id)
        if ok:
            messagebox.showinfo("Успех", f"Чек №{msg} создан. Спасибо за покупку!")
            self.cart.clear()
        else:
            messagebox.showerror("Ошибка", msg)
        self.update_cart_display()
        self.refresh_categories()

    # --- Отчёты ---
    def _display_report(self, date_str):
        if not date_str:
            messagebox.showerror("Ошибка", "Введите дату в формате ГГГГ-ММ-ДД")
            return
        data = get_report(self.conn, date_str)
        self.text_area.delete(1.0, tk.END)
        if not data:
            self.text_area.insert(tk.END, f"За {date_str} продаж нет.")
            return
        total = sum(rev for _, _, rev in data)
        lines = [f"Отчёт за {date_str}:\n"] + \
                [f"{n}: {q:.2f} шт. → {r:.2f} руб." for n, q, r in data] + \
                [f"\nИтого выручка: {total:.2f} руб."]
        self.text_area.insert(tk.END, "\n".join(lines))

    def __del__(self):
        if hasattr(self, 'conn'):
            self.conn.close()

if __name__ == "__main__":
    root = tk.Tk()
    app = StoreApp(root)
    root.mainloop()