-- The daily report: every rental is read once, so a full scan is the right plan. Frequency is once a day.
EXPLAIN (ANALYZE, BUFFERS)
SELECT i.name AS item,
       to_char(lower(r.during), 'YYYY-MM') AS month,
       sum((upper(r.during) - lower(r.during)) * i.daily_rate) AS revenue
FROM rentals r
JOIN items i USING (item_id)
GROUP BY i.name, to_char(lower(r.during), 'YYYY-MM')
ORDER BY i.name, month;
