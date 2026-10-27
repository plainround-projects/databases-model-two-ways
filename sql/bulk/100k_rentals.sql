-- Lesson step 6: 100,000 rentals so the plans mean something (make bulk).
-- 1,000 items get 100 rentals of 3 days each, 4 days apart, so none overlap. The dates run from 2024-01-01 to
-- early 2025, clear of the hand-checked rentals in 2026. Items 5 to 1000 and customers 3 to 500 are added first.
-- The rental ids start at 1,001 so they do not collide with the seed's rentals 1 to 7.
-- Run it through `make bulk`: that drops the exclusion constraint for the load and adds it back afterwards, which builds
-- its index once and re-checks every row. With the constraint in place each insert is checked through the GiST index
-- and 100,000 rows take minutes.
-- Note: items 1 to 4 now have rentals, so "never rented" no longer answers Kayak; `make db` restores the seed.

INSERT INTO customers (customer_id, name)
SELECT n, 'Customer ' || n FROM generate_series(3, 500) AS n
ON CONFLICT DO NOTHING;

INSERT INTO items (item_id, name, daily_rate)
SELECT n, 'Item ' || n, 5 + n % 20 FROM generate_series(5, 1000) AS n
ON CONFLICT DO NOTHING;

INSERT INTO rentals (rental_id, item_id, customer_id, during)
SELECT 1000 + n, 1 + n % 1000, 1 + n % 500,
       daterange(DATE '2024-01-01' + (n / 1000) * 4, DATE '2024-01-01' + (n / 1000) * 4 + 3)
FROM generate_series(1, 100000) AS n;

DO $$ BEGIN PERFORM setval(pg_get_serial_sequence('customers', 'customer_id'), (SELECT max(customer_id) FROM customers)); END $$;
DO $$ BEGIN PERFORM setval(pg_get_serial_sequence('items', 'item_id'), (SELECT max(item_id) FROM items)); END $$;
DO $$ BEGIN PERFORM setval(pg_get_serial_sequence('rentals', 'rental_id'), (SELECT max(rental_id) FROM rentals)); END $$;

-- Without fresh statistics the planner works from the seed's tiny numbers and the plans mislead.
ANALYZE customers;
ANALYZE items;
ANALYZE rentals;
