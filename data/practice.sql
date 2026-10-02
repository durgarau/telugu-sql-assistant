-- Practice dataset for SQL Mitra. Loaded fresh into an in-memory SQLite DB
-- for every evaluation, so learners can never change it.
-- Order amounts are all distinct so ORDER BY amount + LIMIT has no ties.

CREATE TABLE customers (
    customer_id INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    city        TEXT,
    signup_date TEXT NOT NULL
);

INSERT INTO customers VALUES
    (1,  'Ravi Kumar',     'Hyderabad',     '2025-06-12'),
    (2,  'Lakshmi Devi',   'Vijayawada',    '2025-07-03'),
    (3,  'Suresh Reddy',   'Visakhapatnam', '2025-07-21'),
    (4,  'Anjali Sharma',  'Bangalore',     '2025-08-09'),
    (5,  'Karthik Iyer',   'Chennai',       '2025-08-30'),
    (6,  'Priya Nair',     'Mumbai',        '2025-09-14'),
    (7,  'Rahul Verma',    'Delhi',         '2025-10-02'),
    (8,  'Sneha Patil',    'Pune',          '2025-10-18'),
    (9,  'Venkatesh Rao',  'Hyderabad',     '2025-11-05'),
    (10, 'Divya Teja',     'Vijayawada',    '2025-11-27'),
    (11, 'Mohan Das',      NULL,            '2025-12-10');

CREATE TABLE orders (
    order_id       INTEGER PRIMARY KEY,
    customer_id    INTEGER NOT NULL REFERENCES customers(customer_id),
    city           TEXT NOT NULL,
    status         TEXT NOT NULL,  -- delivered | cancelled | in_transit | returned
    amount         INTEGER NOT NULL,  -- rupees
    payment_method TEXT,           -- UPI | Card | COD | NetBanking | NULL
    order_date     TEXT NOT NULL
);

INSERT INTO orders VALUES
    (1,  1,  'Hyderabad',     'delivered',  1250, 'UPI',        '2026-01-05'),
    (2,  2,  'Vijayawada',    'cancelled',   560, 'COD',        '2026-01-07'),
    (3,  3,  'Visakhapatnam', 'delivered',  3400, 'Card',       '2026-01-09'),
    (4,  4,  'Bangalore',     'in_transit',  890, 'UPI',        '2026-01-11'),
    (5,  5,  'Chennai',       'delivered',  2150, 'NetBanking', '2026-01-12'),
    (6,  1,  'Hyderabad',     'cancelled',  4999, 'Card',       '2026-01-15'),
    (7,  6,  'Mumbai',        'delivered',   720, 'UPI',        '2026-01-18'),
    (8,  7,  'Delhi',         'returned',   1890, 'Card',       '2026-01-20'),
    (9,  8,  'Pune',          'delivered',  5600, 'UPI',        '2026-01-22'),
    (10, 9,  'Hyderabad',     'delivered',   340, 'COD',        '2026-01-25'),
    (11, 10, 'Vijayawada',    'in_transit', 1575, 'UPI',        '2026-01-28'),
    (12, 2,  'Vijayawada',    'delivered',  2680, 'UPI',        '2026-02-01'),
    (13, 3,  'Visakhapatnam', 'cancelled',   150, 'UPI',        '2026-02-03'),
    (14, 4,  'Bangalore',     'delivered',  7250, 'Card',       '2026-02-06'),
    (15, 5,  'Chennai',       'returned',    980, 'COD',        '2026-02-08'),
    (16, 6,  'Mumbai',        'cancelled',  3150, 'NetBanking', '2026-02-10'),
    (17, 7,  'Delhi',         'delivered',  4420, 'UPI',        '2026-02-13'),
    (18, 8,  'Pune',          'in_transit',  610, NULL,         '2026-02-15'),
    (19, 9,  'Hyderabad',     'delivered',  1999, 'UPI',        '2026-02-18'),
    (20, 10, 'Vijayawada',    'delivered',   830, 'COD',        '2026-02-20'),
    (21, 11, 'Hyderabad',     'cancelled',  2240, 'UPI',        '2026-02-22'),
    (22, 1,  'Hyderabad',     'delivered',  6100, 'UPI',        '2026-02-25');
