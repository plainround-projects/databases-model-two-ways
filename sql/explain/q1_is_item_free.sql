-- The frequent availability check (200 a day): is item 777 free from 2024-02-01 to 2024-02-04?
-- Before the step-4 constraint nothing indexes (item_id, during); after it the constraint's GiST index answers this.
EXPLAIN (ANALYZE, BUFFERS)
SELECT NOT EXISTS (
    SELECT 1 FROM rentals WHERE item_id = 777 AND during && daterange('2024-02-01', '2024-02-04')
) AS item_is_free;
