# pytest

## What it is

pytest is a Python tool that finds and runs **tests**. A test is a small function that runs some of your code and uses `assert` to state what must be true. If an `assert` is false, or an error escapes, the test **fails**; otherwise it **passes**. pytest locates tests by name: files called `test_*.py`, and functions called `test_*`. This repository pins pytest 9.1.1 (`pytest>=8,<10` in `pyproject.toml`, locked in `requirements-dev.lock`).

## Why this repository uses it

The lesson claims that the database, not the application, prevents a double booking. Tests are how that claim is checked every time, in three layers:

- **Unit tests** (`tests/unit/`): the rules with in-memory fakes, no database, run in a second.
- **Integration tests** (`tests/integration/`): the PostgreSQL adapter against a real server.
- **End-to-end tests** (`tests/e2e/`): the command-line programs run as separate processes, as `make run` runs them.

## Where it appears

| Path | What it holds |
|---|---|
| `tests/conftest.py` | Shared fixtures that build a private schema in PostgreSQL. |
| `tests/unit/application/fakes.py` | The in-memory shop and the fixed clock. |
| `tests/unit/domain/test_period.py` | Periods and the race tally. |
| `tests/unit/application/test_*.py` | Booking, race, report and health use cases. |
| `tests/unit/infrastructure/test_*.py` | Clock, logging, shutdown, retry, settings. |
| `tests/unit/interfaces/test_report_format.py` | Output text and command-line defaults. |
| `tests/integration/test_postgres_rentals.py` | The adapter and the schema's rules, real database. |
| `tests/e2e/test_lesson_scenario.py` | The lesson through the real programs. |
| `pyproject.toml` | `[tool.pytest.ini_options]`. |
| the empty `__init__.py` files | Make `tests` and its folders packages so relative imports work. |

## How it works underneath

`pytest` collects the test files, imports each, and calls each test function. Before running, it **rewrites** the `assert` statements so that a failure shows the values on both sides. A **fixture** is a function marked `@pytest.fixture` that prepares something a test needs; a test asks for it by naming a parameter with the same name, and pytest passes the result in (this is **dependency injection**). A fixture that uses `yield` runs its set-up before the `yield` and its clean-up after the test, even if the test failed. A file named `conftest.py` shares fixtures with every test below it. A **marker** (`@pytest.mark.name`) labels tests so you can select them with `-m name`. `pytest.raises(Error)` is a context manager that passes only if the block raises that error. `@pytest.mark.parametrize` runs one test function once per row of data. A **fake** is a simple stand-in object that behaves like the real one without its cost, such as a database.

## Walkthrough of this repository's use

### Configuration

The settings live in `pyproject.toml`; each key is explained in [toml.md](toml.md) and its section is quoted here.

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra --strict-markers"
markers = [
    "integration: needs PostgreSQL from docker-compose.yml (make up)",
    "e2e: runs the lesson's scenario through the command-line programs against PostgreSQL",
]
```

- `testpaths = ["tests"]`: when run without arguments, look only in `tests/`.
- `addopts = "-ra --strict-markers"`: options added to every run. `-r` prints a summary of results and `a` means "all except passes". `--strict-markers` makes an unknown marker an error, which catches typos.
- `markers`: registers `integration` and `e2e`, with a description. Commands such as `pytest tests/integration -m integration` select by them.

### `conftest.py`: a private schema per test

```python
"""Fixtures for the tests that need PostgreSQL from docker-compose.yml.

Each test gets its own schema holding the lesson's tables and seed, so tests never touch each other's rows or the
data a reader loaded with `make db`, and run in any order.
"""

import dataclasses
import pathlib
import uuid
from collections.abc import Iterator
from typing import Any

import psycopg
import pytest

from rental_shop.infrastructure import postgres
from rental_shop.infrastructure.settings import PostgresSettings, Settings

SQL = pathlib.Path(__file__).resolve().parent.parent / "sql"
SCHEMA_SCRIPTS = [SQL / "001_schema.sql", SQL / "002_seed.sql", *sorted((SQL / "migrations").glob("*.sql"))]

```

- The docstring states the promise: every test gets its own schema holding the tables and the seed, so tests never touch each other or the data a reader loaded with `make db`, and the order of tests does not matter. (A **schema** is a named namespace of tables in a database; see [sql.md](sql.md).)
- `pathlib.Path` represents file paths. `pathlib.Path(__file__).resolve().parent.parent / "sql"` takes this file's own path, makes it absolute, goes up two folders (to the repository root) and then into `sql/`. The `/` operator joins path parts.
- `SCHEMA_SCRIPTS` is a list of the SQL files that build a fresh lab: the schema, the seed, and every migration in sorted order. `*sorted(...)` **unpacks** the sorted list into the list literal.

```python
@pytest.fixture
def lab() -> Iterator[PostgresSettings]:
    """Settings that point at a fresh schema with the schema, seed and migrations applied; dropped afterwards."""
    base = Settings.from_env().postgres
    name = f"t_{uuid.uuid4().hex[:12]}"
    admin = dataclasses.replace(base, schema="public")
    with postgres.session(admin) as connection:
        connection.execute(f"CREATE SCHEMA {name}")
    settings = dataclasses.replace(base, schema=name)
    try:
        with postgres.session(settings) as connection:
            for script in SCHEMA_SCRIPTS:
                connection.execute(script.read_text())
        yield settings
    finally:
        with postgres.session(admin) as connection:
            connection.execute(f"DROP SCHEMA {name} CASCADE")

```

- `@pytest.fixture` makes `lab` a fixture. It returns `Iterator[PostgresSettings]` because it uses `yield`.
- `base = Settings.from_env().postgres` reads the connection settings from the environment (`make test-integration` exports `.env`).
- `name = f"t_{uuid.uuid4().hex[:12]}"` builds a schema name such as `t_9f2c4a1b7d3e`: `uuid4()` is a random unique id, `.hex` its hexadecimal text, `[:12]` the first 12 characters. A random name means two test runs never collide. It matches the lower-case identifier rule of the settings.
- `dataclasses.replace(base, schema="public")` copies the frozen settings with one field changed. The first `with` block, as the admin on `public`, runs `CREATE SCHEMA <name>`. The f-string is safe because the name is generated, not user input.
- The `try` runs the three scripts as a connection whose search path is the new schema; `connection.execute(script.read_text())` sends a whole file. Then `yield settings` runs the test.
- `finally:` drops the schema with `CASCADE` (also dropping the tables in it), whether or not the test passed.

```python
@pytest.fixture
def connection(lab: PostgresSettings) -> Iterator[psycopg.Connection[Any]]:
    """A connection whose search path is the test's schema."""
    with postgres.session(lab) as db:
        yield db
```

`connection` is a second fixture that depends on the first: its parameter is named `lab`, so pytest runs `lab` first. It opens a session on the test's schema and yields the connection.

### `fakes.py`: the in-memory shop

```python
"""In-memory stand-ins for the ports, so use cases are tested without a database."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from rental_shop.domain.errors import (
    BookingDeadlockError,
    ItemAlreadyBookedError,
    UnknownCustomerError,
    UnknownItemError,
)
from rental_shop.domain.model import Customer, Item, MonthlyRevenue, Rental, ReturnDue
from rental_shop.domain.period import RentalPeriod


@dataclass
class InMemoryShop:
    """A rental shop in memory that refuses overlaps the way the exclusion constraint does, under one lock."""

    items: dict[int, Item] = field(default_factory=dict)
    customers: dict[int, Customer] = field(default_factory=dict)
    rentals: list[Rental] = field(default_factory=list)
    deadlocks_to_raise: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)

```

`InMemoryShop` stands in for the database. It is a plain (not frozen) dataclass holding dictionaries of items and customers, a list of rentals, a counter `deadlocks_to_raise`, and a `Lock` to keep it safe when twenty threads use it. Each mutable field uses `field(default_factory=...)` so each shop gets its own container.

```python
    def book(self, item_id: int, customer_id: int, period: RentalPeriod) -> Rental:
        with self.lock:
            if self.deadlocks_to_raise > 0:
                self.deadlocks_to_raise -= 1
                raise BookingDeadlockError("deadlock")
            if item_id not in self.items:
                raise UnknownItemError(item_id)
            if customer_id not in self.customers:
                raise UnknownCustomerError(customer_id)
            if any(r.item_id == item_id and r.period.overlaps(period) for r in self.rentals):
                raise ItemAlreadyBookedError(item_id, period.first_day.isoformat(), period.return_day.isoformat())
            rental = Rental(len(self.rentals) + 1, item_id, customer_id, period)
            self.rentals.append(rental)
            return rental

    def add_item(self, name: str, daily_rate: Decimal) -> Item:
        with self.lock:
            item = Item(len(self.items) + 1, name, daily_rate)
            self.items[item.item_id] = item
            return item

    def add_customer(self, name: str) -> Customer:
        with self.lock:
            customer = Customer(len(self.customers) + 1, name)
            self.customers[customer.customer_id] = customer
            return customer

```

`book` imitates the constraint under a lock: it raises a deadlock error while the counter is positive (decrementing it each time), `UnknownItemError` or `UnknownCustomerError` when the id is absent, `ItemAlreadyBookedError` if `any(...)` finds a rental of the same item with an overlapping period (using the domain's `overlaps`, the same rule as PostgreSQL's `&&`), and otherwise records a new rental numbered `len(self.rentals) + 1`. `add_item` and `add_customer` number new entries the same way.

```python
    def is_item_free(self, item_id: int, period: RentalPeriod) -> bool:
        return not any(r.item_id == item_id and r.period.overlaps(period) for r in self.rentals)

    def free_items(self, period: RentalPeriod) -> list[Item]:
        return [item for item in self.items.values() if self.is_item_free(item.item_id, period)]

    def history(self, customer_id: int) -> list[Rental]:
        return sorted((r for r in self.rentals if r.customer_id == customer_id), key=lambda r: (r.period, r.rental_id))

    def returns_on(self, day: date) -> list[ReturnDue]:
        return [
            ReturnDue(r.rental_id, self.items[r.item_id].name, self.customers[r.customer_id].name)
            for r in self.rentals
            if r.period.return_day == day
        ]

    def revenue_by_item_and_month(self) -> list[MonthlyRevenue]:
        totals: dict[tuple[str, str], Decimal] = {}
        for r in self.rentals:
            item = self.items[r.item_id]
            key = (item.name, r.period.first_day.strftime("%Y-%m"))
            totals[key] = totals.get(key, Decimal(0)) + item.daily_rate * r.period.days
        return [MonthlyRevenue(name, month, amount) for (name, month), amount in sorted(totals.items())]

    def never_rented(self) -> list[Item]:
        rented = {r.item_id for r in self.rentals}
        return [item for item in self.items.values() if item.item_id not in rented]

    def find_customer(self, name: str) -> Customer | None:
        matches = [c for c in self.customers.values() if c.name == name]
        return matches[0] if len(matches) == 1 else None

    @contextmanager
    def open(self) -> Iterator[InMemoryShop]:
        """Plays the part of `GatewayOpener`: every contender shares the one shop, as connections share a database."""
        yield self

```

The remaining methods answer the shop's questions in plain Python: `is_item_free`, `free_items`, `history` (sorted by period then id; periods compare because `order=True`), `returns_on`, `revenue_by_item_and_month` (a dictionary keyed by `(item, month)` and summed with `totals.get(key, Decimal(0))`; `sorted(totals.items())` sorts by key), `never_rented` (a set of rented ids), `find_customer`. `open` is decorated with `@contextmanager` and just yields the shop itself, imitating `GatewayOpener`: every contender shares the one shop, as connections share a database.

```python
class FixedClock:
    """A clock that always says the same day."""

    def __init__(self, day: date) -> None:
        self._day = day

    def today(self) -> date:
        return self._day


def lesson_shop() -> InMemoryShop:
    """The lesson's hand-checkable data: 2 customers, 4 items, 7 rentals."""
    shop = InMemoryShop()
    for name in ("Ada", "Bruno"):
        shop.add_customer(name)
    for name, rate in (("Drill", 10), ("Ladder", 8), ("Tent", 15), ("Kayak", 20)):
        shop.add_item(name, Decimal(rate))

    def day(text: str) -> date:
        return date.fromisoformat(text)

    for item_id, customer_id, first, last in (
        (1, 1, "2026-11-01", "2026-11-04"),
        (1, 2, "2026-11-04", "2026-11-06"),
        (2, 1, "2026-11-02", "2026-11-09"),
        (3, 2, "2026-10-20", "2026-10-23"),
        (1, 1, "2026-12-01", "2026-12-03"),
        (3, 1, "2026-11-07", "2026-11-10"),
        (2, 2, "2026-10-25", "2026-10-28"),
    ):
        shop.book(item_id, customer_id, RentalPeriod(day(first), day(last)))
    return shop
```

`FixedClock` always returns one day. `lesson_shop()` builds the hand-checkable data of the lesson: two customers, four items and the seven rentals of `sql/002_seed.sql`. The nested function `day` converts text to dates. The `for ... in ((...), (...))` loop unpacks each tuple into four names and books the rental.

### Domain tests

```python
from datetime import date

import pytest

from rental_shop.domain.errors import InvalidPeriodError
from rental_shop.domain.model import MonthlyRevenue, RaceTally
from rental_shop.domain.period import RentalPeriod

NOV_1 = date(2026, 11, 1)


def period(first_day: int, return_day: int) -> RentalPeriod:
    return RentalPeriod(date(2026, 11, first_day), date(2026, 11, return_day))


def test_a_period_counts_rental_days_without_the_return_day():
    assert period(1, 4).days == 3


def test_overlapping_periods_clash():
    assert period(1, 4).overlaps(period(3, 5))
    assert period(3, 5).overlaps(period(1, 4))


def test_a_period_inside_another_overlaps_it():
    assert period(1, 10).overlaps(period(3, 5))


def test_periods_that_only_touch_do_not_overlap():
    assert not period(1, 4).overlaps(period(4, 6))
    assert not period(4, 6).overlaps(period(1, 4))


def test_distant_periods_do_not_overlap():
    assert not period(1, 4).overlaps(period(10, 12))

```

Plain functions that assert. `period(1, 4)` is a helper that builds a November 2026 period. The tests state the rules: three rental days for `[1, 4)`, overlap is symmetric, a period inside another overlaps it, touching periods do not overlap, distant periods do not.

```python
def test_a_period_must_end_after_it_starts():
    with pytest.raises(InvalidPeriodError, match="after the first day"):
        period(4, 4)
    with pytest.raises(InvalidPeriodError):
        period(5, 3)


def test_starting_builds_a_period_from_a_length():
    assert RentalPeriod.starting(NOV_1, 3) == period(1, 4)


def test_a_rental_lasts_at_least_one_day():
    with pytest.raises(InvalidPeriodError, match="at least one day"):
        RentalPeriod.starting(NOV_1, 0)


def test_shifting_keeps_the_length():
    shifted = period(1, 4).shifted(2)
    assert shifted == period(3, 6)
    assert shifted.days == 3
    assert period(3, 6).shifted(-2) == period(1, 4)


def test_a_period_prints_as_its_two_dates():
    assert str(period(1, 4)) == "2026-11-01 to 2026-11-04"


def test_periods_sort_by_first_day():
    assert sorted([period(5, 6), period(1, 2)]) == [period(1, 2), period(5, 6)]

```

- `with pytest.raises(InvalidPeriodError, match="after the first day"):` passes only if the block raises that error and its message matches the **regular expression** (`match` uses a search). Periods with equal or reversed dates are refused.
- `starting`, shifting (positive and negative), `str()` and sorting are checked with `==` on dataclasses, which compares all fields.

```python
def test_revenue_names_its_month_as_year_and_month():
    assert MonthlyRevenue.of("Drill", date(2026, 12, 3), 20).month == "2026-12"  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("successes", "refused", "failed", "deadlocked", "correct"),
    [
        (1, 19, 0, 0, True),
        (2, 18, 0, 0, False),
        (0, 19, 1, 0, False),
        (1, 18, 1, 0, False),
        (1, 18, 0, 1, False),
        (0, 20, 0, 0, False),
    ],
)
def test_a_race_is_correct_only_with_exactly_one_winner_and_nothing_else_wrong(
    successes, refused, failed, deadlocked, correct
):
    assert RaceTally(20, successes, refused, failed, deadlocked).is_correct is correct


def test_one_winner_is_the_safety_property_even_when_some_contenders_gave_up():
    assert RaceTally(20, 1, 15, 0, 4).one_winner
    assert not RaceTally(20, 2, 18, 0, 0).one_winner
```

The revenue test uses `# type: ignore[arg-type]` because it passes an `int` where a `Decimal` is declared; it only checks the month text. `@pytest.mark.parametrize(names, rows)` runs the test below it once per row: six combinations of outcome counts, each with the expected truth value of `is_correct`. `is correct` compares identity with `True` or `False`. The last test checks that `one_winner` stays true when some contenders gave up after deadlocks.

### Application tests

```python
import random
from datetime import date

import pytest

from rental_shop.application.book_item import BookItem
from rental_shop.domain.errors import (
    BookingDeadlockError,
    InvalidPeriodError,
    ItemAlreadyBookedError,
    UnknownCustomerError,
    UnknownItemError,
)

from .fakes import lesson_shop

NOV_3 = date(2026, 11, 3)


def test_a_free_item_is_booked_and_the_rental_comes_back():
    shop = lesson_shop()
    rental = BookItem(shop)(4, 1, NOV_3, 2)
    assert (rental.item_id, rental.customer_id, str(rental.period)) == (4, 1, "2026-11-03 to 2026-11-05")


def test_overlapping_dates_are_refused_with_a_message_naming_the_item():
    with pytest.raises(ItemAlreadyBookedError, match="item 1 is already booked"):
        BookItem(lesson_shop())(1, 2, NOV_3, 2)


def test_a_rental_that_starts_on_the_return_day_is_allowed():
    rental = BookItem(lesson_shop())(1, 2, date(2026, 11, 6), 2)
    assert str(rental.period) == "2026-11-06 to 2026-11-08"


def test_a_period_that_cannot_exist_is_refused_before_the_database_is_asked():
    shop = lesson_shop()
    with pytest.raises(InvalidPeriodError):
        BookItem(shop)(4, 1, NOV_3, 0)
    assert len(shop.rentals) == 7


def test_unknown_references_are_named():
    with pytest.raises(UnknownItemError):
        BookItem(lesson_shop())(99, 1, NOV_3, 1)
    with pytest.raises(UnknownCustomerError):
        BookItem(lesson_shop())(4, 99, NOV_3, 1)

```

`from .fakes import lesson_shop` is a relative import (the dot is the current package). `BookItem(shop)(4, 1, NOV_3, 2)` builds the use case, then calls it. The first test checks the item, customer and period text. Another checks the refusal message (`match="item 1 is already booked"`). A rental starting on the return day is allowed. A zero-day rental is refused before any booking, and `len(shop.rentals) == 7` shows nothing was written. The unknown references are named.

```python
def test_a_deadlock_victim_is_retried_with_doubling_pauses_inside_the_jitter_band():
    shop = lesson_shop()
    shop.deadlocks_to_raise = 3
    pauses: list[float] = []
    retried: list[int] = []
    book = BookItem(shop, pause_seconds=0.1, sleep=pauses.append, on_retry=retried.append, rng=random.Random(1))
    book(4, 1, NOV_3, 1)
    for pause, ceiling in zip(pauses, (0.1, 0.2, 0.4), strict=True):
        assert ceiling * 0.5 <= pause <= ceiling
    assert retried == [1, 2, 3]
    assert len(shop.rentals) == 8


def test_a_retry_after_a_deadlock_can_still_be_refused_as_booked():
    shop = lesson_shop()
    shop.deadlocks_to_raise = 1
    with pytest.raises(ItemAlreadyBookedError):
        BookItem(shop, sleep=lambda _: None)(1, 2, NOV_3, 2)


def test_the_deadlock_is_raised_when_every_attempt_loses():
    shop = lesson_shop()
    shop.deadlocks_to_raise = 10
    with pytest.raises(BookingDeadlockError):
        BookItem(shop, attempts=3, sleep=lambda _: None)(4, 1, NOV_3, 1)
    assert shop.deadlocks_to_raise == 7
```

The retry tests use fakes for time and randomness: `sleep=pauses.append` passes the list's `append` method as the sleep function, so each "sleep" is just recorded; `on_retry=retried.append` records the attempts; `random.Random(1)` is a generator with a fixed seed, so runs are repeatable. `zip(pauses, (0.1, 0.2, 0.4), strict=True)` pairs each pause with its ceiling and raises if the lengths differ. Each pause must lie in the band from half the ceiling to the ceiling. Another test shows that a retry after a deadlock can still be refused as already booked. The last shows that when every attempt loses (`attempts=3`, 10 deadlocks queued), `BookingDeadlockError` escapes and exactly three were consumed (`10 - 3 == 7`). `lambda _: None` is a function that ignores its argument and returns nothing.

```python
from rental_shop.application.race import Race

from .fakes import InMemoryShop


def test_exactly_one_of_twenty_contenders_wins_and_the_rest_are_refused():
    shop = InMemoryShop()
    tally = Race(shop.open, sleep=lambda _: None, contenders=20).run_round("1")
    assert (tally.successes, tally.refused, tally.failed) == (1, 19, 0)
    assert tally.is_correct
    assert len(shop.rentals) == 1


def test_every_round_uses_a_fresh_item_so_rounds_do_not_affect_each_other():
    shop = InMemoryShop()
    race = Race(shop.open, sleep=lambda _: None, contenders=5)
    assert race.run_round("1").is_correct
    assert race.run_round("2").is_correct
    assert len(shop.items) == 2
    assert len(shop.rentals) == 2


def test_deadlock_victims_are_retried_and_counted_and_still_end_up_refused():
    shop = InMemoryShop(deadlocks_to_raise=3)
    tally = Race(shop.open, sleep=lambda _: None, contenders=6).run_round("1")
    assert tally.is_correct
    assert tally.deadlock_retries == 3


def test_a_contender_that_loses_every_retry_to_deadlocks_is_counted_apart_from_other_failures():
    shop = InMemoryShop(deadlocks_to_raise=10_000)
    tally = Race(shop.open, sleep=lambda _: None, contenders=3).run_round("1")
    assert (tally.successes, tally.deadlocked, tally.failed) == (0, 3, 0)
    assert not tally.one_winner


def test_a_contender_that_fails_for_another_reason_is_counted_and_the_round_is_not_correct():
    class Broken(InMemoryShop):
        def book(self, item_id, customer_id, period):
            raise RuntimeError("connection lost")

    shop = Broken()
    tally = Race(shop.open, sleep=lambda _: None, contenders=4).run_round("1")
    assert tally.failed == 4
    assert not tally.is_correct
```

The race against the in-memory shop with no waiting. `shop.open` is the opener. One of twenty wins, 19 are refused, none fails. Each round uses a fresh item, so two rounds produce two items and two rentals. With `deadlocks_to_raise=3`, three retries are counted and the round is still correct. With an enormous number of deadlocks, every contender is `deadlocked`, not `failed`. A subclass `Broken(InMemoryShop)` overrides `book` to raise `RuntimeError`, defined inside the test so it exists only there; every contender then counts as `failed` and the round is not correct.

```python
from datetime import date

import pytest

from rental_shop.application.shop_questions import ShopQuestions, UnknownCustomerNameError
from rental_shop.domain.period import RentalPeriod

from .fakes import FixedClock, lesson_shop

WEEKEND = RentalPeriod(date(2026, 11, 7), date(2026, 11, 9))


def ask(today: date | None = date(2026, 11, 4), customer: str = "Ada"):
    return ShopQuestions(lesson_shop(), FixedClock(date(2026, 11, 4))).report(WEEKEND, customer, today)


def test_the_items_free_next_weekend_are_the_drill_and_the_kayak():
    assert [item.name for item in ask().free_items] == ["Drill", "Kayak"]


def test_adas_history_is_rentals_1_3_5_and_6():
    assert sorted(rental.rental_id for rental in ask().history) == [1, 3, 5, 6]


def test_the_history_is_in_date_order():
    assert [rental.rental_id for rental in ask().history] == [1, 3, 6, 5]


def test_todays_return_is_rental_1():
    due = ask().returns_today
    assert [(d.rental_id, d.item_name, d.customer_name) for d in due] == [(1, "Drill", "Ada")]


def test_revenue_per_item_and_month_matches_the_hand_check():
    rows = [(row.item_name, row.month, int(row.amount)) for row in ask().revenue]
    assert rows == [
        ("Drill", "2026-11", 50),
        ("Drill", "2026-12", 20),
        ("Ladder", "2026-10", 24),
        ("Ladder", "2026-11", 56),
        ("Tent", "2026-10", 45),
        ("Tent", "2026-11", 45),
    ]


def test_only_the_kayak_was_never_rented():
    assert [item.name for item in ask().never_rented] == ["Kayak"]


def test_today_comes_from_the_clock_when_not_given():
    assert ask(today=None).today == date(2026, 11, 4)


def test_an_unknown_customer_is_a_named_error():
    with pytest.raises(UnknownCustomerNameError, match="Zed"):
        ask(customer="Zed")
```

`ask(...)` builds the use case over the lesson shop with a fixed clock and returns the report. The tests check each of the five answers against the hand-calculated values, including the date order of the history, the clock being used when `today` is `None`, and the named error for an unknown customer (`match="Zed"`).

```python
from rental_shop.application.health import ProbeFailedError, check_health


class Probe:
    def __init__(self, name: str, error: str | None = None) -> None:
        self.name, self._error = name, error

    def check(self) -> str:
        if self._error:
            raise ProbeFailedError(self._error)
        return "fine"


def test_all_probes_passing_is_healthy():
    report = check_health([Probe("a"), Probe("b")])
    assert report.healthy
    assert [r.detail for r in report.results] == ["fine", "fine"]


def test_one_failing_probe_is_reported_and_makes_the_report_unhealthy():
    report = check_health([Probe("a"), Probe("b", "down")])
    assert not report.healthy
    assert [(r.name, r.ok, r.detail) for r in report.results] == [("a", True, "fine"), ("b", False, "down")]
```

A tiny `Probe` class is a fake probe. One test shows all-passing probes give a healthy report; another shows a failing probe is reported as `(name, False, message)` and makes the report unhealthy.

### Infrastructure tests

```python
from datetime import date

from rental_shop.infrastructure.clock import SystemClock


def test_the_system_clock_reports_a_date():
    assert isinstance(SystemClock().today(), date)
```

```python
import io
import logging
import signal

from rental_shop.infrastructure.logging import configure_logging, fields
from rental_shop.infrastructure.shutdown import ShutdownSignal


def test_a_record_becomes_one_logfmt_line_with_its_fields():
    stream = io.StringIO()
    configure_logging("INFO", stream)
    logging.getLogger("demo").info("partitions assigned", extra=fields(member="consumer-1", partitions=[0, 1]))
    line = stream.getvalue().strip()
    assert line.startswith("ts=")
    assert "level=INFO" in line
    assert "logger=demo" in line
    assert 'msg="partitions assigned"' in line
    assert "member=consumer-1" in line
    assert 'partitions="[0, 1]"' in line


def test_records_below_the_level_are_dropped_():
    stream = io.StringIO()
    configure_logging("INFO", stream)
    logging.getLogger("demo").debug("hidden")
    assert stream.getvalue() == ""


def test_an_exception_is_attached_to_the_line():
    stream = io.StringIO()
    configure_logging("INFO", stream)
    try:
        raise ValueError("boom")
    except ValueError:
        logging.getLogger("demo").exception("failed")
    assert "exc=" in stream.getvalue()
    assert "boom" in stream.getvalue()


def test_configuring_twice_does_not_duplicate_lines():
    stream = io.StringIO()
    configure_logging("INFO", stream)
    configure_logging("INFO", stream)
    logging.getLogger("demo").info("once")
    assert stream.getvalue().count("msg=once") == 1


def test_a_shutdown_signal_starts_unset_and_is_set_by_request():
    shutdown = ShutdownSignal()
    assert not shutdown.requested
    shutdown.request()
    assert shutdown.requested


def test_sigterm_sets_the_flag_once_installed():
    shutdown = ShutdownSignal()
    previous = {number: signal.getsignal(number) for number in (signal.SIGINT, signal.SIGTERM)}
    try:
        shutdown.install()
        signal.raise_signal(signal.SIGTERM)
        assert shutdown.requested
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)
```

`io.StringIO()` is an in-memory text file, passed as the log stream so the test can read what was written. The tests check: one record becomes one logfmt line with `ts=`, level, logger, quoted message and fields (the list `[0, 1]` is quoted because it contains spaces); a record below the level is dropped; an exception adds `exc=`; configuring twice does not duplicate lines. The shutdown tests check that the flag starts unset and is set by `request()`, and that after `install()` a real `SIGTERM` raised with `signal.raise_signal` sets it. The `previous` dictionary and the `finally` restore the old handlers so the test does not change the test runner's behavior.

```python
import random

import pytest

from rental_shop.infrastructure.retry import retry


class Flaky:
    def __init__(self, failures: int) -> None:
        self.failures, self.calls = failures, 0

    def __call__(self) -> str:
        self.calls += 1
        if self.calls <= self.failures:
            raise ConnectionError("down")
        return "ok"


def test_it_returns_the_first_success_without_sleeping():
    pauses: list[float] = []
    assert retry(Flaky(0), attempts=3, base_delay_seconds=1, retry_on=(ConnectionError,), sleep=pauses.append) == "ok"
    assert pauses == []


def test_it_retries_with_doubling_pauses_inside_the_jitter_band():
    pauses: list[float] = []
    operation = Flaky(3)
    result = retry(
        operation,
        attempts=5,
        base_delay_seconds=1,
        retry_on=(ConnectionError,),
        sleep=pauses.append,
        rng=random.Random(1),
    )
    assert result == "ok"
    assert operation.calls == 4
    for pause, ceiling in zip(pauses, (1, 2, 4), strict=True):
        assert ceiling * 0.5 <= pause <= ceiling


def test_the_pause_is_capped():
    pauses: list[float] = []
    retry(
        Flaky(4),
        attempts=6,
        base_delay_seconds=10,
        retry_on=(ConnectionError,),
        sleep=pauses.append,
        max_delay_seconds=15,
    )
    assert max(pauses) <= 15


def test_the_last_failure_is_raised_after_the_final_attempt():
    operation = Flaky(10)
    with pytest.raises(ConnectionError):
        retry(operation, attempts=3, base_delay_seconds=0, retry_on=(ConnectionError,), sleep=lambda _: None)
    assert operation.calls == 3


def test_other_errors_are_not_retried():
    def broken() -> str:
        raise KeyError("x")

    with pytest.raises(KeyError):
        retry(broken, attempts=3, base_delay_seconds=0, retry_on=(ConnectionError,), sleep=lambda _: None)


def test_each_retry_is_reported():
    seen: list[int] = []
    retry(
        Flaky(2),
        attempts=4,
        base_delay_seconds=0,
        retry_on=(ConnectionError,),
        sleep=lambda _: None,
        on_retry=lambda attempt, _: seen.append(attempt),
    )
    assert seen == [1, 2]


def test_at_least_one_attempt_is_required():
    with pytest.raises(ValueError, match="attempts"):
        retry(Flaky(0), attempts=0, base_delay_seconds=0, retry_on=(ConnectionError,))
```

`Flaky` is a callable class that fails a set number of times and then returns `"ok"`; it counts calls. The tests check: no sleep on first-time success; doubling pauses inside the jitter band (`rng=random.Random(1)`); the cap (`max(pauses) <= 15`); the last failure re-raised after the final attempt (exactly three calls); errors outside `retry_on` are not retried; each retry is reported through `on_retry`; zero attempts raise `ValueError`.

```python
import pytest

from rental_shop.infrastructure.settings import ConfigurationError, Settings

MINIMAL = {"POSTGRES_PASSWORD": "s3cret-value"}


def test_defaults_describe_the_local_compose_setup():
    settings = Settings.from_env(MINIMAL)
    postgres = settings.postgres
    assert (postgres.host, postgres.port, postgres.database, postgres.user) == ("localhost", 5441, "rentals", "shop")
    assert (postgres.schema, postgres.connect_timeout_seconds, postgres.statement_timeout_ms) == ("public", 5, 30_000)
    assert settings.log_level == "INFO"


def test_the_database_password_has_no_default():
    with pytest.raises(ConfigurationError, match="POSTGRES_PASSWORD"):
        Settings.from_env({})


def test_the_password_never_appears_in_a_printed_settings_object():
    assert "s3cret-value" not in repr(Settings.from_env(MINIMAL))


def test_every_variable_can_be_overridden():
    settings = Settings.from_env(
        {
            **MINIMAL,
            "POSTGRES_HOST": "db",
            "POSTGRES_PORT": "6543",
            "POSTGRES_DB": "x",
            "POSTGRES_USER": "u",
            "POSTGRES_SCHEMA": "lab_one",
            "POSTGRES_CONNECT_TIMEOUT_SECONDS": "2",
            "POSTGRES_STATEMENT_TIMEOUT_MS": "500",
            "LOG_LEVEL": "debug",
        }
    )
    postgres = settings.postgres
    assert (postgres.host, postgres.port, postgres.database, postgres.user) == ("db", 6543, "x", "u")
    assert (postgres.schema, postgres.connect_timeout_seconds, postgres.statement_timeout_ms) == ("lab_one", 2, 500)
    assert (postgres.password, settings.log_level) == ("s3cret-value", "DEBUG")


@pytest.mark.parametrize(
    "extra",
    [
        {"POSTGRES_PORT": "0"},
        {"POSTGRES_PORT": "five"},
        {"POSTGRES_HOST": "  "},
        {"POSTGRES_SCHEMA": "public; DROP TABLE rentals"},
        {"POSTGRES_SCHEMA": "Upper"},
        {"POSTGRES_STATEMENT_TIMEOUT_MS": "-1"},
        {"LOG_LEVEL": "LOUD"},
    ],
)
def test_an_unusable_value_is_rejected_with_the_variable_name(extra):
    with pytest.raises(ConfigurationError, match=next(iter(extra))):
        Settings.from_env({**MINIMAL, **extra})


def test_settings_read_the_process_environment_by_default(monkeypatch):
    monkeypatch.setenv("POSTGRES_PASSWORD", "from-the-process")
    assert Settings.from_env().postgres.password == "from-the-process"
```

`MINIMAL` holds the only required variable. The tests check the defaults, that the password has no default, that it never appears in `repr`, and that every variable can be overridden (`{**MINIMAL, ...}` merges dictionaries; the lower-case `"debug"` becomes `"DEBUG"`). The parametrized test feeds seven unusable values and checks that the error names the variable (`match=next(iter(extra))` takes the first key of the dictionary). `monkeypatch` is a built-in fixture that changes the real environment for one test and undoes it afterwards.

### Interface tests

```python
from datetime import date

from rental_shop.application.shop_questions import ShopQuestions
from rental_shop.domain.period import RentalPeriod
from rental_shop.interfaces.book_cli import build_parser as book_parser
from rental_shop.interfaces.race_cli import build_parser as race_parser
from rental_shop.interfaces.report_cli import build_parser as report_parser
from rental_shop.interfaces.report_cli import format_report

from ..application.fakes import FixedClock, lesson_shop


def test_the_report_prints_the_lessons_expected_output():
    report = ShopQuestions(lesson_shop(), FixedClock(date(2026, 11, 4))).report(
        RentalPeriod(date(2026, 11, 7), date(2026, 11, 9)), "Ada"
    )
    assert format_report(report) == [
        "free next weekend: Drill, Kayak",
        "Ada's history: 1, 3, 5 and 6",
        "returns on 2026-11-04: rental 1 (Drill, Ada)",
        "revenue per item and month: Drill 2026-11 50.00 | Drill 2026-12 20.00 | Ladder 2026-10 24.00 | "
        "Ladder 2026-11 56.00 | Tent 2026-10 45.00 | Tent 2026-11 45.00",
        "never rented: Kayak",
    ]


def test_an_empty_answer_reads_as_none():
    shop = lesson_shop()
    shop.rentals.clear()
    report = ShopQuestions(shop, FixedClock(date(2026, 11, 4))).report(
        RentalPeriod(date(2026, 11, 7), date(2026, 11, 9)), "Ada"
    )
    lines = format_report(report)
    assert lines[1] == "Ada's history: none"
    assert lines[2] == "returns on 2026-11-04: (none)"


def test_the_report_defaults_are_the_lessons_hand_checked_inputs():
    arguments = report_parser().parse_args([])
    assert (arguments.today, arguments.weekend_from, arguments.weekend_to, arguments.customer) == (
        date(2026, 11, 4),
        date(2026, 11, 7),
        date(2026, 11, 9),
        "Ada",
    )


def test_the_book_program_needs_an_item_a_customer_a_date_and_a_length():
    arguments = book_parser().parse_args(["--item", "1", "--customer", "2", "--from", "2026-11-03", "--days", "2"])
    assert (arguments.item, arguments.customer, arguments.first_day, arguments.days) == (1, 2, date(2026, 11, 3), 2)


def test_the_race_defaults_to_twenty_runs_of_twenty_connections():
    arguments = race_parser().parse_args([])
    assert (arguments.runs, arguments.contenders) == (20, 20)
```

The report text is compared line by line with the lesson's expected output, and an empty answer reads `none` or `(none)`. The parser tests call `build_parser().parse_args([...])` with explicit lists and check the defaults and parsed values (see [argparse.md](argparse.md)).

### Integration tests

```python
"""The PostgreSQL adapter and the schema's own rules, against the real database (make up first)."""

import threading
from datetime import date
from decimal import Decimal
from typing import Any

import psycopg
import pytest
from psycopg import errors
from psycopg.types.range import Range

from rental_shop.application.book_item import BookItem
from rental_shop.application.health import ProbeFailedError
from rental_shop.application.race import Race
from rental_shop.application.shop_questions import ShopQuestions
from rental_shop.domain.errors import ItemAlreadyBookedError, UnknownCustomerError, UnknownItemError
from rental_shop.domain.period import RentalPeriod
from rental_shop.infrastructure import postgres
from rental_shop.infrastructure.clock import SystemClock
from rental_shop.infrastructure.health_probes import PostgresSchemaProbe
from rental_shop.infrastructure.postgres_rentals import (
    INSERT_RENTAL,
    INSERT_RENTAL_SKIPPING_CLASH,
    InsertMode,
    PostgresRentals,
    gateway_opener,
)
from rental_shop.infrastructure.settings import PostgresSettings

from ..conftest import SQL

pytestmark = pytest.mark.integration


def period(first_day: str, return_day: str) -> RentalPeriod:
    return RentalPeriod(date.fromisoformat(first_day), date.fromisoformat(return_day))


@pytest.fixture
def rentals(connection: psycopg.Connection[Any]) -> PostgresRentals:
    return PostgresRentals(connection)

```

`pytestmark = pytest.mark.integration` marks every test in the file. `from ..conftest import SQL` imports a name from the shared module. The `rentals` fixture wraps the lab connection in the adapter.

```python
def test_an_overlapping_rental_is_refused_by_the_database_with_the_exclusion_sqlstate(
    connection: psycopg.Connection[Any],
):
    with pytest.raises(errors.ExclusionViolation) as raised:
        connection.execute(
            "INSERT INTO rentals (item_id, customer_id, during) VALUES (1, 2, daterange('2026-11-03', '2026-11-05'))"
        )
    assert raised.value.sqlstate == "23P01"
    assert raised.value.diag.constraint_name == "rentals_item_id_during_excl"


@pytest.mark.parametrize("mode", list(InsertMode))
def test_the_adapter_turns_a_clash_into_already_booked_in_both_insert_modes(
    connection: psycopg.Connection[Any], mode: InsertMode
):
    with pytest.raises(ItemAlreadyBookedError, match="item 1 is already booked"):
        PostgresRentals(connection, mode).book(1, 2, period("2026-11-03", "2026-11-05"))


@pytest.mark.parametrize("mode", list(InsertMode))
def test_a_clash_with_the_plain_insert_raises_23p01_and_with_on_conflict_returns_no_row(
    connection: psycopg.Connection[Any], mode: InsertMode
):
    statement = INSERT_RENTAL if mode is InsertMode.RAISE else INSERT_RENTAL_SKIPPING_CLASH
    values = (1, 2, Range(date(2026, 11, 3), date(2026, 11, 5), "[)"))
    if mode is InsertMode.RAISE:
        with pytest.raises(errors.ExclusionViolation):
            connection.execute(statement, values)
    else:
        assert connection.execute(statement, values).fetchone() is None


def test_a_rental_that_starts_on_the_return_day_is_accepted(rentals: PostgresRentals):
    rental = rentals.book(1, 2, period("2026-11-06", "2026-11-08"))
    assert rental.period == period("2026-11-06", "2026-11-08")
    assert rental.rental_id > 7


def test_the_same_dates_for_another_item_are_accepted(rentals: PostgresRentals):
    assert rentals.book(4, 1, period("2026-11-01", "2026-11-04")).item_id == 4


def test_a_refused_rental_leaves_nothing_behind(connection: psycopg.Connection[Any], rentals: PostgresRentals):
    with pytest.raises(ItemAlreadyBookedError):
        rentals.book(1, 2, period("2026-11-03", "2026-11-05"))
    assert connection.execute("SELECT count(*) FROM rentals").fetchone() == (7,)


def test_unknown_references_are_named(rentals: PostgresRentals):
    with pytest.raises(UnknownItemError):
        rentals.book(99, 1, period("2027-01-01", "2027-01-02"))
    with pytest.raises(UnknownCustomerError):
        rentals.book(4, 99, period("2027-01-01", "2027-01-02"))


def test_an_empty_range_violates_the_check(connection: psycopg.Connection[Any]):
    with pytest.raises(errors.CheckViolation):
        connection.execute("INSERT INTO rentals (item_id, customer_id, during) VALUES (4, 1, 'empty')")


def test_postgres_stores_a_closed_range_as_half_open(connection: psycopg.Connection[Any]):
    row = connection.execute("SELECT '[2026-11-01,2026-11-04]'::daterange::text").fetchone()
    assert row == ("[2026-11-01,2026-11-05)",)


def test_a_closed_range_makes_a_touching_rental_clash(connection: psycopg.Connection[Any]):
    connection.execute("INSERT INTO rentals (item_id, customer_id, during) VALUES (4, 1, '[2026-11-01,2026-11-04]')")
    with pytest.raises(errors.ExclusionViolation):
        connection.execute(
            "INSERT INTO rentals (item_id, customer_id, during) VALUES (4, 2, daterange('2026-11-04', '2026-11-06'))"
        )

```

Raw SQL checks that the database itself refuses an overlap: the error has SQLSTATE `23P01` and names `rentals_item_id_during_excl`. The adapter test is parametrized over `list(InsertMode)`, so both insert modes are tested. One test checks the plain insert raises and the `ON CONFLICT` form returns no row. Others check the allowed and refused bookings, that a refused rental leaves nothing behind (`count(*) == (7,)`), named unknown references, the empty-range check (`errors.CheckViolation`), the half-open storage of a closed range (`'[2026-11-01,2026-11-04]'::daterange::text` is `[2026-11-01,2026-11-05)`) and the clash that follows.

```python
def test_the_five_questions_have_the_hand_checked_answers(rentals: PostgresRentals):
    report = ShopQuestions(rentals, SystemClock()).report(period("2026-11-07", "2026-11-09"), "Ada", date(2026, 11, 4))
    assert [item.name for item in report.free_items] == ["Drill", "Kayak"]
    assert sorted(rental.rental_id for rental in report.history) == [1, 3, 5, 6]
    assert [(due.rental_id, due.item_name, due.customer_name) for due in report.returns_today] == [(1, "Drill", "Ada")]
    assert [(row.item_name, row.month, row.amount) for row in report.revenue] == [
        ("Drill", "2026-11", Decimal("50.00")),
        ("Drill", "2026-12", Decimal("20.00")),
        ("Ladder", "2026-10", Decimal("24.00")),
        ("Ladder", "2026-11", Decimal("56.00")),
        ("Tent", "2026-10", Decimal("45.00")),
        ("Tent", "2026-11", Decimal("45.00")),
    ]
    assert [item.name for item in report.never_rented] == ["Kayak"]


def test_one_item_can_be_asked_about_alone(rentals: PostgresRentals):
    weekend = period("2026-11-07", "2026-11-09")
    assert not rentals.is_item_free(2, weekend)
    assert rentals.is_item_free(1, weekend)


def test_a_customer_is_found_by_name_only_when_there_is_exactly_one(rentals: PostgresRentals):
    assert rentals.find_customer("Ada") is not None
    assert rentals.find_customer("Nobody") is None
    rentals.add_customer("Ada")
    assert rentals.find_customer("Ada") is None


def test_items_and_customers_can_be_added_with_generated_ids(rentals: PostgresRentals):
    assert rentals.add_item("Saw", Decimal("7.50")).item_id == 5
    assert rentals.add_customer("Cleo").customer_id == 3


def test_the_script_of_queries_runs_as_written(connection: psycopg.Connection[Any]):
    connection.execute((SQL / "003_queries.sql").read_text())


def test_the_document_design_accepts_the_double_booking_the_relational_design_refuses(
    connection: psycopg.Connection[Any],
):
    connection.execute((SQL / "document_model" / "001_documents.sql").read_text())
    connection.execute((SQL / "document_model" / "002_double_booking.sql").read_text())
    booked = connection.execute(
        "SELECT jsonb_array_length(doc->'booked') FROM item_documents WHERE item_id = 1"
    ).fetchone()
    assert booked == (2,)

```

The five questions with the hand-checked answers; `is_item_free`; `find_customer` returning `None` for zero or two matches; generated ids for new rows (5 and 3 after the seed's 4 items and 2 customers); the script `003_queries.sql` running as written; and the document design accepting the double booking the tables refuse (`booked == (2,)`: two entries in the array).

```python
def test_every_statement_is_bounded_by_the_statement_timeout(lab: PostgresSettings):
    import dataclasses

    impatient = dataclasses.replace(lab, statement_timeout_ms=100)
    with postgres.session(impatient) as connection, pytest.raises(errors.QueryCanceled):
        connection.execute("SELECT pg_sleep(2)")


def test_a_connection_to_nowhere_gives_up_after_its_retries(lab: PostgresSettings):
    import dataclasses

    unreachable = dataclasses.replace(lab, port=1, connect_timeout_seconds=1)
    with pytest.raises(psycopg.OperationalError):
        postgres.connect(unreachable, attempts=2)


def test_the_health_probe_passes_on_the_lab_schema(lab: PostgresSettings):
    assert "exclusion constraint" in PostgresSchemaProbe(lab).check()


def test_the_health_probe_names_what_is_missing(lab: PostgresSettings, connection: psycopg.Connection[Any]):
    connection.execute("ALTER TABLE rentals DROP CONSTRAINT rentals_item_id_during_excl")
    with pytest.raises(ProbeFailedError, match="exclusion constraint"):
        PostgresSchemaProbe(lab).check()
    connection.execute("DROP TABLE rentals")
    with pytest.raises(ProbeFailedError, match="missing tables"):
        PostgresSchemaProbe(lab).check()

```

The statement timeout is tested with `pg_sleep(2)` under a 100 ms limit, expecting `errors.QueryCanceled`. `with a as x, pytest.raises(...)` opens two context managers in one line. A connection to port 1 must fail with `OperationalError` after its retries. The health probe passes on the lab and names what is missing when the constraint or the table is dropped.

```python
def test_twenty_connections_racing_for_the_same_item_give_exactly_one_winner_and_nineteen_refusals(
    lab: PostgresSettings,
):
    race = Race(gateway_opener(lab), contenders=20)
    tallies = [race.run_round(str(run)) for run in range(3)]
    assert all(tally.is_correct for tally in tallies), tallies


def test_with_a_plain_insert_one_contender_still_wins_whatever_happens_to_the_others(lab: PostgresSettings):
    race = Race(gateway_opener(lab, InsertMode.RAISE), contenders=20)
    tallies = [race.run_round(str(run)) for run in range(3)]
    assert all(tally.one_winner and tally.failed == 0 for tally in tallies), tallies


def test_two_sessions_booking_the_same_dates_at_once_never_both_win(lab: PostgresSettings):
    barrier = threading.Barrier(2)
    results: list[str] = []

    def contend(customer_id: int) -> None:
        with gateway_opener(lab)() as session:
            barrier.wait()
            try:
                BookItem(session)(4, customer_id, date(2027, 3, 1), 3)
                results.append("won")
            except ItemAlreadyBookedError:
                results.append("refused")

    threads = [threading.Thread(target=contend, args=(customer,)) for customer in (1, 2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(results) == ["refused", "won"]
```

The real races: three rounds of twenty contenders must each be correct; with the plain insert, each round must still have exactly one winner and no failures. The last test uses two threads and a `Barrier(2)` to prove that two sessions booking the same dates at once never both win: `sorted(results) == ["refused", "won"]`.

### End-to-end tests

```python
"""The lesson's scenario through the command-line programs, as the Makefile runs them (make up first)."""

import os
import re
import subprocess
import sys

import pytest

from rental_shop.infrastructure.settings import PostgresSettings

pytestmark = pytest.mark.e2e


def program(module: str, lab: PostgresSettings, *args: str) -> subprocess.CompletedProcess[str]:
    environment = {**os.environ, "POSTGRES_SCHEMA": lab.schema}
    return subprocess.run(
        [sys.executable, "-m", f"rental_shop.interfaces.{module}", *args],
        capture_output=True,
        text=True,
        env=environment,
        timeout=300,
        check=False,
    )

```

`subprocess.run` starts a separate program and waits for it. `sys.executable` is the Python that runs the tests; `-m rental_shop.interfaces.<module>` runs a program module; `*args` adds the arguments. `capture_output=True, text=True` collects standard output and error as text; `env=` sets the environment (the real one plus the test's schema); `timeout=300` kills a stuck program; `check=False` returns the exit code instead of raising.

```python
def test_the_report_prints_the_lessons_expected_answers(lab: PostgresSettings):
    result = program("report_cli", lab)
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        "free next weekend: Drill, Kayak",
        "Ada's history: 1, 3, 5 and 6",
        "returns on 2026-11-04: rental 1 (Drill, Ada)",
        "revenue per item and month: Drill 2026-11 50.00 | Drill 2026-12 20.00 | Ladder 2026-10 24.00 | "
        "Ladder 2026-11 56.00 | Tent 2026-10 45.00 | Tent 2026-11 45.00",
        "never rented: Kayak",
    ]


def test_an_overlap_is_refused_a_touching_range_is_booked_and_the_exit_codes_say_so(lab: PostgresSettings):
    refused = program("book_cli", lab, "--item", "1", "--customer", "2", "--from", "2026-11-03", "--days", "2")
    assert refused.returncode == 3
    assert "already booked" in refused.stdout

    touching = program("book_cli", lab, "--item", "1", "--customer", "2", "--from", "2026-11-06", "--days", "2")
    assert touching.returncode == 0, touching.stderr
    # the refused insert used up a number from the identity sequence, so the new rental is 9, not 8
    assert re.fullmatch(r"booked rental (8|9): item 1 for 2026-11-06 to 2026-11-08\n", touching.stdout)

    nonsense = program("book_cli", lab, "--item", "1", "--customer", "2", "--from", "2026-11-06", "--days", "0")
    assert nonsense.returncode == 2


def test_twenty_races_of_twenty_connections_each_have_exactly_one_winner(lab: PostgresSettings):
    result = program("race_cli", lab, "--runs", "20")
    assert result.returncode == 0, result.stderr + result.stdout
    lines = [line for line in result.stdout.splitlines() if line.startswith("run ")]
    assert len(lines) == 20
    assert all(
        line == f"run {number:2d}: 1 success, 19 refused by the exclusion constraint"
        for number, line in enumerate(lines, 1)
    )
    assert "20 of 20 runs had exactly one winner" in result.stdout


def test_the_plain_insert_race_also_has_one_winner_each_time_whatever_happens_to_the_others(lab: PostgresSettings):
    result = program("race_cli", lab, "--runs", "5", "--insert", "raise")
    assert result.returncode == 0, result.stderr + result.stdout
    lines = [line for line in result.stdout.splitlines() if line.startswith("run ")]
    assert len(lines) == 5
    assert all(": 1 success, " in line for line in lines)
    assert "5 of 5 runs had exactly one winner" in result.stdout


def test_the_health_command_is_green_on_the_lab_and_red_without_a_password(lab: PostgresSettings):
    assert program("health_cli", lab).returncode == 0
    broken = subprocess.run(
        [sys.executable, "-m", "rental_shop.interfaces.health_cli"],
        capture_output=True,
        text=True,
        env={key: value for key, value in os.environ.items() if key != "POSTGRES_PASSWORD"},
        timeout=60,
        check=False,
    )
    assert broken.returncode == 2
    assert "POSTGRES_PASSWORD" in broken.stderr
```

The report's standard output must equal the lesson's five lines. The book program must exit 3 with "already booked" for an overlap, 0 for a touching rental (the regular expression `booked rental (8|9)` accepts either id because a refused insert uses up one number from the identity sequence), and 2 for zero days. The race program must print twenty lines `run N: 1 success, 19 refused by the exclusion constraint` and exit 0. The plain-insert race must have one winner each time. The health program exits 0 on the lab and 2 when the password variable is removed from its environment.

## Try it yourself

```bash
make test
```
Runs the unit tests with coverage. Expect `73 passed` and a coverage table with the domain and application at 95% or more.

```bash
.venv/bin/python -m pytest tests/unit/domain -q -k overlap
```
`-k` selects tests whose names contain a word. Expect the overlap tests only.

```bash
.venv/bin/python -m pytest tests/unit/application/test_book_item.py -q -x --tb=short
```
`-x` stops at the first failure; `--tb=short` shortens tracebacks.

```bash
make up && make test-integration test-e2e
```
Needs Docker. Expect `25 passed` and `5 passed`. Each test uses its own schema.

```bash
.venv/bin/python -m pytest --collect-only -q | tail -3
```
Lists what would run, with the total count.

## Mistakes people make

- **Tests that share data**, so order matters. A schema per test removes it.
- **Using the real database for rules that fakes can check.** The unit layer needs no PostgreSQL.
- **Real clocks and random numbers in tests**, which make runs unrepeatable. Fakes and a seed replace them.
- **A broad `pytest.raises(Exception)`.** Each test names the error and message.
- **Forgetting clean-up.** `yield` fixtures with `finally`.
- **Unregistered markers.** `--strict-markers` catches them.

## Check yourself

1. How does pytest find tests? *Files `test_*.py`, functions `test_*`.*
2. What is a fixture and how is it requested? *A set-up function; a test asks for it by a parameter with the same name.*
3. Why does `lab` drop its schema in `finally`? *So it is removed even if the test failed.*
4. What does `parametrize` do? *Runs the same test for each row of data.*
5. What separates unit, integration and e2e tests here? *Fakes only; a real database through the adapter; whole programs as subprocesses.*

## Further reading

- pytest documentation (stable docs; locked at 9.1.1): https://docs.pytest.org/en/stable/
- Fixtures: https://docs.pytest.org/en/stable/how-to/fixtures.html
- Parametrize: https://docs.pytest.org/en/stable/how-to/parametrize.html
- Markers: https://docs.pytest.org/en/stable/how-to/mark.html
