
PRAGMA foreign_keys = ON;


CREATE TABLE IF NOT EXISTS jobs_titles (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);


CREATE TABLE IF NOT EXISTS emploees (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    surnaame TEXT NOT NULL,
    id_job_title INTEGER NOT NULL,
    FOREIGN KEY (id_job_title) REFERENCES jobs_titles(id)
);


CREATE TABLE IF NOT EXISTS categories (
    id_category INTEGER PRIMARY KEY,
    name_category TEXT NOT NULL UNIQUE
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

