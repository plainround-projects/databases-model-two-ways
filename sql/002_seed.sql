-- DML: the hand-checkable data of the lesson. 2 customers, 4 items, 7 rentals.
-- Dates are half-open: the second date is the day the item comes back, not a rental day.

INSERT INTO customers (customer_id, name) VALUES (1, 'Ada'), (2, 'Bruno');

INSERT INTO items (item_id, name, daily_rate) VALUES
    (1, 'Drill', 10),
    (2, 'Ladder', 8),
    (3, 'Tent', 15),
    (4, 'Kayak', 20);

INSERT INTO rentals (rental_id, item_id, customer_id, during) VALUES
    (1, 1, 1, daterange('2026-11-01', '2026-11-04')),  -- Drill, Ada, 3 days
    (2, 1, 2, daterange('2026-11-04', '2026-11-06')),  -- Drill, Bruno; touches rental 1 (allowed: 11-04 is free again)
    (3, 2, 1, daterange('2026-11-02', '2026-11-09')),  -- Ladder, Ada, 7 days
    (4, 3, 2, daterange('2026-10-20', '2026-10-23')),  -- Tent, Bruno
    (5, 1, 1, daterange('2026-12-01', '2026-12-03')),  -- Drill, Ada
    (6, 3, 1, daterange('2026-11-07', '2026-11-10')),  -- Tent, Ada
    (7, 2, 2, daterange('2026-10-25', '2026-10-28'));  -- Ladder, Bruno

-- Explicit ids were given above, so move each identity sequence past them.
DO $$ BEGIN PERFORM setval(pg_get_serial_sequence('customers', 'customer_id'), (SELECT max(customer_id) FROM customers)); END $$;
DO $$ BEGIN PERFORM setval(pg_get_serial_sequence('items', 'item_id'), (SELECT max(item_id) FROM items)); END $$;
DO $$ BEGIN PERFORM setval(pg_get_serial_sequence('rentals', 'rental_id'), (SELECT max(rental_id) FROM rentals)); END $$;

ANALYZE customers;
ANALYZE items;
ANALYZE rentals;
