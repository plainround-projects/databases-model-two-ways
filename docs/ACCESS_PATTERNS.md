# Access patterns (lesson step 1)

The five questions the shop asks, plus the one write that needs a rule. Frequencies are the lesson's planning numbers for a small shop; "must be current" separates the questions where a wrong answer costs money from the ones where yesterday's answer is fine.

| Pattern | Frequency | Must be current? | Query | Index it uses |
| --- | --- | --- | --- | --- |
| Is item X free next weekend? | 200 a day, on demand | Yes, exactly: a wrong "free" is a double booking | `NOT EXISTS (... item_id = X AND during && range)` ([003_queries.sql](../sql/003_queries.sql), 1b) | `rentals_item_id_during_excl`, the GiST index that comes with the constraint |
| Which items are free next weekend? | The same screen, for the whole catalog | Yes | `NOT EXISTS` per item ([003_queries.sql](../sql/003_queries.sql), 1) | `rentals_item_id_during_excl`, one probe per item |
| A customer's rental history | 100 a day | Yes | `WHERE customer_id = ? ORDER BY lower(during)` (2) | `rentals_customer (customer_id, lower(during))`, which also gives the order |
| Today's returns | 20 a day | Yes | `WHERE upper(during) = ?` (3) | `rentals_return_day (upper(during))` |
| Revenue per item and month | 1 a day, a report | No: an hour old is fine | `GROUP BY item, month` (4) | None, on purpose: it reads every rental once, so a full scan is the right plan |
| Items never rented | 1 a week | No | `NOT EXISTS (... item_id = i.item_id)` (5) | None: an anti join over all rentals |
| **Book an item** (the write) | 60 a day | Yes, and two requests may race for the same dates | `INSERT` ([postgres_rentals.py](../src/rental_shop/infrastructure/postgres_rentals.py)) | The exclusion constraint checks it through its GiST index |

Every pattern that must be exactly current uses an index. The two report queries do not, by design; their plans are in [sql/explain](../sql/explain/results.md).

Reading the table: the write rate (60 a day) is smaller than the read rate on availability (200 a day), which is why the availability probe is the one worth an index and why the write can afford the cost of a GiST check. Foreign keys index only the parent side, so `rentals.item_id` and `rentals.customer_id` get their coverage from the exclusion index and `rentals_customer`; without them a delete of an item or customer would scan `rentals`.
