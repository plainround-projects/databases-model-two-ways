-- Rentals coming back on one day: rentals_return_day (upper(during)).
EXPLAIN (ANALYZE, BUFFERS)
SELECT r.rental_id, i.name AS item, c.name AS customer
FROM rentals r
JOIN items i USING (item_id)
JOIN customers c USING (customer_id)
WHERE upper(r.during) = DATE '2024-03-12'
ORDER BY r.rental_id;
