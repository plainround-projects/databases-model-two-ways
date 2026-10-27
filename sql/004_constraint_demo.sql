-- What the constraint does (lesson step 4), as psql shows it. Each case runs in its own transaction and is
-- rolled back, so the hand-checked data stays as it was. ON_ERROR_STOP is off so the refusal is printed
-- and the script goes on (make demo).
\set ON_ERROR_STOP off

\echo '-- overlap: Drill from 11-03 to 11-05 collides with rental 1 (11-01 to 11-04); expect SQLSTATE 23P01'
BEGIN;
INSERT INTO rentals (rental_id, item_id, customer_id, during) VALUES (8, 1, 2, daterange('2026-11-03', '2026-11-05'));
ROLLBACK;

\echo '-- touching: Drill from 11-06 starts the day rental 2 ends; expect INSERT 0 1'
BEGIN;
INSERT INTO rentals (rental_id, item_id, customer_id, during) VALUES (9, 1, 2, daterange('2026-11-06', '2026-11-08'));
ROLLBACK;

\echo '-- closed range: [] counts the return day as a rental day, so a rental that only touches is refused'
BEGIN;
INSERT INTO rentals (rental_id, item_id, customer_id, during) VALUES (10, 4, 1, '[2026-11-01,2026-11-04]');
SELECT during AS stored_as FROM rentals WHERE rental_id = 10;
INSERT INTO rentals (rental_id, item_id, customer_id, during) VALUES (11, 4, 2, daterange('2026-11-04', '2026-11-06'));
ROLLBACK;

\echo '-- an empty range is refused by the check'
BEGIN;
INSERT INTO rentals (rental_id, item_id, customer_id, during) VALUES (12, 4, 1, 'empty');
ROLLBACK;
