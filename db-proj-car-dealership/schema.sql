PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS job_titles (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS employees (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    surname TEXT NOT NULL,
    id_job_title INTEGER NOT NULL,
    FOREIGN KEY (id_job_title) REFERENCES job_titles(id)
);

CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    phone TEXT,
    email TEXT
);

CREATE TABLE IF NOT EXISTS car_categories (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS cars (
    id INTEGER PRIMARY KEY,
    brand TEXT NOT NULL,
    model TEXT NOT NULL,
    year INTEGER,
    color TEXT,
    vin TEXT UNIQUE NOT NULL,
    price REAL NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 1,
    id_category INTEGER NOT NULL,
    steering TEXT NOT NULL DEFAULT 'left',       
    power INTEGER NOT NULL,         
    engine_volume REAL,       
    fuel_type TEXT,         
    transmission TEXT,    
    drive TEXT,  
    condition TEXT DEFAULT 'new',  
    mileage INTEGER, 
    FOREIGN KEY (id_category) REFERENCES car_categories(id)
);

CREATE TABLE IF NOT EXISTS sales (
    id INTEGER PRIMARY KEY,
    sale_date REAL NOT NULL,
    id_customer INTEGER NOT NULL,
    id_employee INTEGER NOT NULL,
    total_amount REAL NOT NULL,
    FOREIGN KEY (id_customer) REFERENCES customers(id),
    FOREIGN KEY (id_employee) REFERENCES employees(id)
);

CREATE TABLE IF NOT EXISTS sale_details (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    id_sale INTEGER NOT NULL,
    id_car INTEGER NOT NULL,
    quantity INTEGER NOT NULL,
    price_at_sale REAL NOT NULL,
    in_stock_at_sale INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (id_sale) REFERENCES sales(id),
    FOREIGN KEY (id_car) REFERENCES cars(id)
);

CREATE TRIGGER IF NOT EXISTS deduct_quantity AFTER INSERT ON sale_details
BEGIN
    UPDATE cars SET quantity = quantity - NEW.quantity WHERE id = NEW.id_car;
END;