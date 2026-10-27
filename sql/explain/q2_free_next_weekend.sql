-- Which of the 1,000 items are free for a three-day window? One probe per item.
EXPLAIN (ANALYZE, BUFFERS)
SELECT i.item_id, i.name
FROM items i
WHERE NOT EXISTS (
    SELECT 1 FROM rentals r WHERE r.item_id = i.item_id AND r.during && daterange('2024-02-01', '2024-02-04')
)
ORDER BY i.item_id;
