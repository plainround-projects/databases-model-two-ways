-- One customer's history, oldest first: rentals_customer (customer_id, lower(during)) gives the rows already in order.
EXPLAIN (ANALYZE, BUFFERS)
SELECT r.rental_id, i.name AS item, lower(r.during) AS first_day, upper(r.during) AS return_day
FROM rentals r
JOIN items i USING (item_id)
WHERE r.customer_id = 42
ORDER BY lower(r.during), r.rental_id;
