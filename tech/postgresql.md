# PostgreSQL 18

## What it is

PostgreSQL ("Postgres") is a **relational database server**: a program that stores tables on disk, accepts connections over the network, and answers SQL. It guarantees that a group of changes (a **transaction**) either happens completely or not at all, that committed data survives a crash, and that concurrent users do not corrupt each other's work. This repository runs version 18 from the official image `postgres:18`; the captured plans were made on 18.6.

## Why this repository uses it

The lesson's central rule, "no item is rented twice for overlapping dates", is enforced by PostgreSQL itself with an **exclusion constraint** that is backed by a **GiST index**. The same server also stores the document version of the data (as JSONB) to show that the rule is impossible to state there.

## Where it appears

| File | What it does with PostgreSQL |
|---|---|
| `docker-compose.yml` | Starts the server with `deadlock_timeout=100ms`. See [docker-compose.md](docker-compose.md). |
| `sql/*.sql` | Everything run against it. See [sql.md](sql.md). |
| `sql/migrations/001_exclusion_constraint.sql` | The extension and the exclusion constraint. |
| `sql/explain/` | Plans from `EXPLAIN (ANALYZE, BUFFERS)` and `results.md`. |
| `src/rental_shop/infrastructure/` | The Python adapter. See [psycopg.md](psycopg.md). |
| `.env.example` | Host, port, database, user, password, schema, timeouts. See [dotenv.md](dotenv.md). |

## How it works underneath

The server is one main process (the **postmaster**) that starts a separate **backend process** for every client connection. Data lives in files on disk, divided into 8-kilobyte **pages**; recently used pages are kept in a shared memory cache (**shared buffers**). Every change is first written to the **write-ahead log** (WAL), so after a crash the server replays the log.

PostgreSQL uses **MVCC** (multi-version concurrency control). An update does not overwrite a row; it writes a new version and keeps the old one for transactions that started earlier. Readers never block writers. Old versions are cleaned up later by **vacuum**.

An **index** is a separate structure that maps values to row locations so a query can find rows without reading the whole table. The most common kind is a B-tree, good for equality and order. A **GiST** (Generalized Search Tree) index handles other questions, such as "which ranges overlap this range". A **constraint** is a rule the server checks on every change; an **exclusion constraint** generalises uniqueness: it says that no two rows may satisfy the listed operators against each other at the same time (here `=` on the item and `&&` on the dates). The server enforces it by looking into the GiST index for a conflicting row as part of every insert.

Two transactions that insert overlapping rows at nearly the same instant cannot both see "no conflict yet", because each can see the other's uncommitted row in the index and must wait for it to finish. If each waits for the other, that is a **deadlock**; after `deadlock_timeout` the server checks for one and aborts one transaction with SQLSTATE `40P01`. A refused insert is SQLSTATE `23P01`.

The **planner** decides how to run a query: which indexes to use, in what order to join tables. It estimates costs from **statistics** that `ANALYZE` collects. `EXPLAIN` shows the plan, and `EXPLAIN (ANALYZE, BUFFERS)` runs it and adds real times and page counts.

## Walkthrough of this repository's use

### The constraint

```sql
CREATE EXTENSION IF NOT EXISTS btree_gist;
```

```sql
ALTER TABLE rentals
    ADD CONSTRAINT rentals_item_id_during_excl EXCLUDE USING gist (item_id WITH =, during WITH &&);
```

The extension line and the constraint are explained in [sql.md](sql.md). In server terms: creating the constraint builds a GiST index named like the constraint, `rentals_item_id_during_excl`, over `(item_id, during)`. For every `INSERT` or `UPDATE` of `rentals` the server probes that index for a row with the same item whose range overlaps; a hit raises `23P01`. The same index also answers the query "is this item free for these dates", which is why the lesson's plan after the constraint is an **index-only scan** (the answer is read from the index without touching the table).

### The server setting

```yaml
    command: ["postgres", "-c", "deadlock_timeout=100ms"]
```

`postgres -c deadlock_timeout=100ms` starts the server with one configuration parameter changed from its default of one second, so the 20-way races find and resolve deadlocks quickly.

### What the captured plans show

`sql/explain/results.md` lists the real plans captured on 100,007 rentals. Read the shapes, not the milliseconds:

- Before the constraint, "is item 777 free" is a **sequential scan** (reading the table from the start) that stops at the first match: 8,782 rows scanned, 66 buffers read.
- After the constraint, the same query is an **index-only scan** on `rentals_item_id_during_excl`, 52 buffers, `Heap Fetches: 0`.
- The monthly revenue report reads every rental once, so a sequential scan is correct; its sort spills to disk (`Sort Method: external merge`) because `work_mem` is 4 MB.
- The never-rented query makes 1,000 index probes, an **anti join** (return rows with no match).

The commands that produce these files are in `scripts/capture_explain.sh`; see [bash.md](bash.md).

## Try it yourself

```bash
make up && make db
docker compose exec -T postgres psql -U shop -d rentals -c '\d rentals'
```
Shows the table with its check constraint, the three indexes (`rentals_pkey`, `rentals_customer`, `rentals_return_day`, `rentals_item_id_during_excl` of type `gist`), and the foreign keys.

```bash
docker compose exec -T postgres psql -U shop -d rentals -c "EXPLAIN SELECT 1 FROM rentals WHERE item_id = 1 AND during && daterange('2026-11-07','2026-11-09')"
```
Expect an `Index Scan` or `Index Only Scan` using `rentals_item_id_during_excl`.

```bash
docker compose exec -T postgres psql -U shop -d rentals -c "SELECT conname, contype FROM pg_constraint WHERE conrelid = 'rentals'::regclass ORDER BY 1"
```
The `x` in `contype` marks the exclusion constraint.

```bash
make demo
```
Watch the server refuse the overlap with SQLSTATE `23P01`.

## Mistakes people make

- **Checking in the application first.** Two sessions can both pass the check; the constraint cannot be raced.
- **Forgetting that foreign keys do not index the child column.** The schema adds the indexes the queries need.
- **Bulk-loading with the constraint in place.** Every row is checked through the index; the lab drops it for the load and re-adds it.
- **Reading plan times on a busy machine.** Compare buffer counts and plan shapes.
- **Running `ANALYZE` never.** The planner works from stale numbers.

## Check yourself

1. What does an exclusion constraint generalise? *Uniqueness, with operators other than equality.*
2. Why is `btree_gist` needed? *GiST cannot index plain integers without it, and the constraint mixes `=` on an integer with `&&` on a range.*
3. What is MVCC? *Updates write new row versions so readers do not block writers.*
4. What SQLSTATE does a double booking raise, and a deadlock victim? *`23P01` and `40P01`.*
5. What does `EXPLAIN (ANALYZE, BUFFERS)` add to `EXPLAIN`? *Real execution, real times and page counts.*

## Further reading

- PostgreSQL 18 documentation: https://www.postgresql.org/docs/18/
- Exclusion constraints: https://www.postgresql.org/docs/18/ddl-constraints.html#DDL-CONSTRAINTS-EXCLUSION
- GiST: https://www.postgresql.org/docs/18/gist.html
- Using EXPLAIN: https://www.postgresql.org/docs/18/using-explain.html
- Deadlocks: https://www.postgresql.org/docs/18/explicit-locking.html#LOCKING-DEADLOCKS
