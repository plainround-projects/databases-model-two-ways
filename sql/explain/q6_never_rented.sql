-- Items with no rentals, once a week. An anti join over all rentals.
EXPLAIN (ANALYZE, BUFFERS)
SELECT i.item_id, i.name
FROM items i
WHERE NOT EXISTS (SELECT 1 FROM rentals r WHERE r.item_id = i.item_id)
ORDER BY i.item_id;
