# psycopg 3

## What it is

psycopg is the Python **driver** for PostgreSQL: a library that opens a network connection to the database server, sends SQL text, and turns the server's answers into Python values. This repository uses version 3 (`psycopg[binary]>=3.2,<4`). The `[binary]` part is an **extra**: it installs a prebuilt copy of `libpq`, PostgreSQL's own client library written in C, so nothing has to be compiled.

## Why this repository uses it

The domain and application layers know nothing about databases. One adapter layer turns the shop's questions into SQL and the database's refusals into the shop's named errors. psycopg is the only place where a connection exists, and the import contract in `pyproject.toml` forbids anything below the adapter from importing it (see [import-linter.md](import-linter.md)).

## Where it appears

| File | Role |
|---|---|
| `src/rental_shop/infrastructure/postgres.py` | Opens connections with timeouts, retries and a `session` that always closes. |
| `src/rental_shop/infrastructure/postgres_rentals.py` | `PostgresRentals`: every reads-and-writes query of the shop. |
| `src/rental_shop/infrastructure/health_probes.py` | Asks the server whether the tables and the constraint exist. |
| `tests/integration/test_postgres_rentals.py` | Tests the adapter against a real database (see [pytest.md](pytest.md)). |

## How it works underneath

A **connection** is a long-lived network link (a TCP socket, to host and port) between the program and one PostgreSQL server process. The first messages authenticate the user and database. After that the program sends **queries** and reads **rows**. A **cursor** is the object that holds the result of a query. A **transaction** groups statements so they all take effect or none does.

By default a driver starts a transaction implicitly and nothing is permanent until `commit()`. With **autocommit** on, each statement is its own transaction, and a block `with connection.transaction():` makes an explicit one. This repository uses autocommit plus explicit blocks so every transaction boundary is visible in the code.

**Parameters** are the values you pass separately from the SQL text: the SQL has `%s` placeholders and the values go in a tuple. psycopg 3 sends them to the server apart from the text, so they can never be mistaken for SQL (this is how **SQL injection**, an attack where data is run as code, is prevented). Python values are adapted automatically: `int` to `integer`, `Decimal` to `numeric`, `date` to `date`, and `psycopg.types.range.Range` to a range type.

When a statement fails, the server sends an error with a five-character **SQLSTATE** code. psycopg maps each to a Python exception class under `psycopg.errors`; for example `23P01` is `ExclusionViolation`, `40P01` is `DeadlockDetected` and `23503` is `ForeignKeyViolation`.

## Walkthrough of this repository's use

### `postgres.py`: connecting

```python
"""Adapter: connections to PostgreSQL, with a connect timeout, a statement timeout and retries with backoff."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import psycopg

from .logging import fields
from .retry import retry
from .settings import PostgresSettings

logger = logging.getLogger(__name__)

```

The imports: `contextmanager` turns a generator function into a context manager (below); `Iterator` types a generator; `Any` marks a type that does not matter; `fields` and `retry` come from the other support modules (see [python-logging.md](python-logging.md) and [python-stdlib.md](python-stdlib.md)); `logger` is this module's logger.

```python
def connect(settings: PostgresSettings, attempts: int = 5) -> psycopg.Connection[Any]:
    """Open a connection in autocommit mode, so `with connection.transaction()` is the only boundary.

    The session's search path is the configured schema (then `public`, where extensions live) and every statement
    is bounded by the statement timeout.
    """

    def open_connection() -> psycopg.Connection[Any]:
        return psycopg.connect(
            host=settings.host,
            port=settings.port,
            dbname=settings.database,
            user=settings.user,
            password=settings.password,
            connect_timeout=settings.connect_timeout_seconds,
            options=f"-c search_path={settings.schema},public -c statement_timeout={settings.statement_timeout_ms}",
            autocommit=True,
        )
```

`connect` has an inner function `open_connection` (a closure over `settings`) so the whole opening can be retried. `psycopg.connect(...)` takes keyword arguments:

- `host`, `port`, `dbname`, `user`, `password`: where to connect and as whom.
- `connect_timeout`: the seconds to wait before giving up on opening the connection.
- `options`: a string of command-line options sent to the server at start. `-c search_path=<schema>,public` sets the **search path**, the ordered list of schemas the server searches for an unqualified table name; `public` stays second because the `btree_gist` extension lives there. `-c statement_timeout=<ms>` makes the server cancel any statement that runs longer.
- `autocommit=True`: see above.

The return annotation `psycopg.Connection[Any]` says the connection yields rows of any shape (tuples here).

```python
    return retry(
        open_connection,
        attempts=attempts,
        base_delay_seconds=0.5,
        retry_on=(psycopg.OperationalError,),
        on_retry=lambda attempt, error: logger.warning(
            "retrying database connection", extra=fields(attempt=attempt, error=error)
        ),
    )
```

The function returns the result of `retry(...)` (see [python-stdlib.md](python-stdlib.md)): up to `attempts` (five) tries, starting with a 0.5 second pause, only when the error is `psycopg.OperationalError` (the database is not reachable yet). `on_retry` is a `lambda`, an unnamed one-expression function, that logs a warning with the attempt and the error.

```python
@contextmanager
def session(settings: PostgresSettings) -> Iterator[psycopg.Connection[Any]]:
    """A connection that is always closed, also when the block raises."""
    connection = connect(settings)
    try:
        yield connection
    finally:
        connection.close()
```

`@contextmanager` lets `session` be used in `with session(settings) as connection:`. Everything before `yield` is the set-up (open the connection); `yield connection` hands it to the `with` body; `finally` closes it whether the block ended normally or with an error.

### `postgres_rentals.py`: the SQL

```python
"""Adapter: the rental shop's reads and writes as plain SQL on PostgreSQL. Implements `RentalGateway`."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Any

import psycopg
from psycopg import errors
from psycopg.types.range import Range

from ..application.ports import GatewayOpener, RentalGateway
from ..domain.errors import BookingDeadlockError, ItemAlreadyBookedError, UnknownCustomerError, UnknownItemError
from ..domain.model import Customer, Item, MonthlyRevenue, Rental, ReturnDue
from ..domain.period import RentalPeriod
from .postgres import session
from .settings import PostgresSettings
```

The imports. `Enum` is for the insert mode, `psycopg.errors` gives the exception classes, and `Range` is psycopg's range type. The adapter imports from the application and domain layers (allowed: infrastructure may depend downward).

```python
INSERT_RENTAL = """
    INSERT INTO rentals (item_id, customer_id, during) VALUES (%s, %s, %s) RETURNING rental_id
"""
# Same insert, but a clash with the exclusion constraint returns no row instead of raising SQLSTATE 23P01.
INSERT_RENTAL_SKIPPING_CLASH = """
    INSERT INTO rentals (item_id, customer_id, during) VALUES (%s, %s, %s)
    ON CONFLICT ON CONSTRAINT rentals_item_id_during_excl DO NOTHING RETURNING rental_id
"""
IS_FREE = "SELECT NOT EXISTS (SELECT 1 FROM rentals WHERE item_id = %s AND during && %s)"
FREE_ITEMS = """
    SELECT i.item_id, i.name, i.daily_rate FROM items i
    WHERE NOT EXISTS (SELECT 1 FROM rentals r WHERE r.item_id = i.item_id AND r.during && %s)
    ORDER BY i.item_id
"""
```

The SQL strings are module constants, written with triple quotes (a string that may span lines). `%s` marks a parameter. `INSERT ... VALUES (%s, %s, %s) RETURNING rental_id` inserts one row and gives back the id the server generated. The second form, `ON CONFLICT ON CONSTRAINT rentals_item_id_during_excl DO NOTHING RETURNING rental_id`, means: if the new row would violate that exclusion constraint, skip it and return no row instead of raising an error. `IS_FREE` and `FREE_ITEMS` are lesson queries 1b and 1 (see [sql.md](sql.md)).

```python
HISTORY = """
    SELECT rental_id, item_id, customer_id, lower(during), upper(during) FROM rentals
    WHERE customer_id = %s ORDER BY lower(during), rental_id
"""
RETURNS_ON = """
    SELECT r.rental_id, i.name, c.name FROM rentals r
    JOIN items i USING (item_id) JOIN customers c USING (customer_id)
    WHERE upper(r.during) = %s ORDER BY r.rental_id
"""
REVENUE = """
    SELECT i.name, min(lower(r.during)), sum((upper(r.during) - lower(r.during)) * i.daily_rate)
    FROM rentals r JOIN items i USING (item_id)
    GROUP BY i.name, to_char(lower(r.during), 'YYYY-MM')
    ORDER BY i.name, to_char(lower(r.during), 'YYYY-MM')
"""
NEVER_RENTED = """
    SELECT i.item_id, i.name, i.daily_rate FROM items i
    WHERE NOT EXISTS (SELECT 1 FROM rentals r WHERE r.item_id = i.item_id) ORDER BY i.item_id
"""
```

`HISTORY`, `RETURNS_ON`, `REVENUE` and `NEVER_RENTED` are queries 2 to 5 of `sql/003_queries.sql`. The revenue query selects `min(lower(r.during))` instead of the month text so the adapter can build the month label in Python (`MonthlyRevenue.of`); the `GROUP BY` and `ORDER BY` are the same `to_char` expression as in the pure-SQL version.

```python
class InsertMode(Enum):
    """How a booking insert meets the exclusion constraint.

    RAISE is the plain INSERT: a clash raises SQLSTATE 23P01. Contenders that insert overlapping rows at the same
    moment wait for each other's uncommitted rows and can deadlock (40P01); PostgreSQL ends one of them.
    SKIP uses `ON CONFLICT DO NOTHING`: a clash returns no row. PostgreSQL then lets an inserter wait only for an
    older transaction, so contenders cannot deadlock on each other. The constraint decides in both modes.
    """

    RAISE = "raise"
    SKIP = "skip"


def _range(period: RentalPeriod) -> Range[date]:
    return Range(period.first_day, period.return_day, "[)")
```

`InsertMode` is an `Enum`: a class whose members are fixed named constants. `RAISE = "raise"` and `SKIP = "skip"` have text values. The docstring explains the difference: with a plain insert, contenders that insert overlapping rows at the same moment wait for each other's uncommitted rows and may deadlock (PostgreSQL ends one with `40P01`); with `ON CONFLICT DO NOTHING` an inserter waits only for an older transaction, so a deadlock between contenders cannot happen. In both modes the constraint decides who wins. `_range` turns a `RentalPeriod` into `Range(first, return, "[)")`, a half-open range that psycopg sends as a `daterange`.

### `postgres_rentals.py`: the `PostgresRentals` class

```python
class PostgresRentals:
    """One connection's view of the rental database.

    Not safe to share between threads: give each thread its own connection and its own `PostgresRentals`.
    """

    def __init__(self, connection: psycopg.Connection[Any], insert_mode: InsertMode = InsertMode.SKIP) -> None:
        self._connection = connection
        self._insert = INSERT_RENTAL if insert_mode is InsertMode.RAISE else INSERT_RENTAL_SKIPPING_CLASH
```

The class wraps one connection. Its docstring warns that it is not safe to share between threads. The constructor stores the connection and chooses which insert statement to use (`is` compares identity, the right way to compare enum members).

```python
    def book(self, item_id: int, customer_id: int, period: RentalPeriod) -> Rental:
        """Insert in one statement and translate the constraint violations into the shop's named errors."""
        try:
            with self._connection.transaction():
                row = self._connection.execute(self._insert, (item_id, customer_id, _range(period))).fetchone()
        except errors.ExclusionViolation as error:
            raise ItemAlreadyBookedError(
                item_id, period.first_day.isoformat(), period.return_day.isoformat()
            ) from error
        except errors.DeadlockDetected as error:
            raise BookingDeadlockError(f"deadlock while booking item {item_id} for {period}") from error
        except errors.ForeignKeyViolation as error:
            if error.diag.constraint_name == "rentals_customer_id_fkey":
                raise UnknownCustomerError(customer_id) from error
            raise UnknownItemError(item_id) from error
        if row is None:  # ON CONFLICT DO NOTHING skipped the insert: the exclusion constraint refused it
            raise ItemAlreadyBookedError(item_id, period.first_day.isoformat(), period.return_day.isoformat())
        return Rental(int(row[0]), item_id, customer_id, period)
```

`book` runs the insert inside `with self._connection.transaction():` (a real transaction: committed on a normal exit, rolled back on an exception). `execute(sql, params)` returns a cursor and `.fetchone()` gives the first row as a tuple, or `None` if there was none. The `except` blocks translate driver errors into domain errors, each with `from error`, which keeps the original error attached as the cause:

- `ExclusionViolation` becomes `ItemAlreadyBookedError`.
- `DeadlockDetected` becomes `BookingDeadlockError`, which `BookItem` retries.
- `ForeignKeyViolation` becomes `UnknownCustomerError` or `UnknownItemError`, depending on `error.diag.constraint_name`, the name of the violated constraint (`rentals_customer_id_fkey` is the name PostgreSQL gave the foreign key to `customers`).

If the insert returned no row, `ON CONFLICT DO NOTHING` skipped it, which means the exclusion constraint refused it, so the same booked error is raised. Otherwise `row[0]` is the new id.

```python
    def add_item(self, name: str, daily_rate: Decimal) -> Item:
        row = self._connection.execute(
            "INSERT INTO items (name, daily_rate) VALUES (%s, %s) RETURNING item_id", (name, daily_rate)
        ).fetchone()
        assert row is not None
        return Item(int(row[0]), name, daily_rate)

    def add_customer(self, name: str) -> Customer:
        row = self._connection.execute(
            "INSERT INTO customers (name) VALUES (%s) RETURNING customer_id", (name,)
        ).fetchone()
        assert row is not None
        return Customer(int(row[0]), name)

    def is_item_free(self, item_id: int, period: RentalPeriod) -> bool:
        row = self._connection.execute(IS_FREE, (item_id, _range(period))).fetchone()
        assert row is not None
        return bool(row[0])
```

`add_item`, `add_customer` and `is_item_free` each run one statement. `assert row is not None` tells the type checker (and a reader) that an `INSERT ... RETURNING` always returns a row. `bool(row[0])` converts the database's boolean.

```python
    def free_items(self, period: RentalPeriod) -> list[Item]:
        rows = self._connection.execute(FREE_ITEMS, (_range(period),)).fetchall()
        return [Item(int(item_id), str(name), Decimal(rate)) for item_id, name, rate in rows]

    def history(self, customer_id: int) -> list[Rental]:
        rows = self._connection.execute(HISTORY, (customer_id,)).fetchall()
        return [
            Rental(int(rental_id), int(item_id), int(customer), RentalPeriod(first_day, return_day))
            for rental_id, item_id, customer, first_day, return_day in rows
        ]

    def returns_on(self, day: date) -> list[ReturnDue]:
        rows = self._connection.execute(RETURNS_ON, (day,)).fetchall()
        return [ReturnDue(int(rental_id), str(item), str(customer)) for rental_id, item, customer in rows]

    def revenue_by_item_and_month(self) -> list[MonthlyRevenue]:
        rows = self._connection.execute(REVENUE).fetchall()
        return [MonthlyRevenue.of(str(item), first_day, Decimal(amount)) for item, first_day, amount in rows]

    def never_rented(self) -> list[Item]:
        rows = self._connection.execute(NEVER_RENTED).fetchall()
        return [Item(int(item_id), str(name), Decimal(rate)) for item_id, name, rate in rows]

    def find_customer(self, name: str) -> Customer | None:
        rows = self._connection.execute("SELECT customer_id, name FROM customers WHERE name = %s", (name,)).fetchall()
        return Customer(int(rows[0][0]), str(rows[0][1])) if len(rows) == 1 else None
```

The read methods call `.fetchall()`, which returns all rows as a list of tuples, and build domain objects with **list comprehensions**: `[Item(...) for item_id, name, rate in rows]` loops over the rows, **unpacking** each tuple into three names. `int(...)`, `str(...)` and `Decimal(...)` convert and also reassure the type checker. In `history`, `lower(during)` and `upper(during)` arrive as Python `date` values, so the period is rebuilt as `RentalPeriod(first_day, return_day)`. `find_customer` returns a customer only if exactly one row matched, else `None`.

```python
def gateway_opener(settings: PostgresSettings, insert_mode: InsertMode = InsertMode.SKIP) -> GatewayOpener:
    """An opener that gives every caller its own connection, closed when the caller's block ends."""

    @contextmanager
    def open_gateway() -> Iterator[RentalGateway]:
        with session(settings) as connection:
            yield PostgresRentals(connection, insert_mode)

    return open_gateway
```

`gateway_opener` returns a function that opens a fresh session and yields a `PostgresRentals` for it. The inner function is decorated with `@contextmanager`, and the connection is closed when the caller's `with` ends. The race uses it to give every contender its own connection.

### `health_probes.py`

```python
"""Adapter: the health check of the one dependency, PostgreSQL."""

from __future__ import annotations

import psycopg

from ..application.health import ProbeFailedError
from .postgres import session
from .settings import PostgresSettings


class PostgresSchemaProbe:
    """Healthy when PostgreSQL answers and the rental tables and the exclusion constraint exist."""

    name = "postgres"

    def __init__(self, settings: PostgresSettings) -> None:
        self._settings = settings

    def check(self) -> str:
        try:
            with session(self._settings) as connection:
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT table_name FROM information_schema.tables WHERE table_schema = %s",
                        (self._settings.schema,),
                    )
                }
                missing = {"customers", "items", "rentals"} - tables
                if missing:
                    raise ProbeFailedError(f"missing tables {sorted(missing)}; run make db")
                constraint = connection.execute(
                    "SELECT 1 FROM pg_constraint WHERE conname = 'rentals_item_id_during_excl' AND contype = 'x' "
                    "AND connamespace = %s::regnamespace",
                    (self._settings.schema,),
                ).fetchone()
                if constraint is None:
                    raise ProbeFailedError(
                        "the exclusion constraint rentals_item_id_during_excl is missing; run make db"
                    )
        except psycopg.Error as error:
            raise ProbeFailedError(f"cannot use PostgreSQL: {error}") from error
        return "customers, items, rentals and the exclusion constraint exist"
```

`PostgresSchemaProbe` matches the `HealthProbe` protocol: a class attribute `name = "postgres"` and a `check` method. The first query reads `information_schema.tables`, a standard catalog view that lists tables, filtered by schema. The `{ row[0] for row in ... }` is a **set comprehension**. `{"customers", "items", "rentals"} - tables` is set difference: the required names that are absent. If any are missing the probe fails with a message that says `run make db`. The second query looks in `pg_constraint`, PostgreSQL's catalog of constraints, for the exclusion constraint: `contype = 'x'` means exclusion, and `connamespace = %s::regnamespace` converts the schema name into the internal schema identifier. `except psycopg.Error as error:` catches any driver error (the server is down, wrong password) and re-raises it as `ProbeFailedError`. If everything passes it returns the success text.

## Try it yourself

```bash
make up && make db && set -a && . ./.env && set +a && .venv/bin/python -c "
from rental_shop.infrastructure.settings import Settings
from rental_shop.infrastructure.postgres import session
s = Settings.from_env().postgres
with session(s) as c:
    print(c.execute('SHOW search_path').fetchone(), c.execute('SHOW statement_timeout').fetchone())"
```
`set -a` makes every variable assigned by the next `. ./.env` an exported one, so the Python program (which reads the real environment, not the file) sees the settings. Expect `('public, public',)` and `('30s',)`: the configured schema, then `public`, and the 30 000 ms timeout shown as 30 seconds.

```bash
make health
```
Expect `ok postgres: customers, items, rentals and the exclusion constraint exist`.

```bash
docker compose exec -T postgres psql -U shop -d rentals -c "insert into rentals (item_id, customer_id, during) values (1, 2, daterange('2026-11-03','2026-11-05'))"
```
Expect the server's own error: `conflicting key value violates exclusion constraint`, the message psycopg turns into `ExclusionViolation`.

```bash
.venv/bin/python -m pytest tests/integration -m integration -q
```
Runs the adapter's tests against the database.

## Mistakes people make

- **Building SQL with f-strings.** Values go in the parameter tuple.
- **Leaving a connection open** after an error. `session` closes in `finally`.
- **Sharing one connection between threads.** The race gives each its own.
- **Catching a database error by message text.** The code catches classes that map to SQLSTATE codes.
- **Forgetting a unit of work.** Autocommit plus `transaction()` makes boundaries explicit.

## Check yourself

1. What is a SQLSTATE and where does `23P01` appear? *A five-character error code; it is `ExclusionViolation` in psycopg.*
2. Why are parameters passed separately? *So data can never be read as SQL (injection).*
3. What does `autocommit=True` change? *Each statement commits at once unless inside `transaction()`.*
4. What does `from error` do on a `raise`? *It keeps the original error as the cause.*
5. Why does `book` raise the booked error when `row is None`? *`ON CONFLICT DO NOTHING` returns nothing when the constraint refused the row.*

## Further reading

- psycopg 3 documentation (this repository locks psycopg 3.3.6 in `requirements.lock`): https://www.psycopg.org/psycopg3/docs/
- Passing parameters: https://www.psycopg.org/psycopg3/docs/basic/params.html
- Transactions: https://www.psycopg.org/psycopg3/docs/basic/transactions.html
- PostgreSQL error codes: https://www.postgresql.org/docs/18/errcodes-appendix.html
