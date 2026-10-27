-- The five questions of lesson step 1, answered on the hand-checked data (make queries).
-- "Today" is 2026-11-04 and "next weekend" is 2026-11-07 up to, not including, 2026-11-09.

-- 1. Free next weekend: items with no rental that overlaps the weekend. Expected: Drill, Kayak.
SELECT i.item_id, i.name
FROM items i
WHERE NOT EXISTS (
    SELECT 1 FROM rentals r
    WHERE r.item_id = i.item_id AND r.during && daterange('2026-11-07', '2026-11-09')
)
ORDER BY i.item_id;

-- 1b. The same question for one item, the frequent form (200 a day): is the Ladder free next weekend? Expected: f.
SELECT NOT EXISTS (
    SELECT 1 FROM rentals r WHERE r.item_id = 2 AND r.during && daterange('2026-11-07', '2026-11-09')
) AS ladder_is_free;

-- 2. Ada's rental history, oldest first. Expected: rentals 1, 3, 6, 5 (by start date).
SELECT r.rental_id, i.name AS item, lower(r.during) AS first_day, upper(r.during) AS return_day
FROM rentals r
JOIN items i USING (item_id)
WHERE r.customer_id = (SELECT customer_id FROM customers WHERE name = 'Ada')
ORDER BY lower(r.during), r.rental_id;

-- 3. Returns today: rentals whose return day is 2026-11-04. Expected: rental 1 (Drill, Ada).
SELECT r.rental_id, i.name AS item, c.name AS customer
FROM rentals r
JOIN items i USING (item_id)
JOIN customers c USING (customer_id)
WHERE upper(r.during) = DATE '2026-11-04'
ORDER BY r.rental_id;

-- 4. Revenue per item and month, the month being the one the rental starts in.
--    upper - lower on a daterange is the number of days. Expected: Drill 2026-11 50, Drill 2026-12 20,
--    Ladder 2026-10 24, Ladder 2026-11 56, Tent 2026-10 45, Tent 2026-11 45.
SELECT i.name AS item,
       to_char(lower(r.during), 'YYYY-MM') AS month,
       sum((upper(r.during) - lower(r.during)) * i.daily_rate) AS revenue
FROM rentals r
JOIN items i USING (item_id)
GROUP BY i.name, to_char(lower(r.during), 'YYYY-MM')
ORDER BY i.name, month;

-- 5. Items never rented. Expected: Kayak.
SELECT i.item_id, i.name
FROM items i
WHERE NOT EXISTS (SELECT 1 FROM rentals r WHERE r.item_id = i.item_id)
ORDER BY i.item_id;
