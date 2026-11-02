# databases-model-two-ways

The data layer of a small equipment-rental shop, designed twice (as tables and as documents) and built in PostgreSQL, where an exclusion constraint makes it impossible to rent one item twice for overlapping dates, however many connections race for it.

| | |
| --- | --- |
| **Lesson** | `/prep/databases/project-model-two-ways`, "The rental shop, modeled two ways" (`data-structure-explainer/src/content/tracks/databases/12-project-model-two-ways.md` in the Plainround app) |
| **Planned hours** | 6 |
| **Level** | Beginner |
| **Architecture** | [ARCHITECTURE.md](ARCHITECTURE.md), decisions: [docs/adr](docs/adr), access patterns: [docs/ACCESS_PATTERNS.md](docs/ACCESS_PATTERNS.md), the document design: [docs/DOCUMENT_MODEL.md](docs/DOCUMENT_MODEL.md) |

## Prerequisites

| Tool | Version | Used for |
| --- | --- | --- |
| Docker with Compose v2 | 24 or newer (tested with 24.0.6) | PostgreSQL |
| Python | 3.12 or 3.13 (tested with 3.13; the CI uses 3.12) | the programs and tests |
| GNU Make | 3.81 or newer | every command below |
| PostgreSQL image | `postgres:18` | pulled on first `make up` |
| Python packages | `psycopg[binary]` 3.2 or newer at run time (3.3.6 locked); pytest, pytest-cov, ruff, mypy, import-linter, pip-audit for development. All pinned with hashes in `requirements.lock` and `requirements-dev.lock`; `make` installs them into `.venv/` | everything |

No cloud account. The database password is read from the environment, never from code: `make up` copies `.env.example` to `.env` the first time (a throwaway value for a database that lives only on this machine while the container runs). Port 5441 must be free (set `POSTGRES_PORT` in `.env` to change it).

## Setup, run, test, stop

```bash
make up                  # PostgreSQL 18, waits until it accepts connections; creates .venv
make db                  # sql/reset.sql, 001_schema.sql, 002_seed.sql, migrations/001_exclusion_constraint.sql
make queries             # sql/003_queries.sql: the five questions on the hand-checked data
make demo                # sql/004_constraint_demo.sql: an overlap is refused, a touching range is accepted
make demo-documents      # the same double booking in the document design (JSONB): both are accepted
make report              # the five questions through the application code
make book ITEM=1 CUSTOMER=2 FROM=2026-11-03 DAYS=2     # one booking; exit code 3 when the dates are taken
make race                # 20 connections race for one item, 20 times; exactly one wins each time
make race-plain          # the same race with a plain INSERT (SQLSTATE 23P01); deadlock victims are retried and counted
make bulk                # 100,000 rentals (step 6); `make db` restores the hand-checked data
make explain             # EXPLAIN (ANALYZE, BUFFERS) of every query on 100,000 rentals -> sql/explain/*.txt
make run                 # db, queries, demo, demo-documents, db again, report, race
make health              # exit 0 when PostgreSQL has the tables and the exclusion constraint
make lint                # ruff check and format check, mypy (strict), import-linter
make test                # unit tests with coverage (no PostgreSQL needed; domain and application at 95% or more)
make test-integration    # the repository and the schema against PostgreSQL (needs make up)
make test-e2e            # the lesson's scenario through the command-line programs (needs make up)
make audit               # known-vulnerability check of the locked dependencies
make down                # stops PostgreSQL and deletes its data
```

`make help` lists every target. Operational log lines (structured `logfmt`) go to standard error; results go to standard output. Integration and end-to-end tests build their own schema inside the database and drop it afterwards, so they never touch the data `make db` loaded.

## The SQL

Every statement the project runs against PostgreSQL is a file under [sql/](sql/), run in this order:

| File | Kind | What it holds | Run by |
| --- | --- | --- | --- |
| [reset.sql](sql/reset.sql) | DDL (outside the run order) | drops the tables so `make db` can rebuild | `make db` |
| [001_schema.sql](sql/001_schema.sql) | DDL | `customers`, `items`, `rentals` with `daterange`, keys, foreign keys, checks and the two lookup indexes (lesson step 2) | `make db` |
| [002_seed.sql](sql/002_seed.sql) | DML | the lesson's hand-checkable data: 2 customers, 4 items, 7 rentals | `make db` |
| [migrations/001_exclusion_constraint.sql](sql/migrations/001_exclusion_constraint.sql) | DDL (lesson step 4's change) | `btree_gist` and `EXCLUDE USING gist (item_id WITH =, during WITH &&)` | `make db`, `make bulk` |
| [003_queries.sql](sql/003_queries.sql) | queries | the five questions, each with its expected answer in a comment | `make queries` |
| [004_constraint_demo.sql](sql/004_constraint_demo.sql) | DML demo | an overlap (refused, SQLSTATE 23P01), a touching range (accepted), a closed range that clashes, an empty range (refused by the check); every case is rolled back | `make demo` |
| [bulk/100k_rentals.sql](sql/bulk/100k_rentals.sql) | DML | 100,000 rentals, 1,000 items, 500 customers, then `ANALYZE` | `make bulk` |
| [explain/](sql/explain) | `EXPLAIN (ANALYZE, BUFFERS)` | each query as `.sql` and its captured plan as `.txt`; the availability query before and after the constraint; [results.md](sql/explain/results.md) | `make explain` |
| [document_model/](sql/document_model) | DDL and DML | the document design as JSONB, and the double booking it accepts | `make demo-documents` |

The constraint is a migration on purpose: the lesson adds it in step 4 after designing the tables in step 2, and the availability query's plan can be captured before and after it.

## Done when: the lesson's checklist and the proof for each line

| # | Done when (from the lesson) | Command | What proves it |
| --- | --- | --- | --- |
| 1 | Each access pattern has its expected frequency and whether it must be exactly up to date. | read [docs/ACCESS_PATTERNS.md](docs/ACCESS_PATTERNS.md) | One table: the five questions plus the write, each with a frequency, a freshness need, the query and the index it uses. |
| 2 | Every access pattern maps to a query that uses an index you listed. | `make explain`, then read [sql/explain/results.md](sql/explain/results.md) | The three patterns that must be current use `rentals_item_id_during_excl`, `rentals_customer` and `rentals_return_day`, in the captured plans. The two report queries (revenue, never rented) read every rental on purpose and say so. |
| 3 | You can name the access pattern that is awkward in the document design and the one that is easier. | read [docs/DOCUMENT_MODEL.md](docs/DOCUMENT_MODEL.md); `make demo-documents` | Easier: a customer's history (one document). Awkward: the availability check, and keeping the two copies of a rental in step. The demo books the drill twice and both bookings are accepted; the query after it finds the overlap. |
| 4 | Inserting an overlapping rental for the same item fails with a constraint violation, and touching ranges are allowed. | `make demo` | `ERROR:  conflicting key value violates exclusion constraint "rentals_item_id_during_excl"` with the `DETAIL:` line naming both ranges, then `INSERT 0 1` for the rental that starts the day another ends. The integration test checks SQLSTATE `23P01`. |
| 5 | Exactly one rental succeeds every time over 20 runs, with no application-level locking. | `make race` | Twenty lines `run N: 1 success, 19 refused by the exclusion constraint` and `20 of 20 runs had exactly one winner`; exit code 0. 20 threads, each on its own connection, released together by a barrier; a new item each run; no lock anywhere in the application. `make race-plain` does it with a plain `INSERT`; see "A finding about the race" below. |
| 6 | Each query returns the right answer on the small hand-checked set, and the README notes which plan surprised you. | `make report`, `make queries`, `make explain` | The report prints the lesson's expected output line for line (see below). The plan notes are in the next section. |

The report on the hand-checked data (`make report`, also asserted by the end-to-end test):

```text
free next weekend: Drill, Kayak
Ada's history: 1, 3, 5 and 6
returns on 2026-11-04: rental 1 (Drill, Ada)
revenue per item and month: Drill 2026-11 50.00 | Drill 2026-12 20.00 | Ladder 2026-10 24.00 | Ladder 2026-11 56.00 | Tent 2026-10 45.00 | Tent 2026-11 45.00
never rented: Kayak
```

The review checklist of the lesson, line by line: the frequencies and freshness needs are in ACCESS_PATTERNS.md; the indexes are named there and the plans are in `sql/explain`; the document trade-off is in DOCUMENT_MODEL.md; the constraint and the touching case are `make demo`; the race is `make race`; the five answers are `make report`; the plans were captured after `ANALYZE` on 100,000 rentals; and the application catches `23P01` (or its `ON CONFLICT` equivalent) and says "already booked" (`make book`, exit code 3).

### A finding about the race

The lesson's race script inserts from 20 connections at once and expects one success and nineteen exclusion violations. Run exactly that against PostgreSQL 18 (`make race-plain`) and the safety property holds in every run (one winner), but about one round in five also contains deadlocks (SQLSTATE `40P01`): each contender inserts its row, then checks the constraint, finds the other contenders' uncommitted rows and waits for them, while they wait for it. PostgreSQL ends one of them after `deadlock_timeout`. In the worst rounds the same contenders lost again on every retry. The default insert therefore uses `INSERT ... ON CONFLICT ON CONSTRAINT rentals_item_id_during_excl DO NOTHING`: a clash returns no row, and PostgreSQL then lets an inserter wait only for an older transaction, so waits cannot form a cycle. The constraint is still the only rule. [ADR 0002](docs/adr/0002-two-insert-modes-for-booking.md) has the details; the compose file sets `deadlock_timeout=100ms` so the plain mode's deadlocks resolve quickly.

### Plans that surprised

Captured on 100,000 rentals after `ANALYZE` ([results.md](sql/explain/results.md)):

- **The availability check is an Index Only Scan, not an Index Scan**, on the constraint's GiST index, with `Heap Fetches: 0`. The lesson's expected output shows `Index Scan`; for a query that only asks `NOT EXISTS` the planner does not need the table.
- **Before the constraint the same check is a sequential scan that stops at the first match** (`Rows Removed by Filter: 8782` of 100,007 rows, not all of them), because `EXISTS` ends at one row. The scan is cheap for an item that was rented early and expensive for one that is free, which is the case that matters.
- **"Free next weekend" for every item is one pass over the index, not a probe per item**: a Hash Anti Join between the items and one index scan on the date range.
- **The revenue report sorts 100,000 rows on disk** (`Sort Method: external merge`) because the group key is an expression and `work_mem` is 4 MB. At one report a day that is acceptable, and it is the plan that would change first if the report ran more often.
- **"Never rented" is 1,000 index probes in a Nested Loop Anti Join**, not a scan of `rentals`.

## Stretch goals

| Stretch (from the lesson) | Built? |
| --- | --- |
| Build the document version in a document store and compare the code for the availability check. | Partly. The document design is runnable as JSONB in PostgreSQL ([sql/document_model](sql/document_model)) to show what it cannot enforce; no document database is used. ARCHITECTURE.md, "How to extend it", describes the port to implement. |
| Add a soft delete for canceled rentals and keep the exclusion constraint correct. | No. The approach (`canceled_at` and `WHERE (canceled_at IS NULL)` on the constraint) is in ARCHITECTURE.md. |
| Add row-level security so a customer's session can only read their own rentals. | No. The approach is in ARCHITECTURE.md. |

## What is simplified for teaching

Only what the lesson scopes out, plus where this build differs from the lesson's text:

- One PostgreSQL container, a throwaway password, plain-text connection; no pooling, no replica.
- The lesson's `rentals` table has an explicit integer `rental_id`; this one generates it (`GENERATED BY DEFAULT AS IDENTITY`) and lets the seed and the bulk load give explicit ids, so the race and the report can add rows. The bulk load's ids start at 1,001 so they do not collide with the seed's.
- The exclusion constraint is added by a migration rather than inside `CREATE TABLE`, so the plan of the availability query can be captured before and after it.
- The bulk load drops the constraint, loads, and adds it back (`make bulk`): with the constraint in place 100,000 inserts take minutes because every row is checked through the GiST index.
- The `CHECK` on the range's bounds states the half-open rule but cannot fail for a `daterange`: PostgreSQL stores every input as `[)` (a closed `'[a,b]'` becomes `[a,b+1)`). The check that does the work is `NOT isempty`. `make demo` shows what a closed range does to a touching rental.
- The compose file sets `deadlock_timeout=100ms` (default one second) so the plain-insert race finishes quickly.
- The plan timings in `sql/explain` were captured on a laptop that was busy with other work, so the milliseconds are larger than a quiet machine's and the shapes of the plans are what to read.

## Project structure

```text
src/rental_shop/
  domain/            RentalPeriod (half-open dates, overlap), Customer, Item, Rental, report rows, the race tally,
                     named errors. Depends on nothing outside the standard library.
  application/       use cases (book an item, the shop's five questions, the race, health) and the ports they need
                     (RentalBooking, RentalQueries, GatewayOpener, Clock, HealthProbe). Depends on domain only.
  infrastructure/    adapters: the psycopg repository with its two insert modes, connection with timeouts and
                     retry, settings (environment, validated), logfmt logging, retry with backoff, signals, clock.
                     Depends on application and domain.
  interfaces/        command-line programs: book, race, report, health. Wire adapters into use cases and own
                     exit codes. Nothing depends on it.
sql/                 reset, 001_schema, 002_seed, 003_queries, 004_constraint_demo, migrations/, bulk/, explain/,
                     document_model/.
tests/
  unit/              domain, application (with an in-memory shop), settings, logging, retry, CLI formats. No services.
  integration/       the repository, the schema's rules, the race and the health probe against PostgreSQL.
  e2e/               the lesson's scenario through the command-line programs.
docs/                ACCESS_PATTERNS.md, DOCUMENT_MODEL.md, adr/ (the database decides; two insert modes).
tech/                one note per technology the repository uses, from zero, with every file quoted and explained (start with tech/README.md).
scripts/             capture_explain.sh (the plans in sql/explain).
docker-compose.yml   PostgreSQL 18.      Dockerfile  the programs as an image (non-root, health command as its check).
pyproject.toml       project metadata and every tool's configuration (ruff, mypy, pytest, import-linter).
requirements*.lock   hash-pinned dependencies (runtime, and runtime plus development tools).
Makefile             the only commands a reader needs (make help).
```

The dependency rule (domain depends on nothing; application on domain; infrastructure and interfaces on both; nothing on interfaces) is enforced by `make lint` through import-linter. A second contract forbids `domain` and `application` from importing `psycopg`.

## Author and license

Written by Sumit Srivastava. Released under the MIT License, see [LICENSE](LICENSE). Changes are in [CHANGELOG.md](CHANGELOG.md).
