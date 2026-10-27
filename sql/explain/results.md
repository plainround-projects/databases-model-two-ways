# Plans on 100,000 rentals

Captured by `make explain` (`scripts/capture_explain.sh`) on PostgreSQL 18.6 after `ANALYZE`: 1,000 items, 500 customers, 100,007 rentals. The milliseconds are larger than a quiet machine's, because the laptop was busy with many other containers while the plans were captured; read the shapes of the plans and the buffer counts, not the times.

| Query | File | Plan | Index | What to notice |
| --- | --- | --- | --- | --- |
| Is item 777 free from 2024-02-01 to 2024-02-04? (before the constraint) | [q1_is_item_free_before.txt](q1_is_item_free_before.txt) | Seq Scan inside an `EXISTS`, `Rows Removed by Filter: 8782`, 66 buffers | none | The scan stops at the first match, so it read 8,782 of the 100,007 rows before finding item 777's rental. For an item that is free it must read them all. |
| The same, after the constraint | [q1_is_item_free_after.txt](q1_is_item_free_after.txt) | Index Only Scan, `Heap Fetches: 0`, 52 buffers | `rentals_item_id_during_excl` | The constraint's GiST index answers the question. The lesson's expected output says `Index Scan`; for a query that only needs to know whether a row exists the planner does not visit the table at all. |
| Which items are free for a three-day window? | [q2_free_next_weekend.txt](q2_free_next_weekend.txt) | Hash Right Anti Join of the items with one Index Only Scan on the date range | `rentals_item_id_during_excl` | One pass over the index for the whole catalog, not a probe per item. Every item has a rental in the window in this data, so the answer is no rows. |
| One customer's history, oldest first | [q3_customer_history.txt](q3_customer_history.txt) | Bitmap Index Scan, Bitmap Heap Scan, Hash Join with the items, Sort on the start date | `rentals_customer` | 200 rows for customer 42. The bitmap path was chosen over a plain index scan because 200 rows spread over 100,007 would hit 200 different pages; the sort on `lower(during)` still happens, so the index on `(customer_id, lower(during))` serves the filter and not the order here. |
| Rentals coming back on one day | [q4_returns_today.txt](q4_returns_today.txt) | Index Scan, then two hash joins | `rentals_return_day` | The bulk data has all 1,000 items returning on the same days, so this day has 1,000 rows. |
| Revenue per item and month | [q5_revenue_per_item_and_month.txt](q5_revenue_per_item_and_month.txt) | Seq Scan on rentals, Hash Join, Sort, GroupAggregate; `Sort Method: external merge  Disk: 4504kB` | none | Every rental is read once, so a scan is right. The sort goes to disk because the group key is an expression and `work_mem` is 4 MB: the plan that would change first if the report ran more often. |
| Items never rented | [q6_never_rented.txt](q6_never_rented.txt) | Nested Loop Anti Join: 1,000 Index Only Scans | `rentals_item_id_during_excl` | 1,000 probes (3,052 buffers) instead of one pass; the planner estimated 100 rows per probe and chose probes over a hash anti join. |

## The plan that surprised

The availability check is an Index Only Scan, not the `Index Scan` the lesson's expected output shows, with no table access at all. And before the constraint exists, the `EXISTS` check is a sequential scan that stops early, which makes it look cheap for an item that was rented early and hides how bad it is for one that is free.
