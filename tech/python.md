# Python 3.13

## What it is

Python is a programming language: you write instructions as text in files ending in `.py`, and a program called the **interpreter** reads and carries them out one statement at a time. This repository is pinned to Python 3.13.1 in its Dockerfile and works on 3.12 or newer (`requires-python = ">=3.12"`). A **module** is one `.py` file. A **package** is a folder of modules with an `__init__.py` file in it. Code in one module uses another with `import`.

## Why this repository uses it

The lesson's SQL does the real work; Python is the thin application around it. It books rentals, races 20 connections for one item, prints the five answers and checks health. The code is arranged in four layers so the rules about rentals stay separate from the database driver. This file covers the two inner layers, `domain` and `application`; the outer ones have their own files.

## Where it appears

| Path | What it holds |
|---|---|
| `src/rental_shop/__init__.py` | The package marker and its version. |
| `src/rental_shop/domain/` | `errors.py`, `period.py`, `model.py`: the shop's vocabulary. Standard library only. |
| `src/rental_shop/application/` | `ports.py`, `book_item.py`, `race.py`, `shop_questions.py`, `health.py`: the use cases. |
| `src/rental_shop/infrastructure/`, `interfaces/` | Adapters and command-line programs; see [psycopg.md](psycopg.md), [python-stdlib.md](python-stdlib.md), [python-logging.md](python-logging.md), [argparse.md](argparse.md). |
| `tests/` | See [pytest.md](pytest.md). |

## How it works underneath

When you run `python -m rental_shop.interfaces.book_cli`, the interpreter finds the module on its **import path**, compiles it to **bytecode** (a compact internal form) and runs it. Everything is an **object** (a value with attributes and methods): numbers, text, functions, classes. A **variable** is a name pointing at an object. **Indentation** (four spaces) marks which lines belong to a block; there are no braces.

A **type hint** (`x: int`) says what kind of value is expected. Python does not enforce hints when running; a separate tool, mypy, checks them (see [mypy.md](mypy.md)). A **class** is a blueprint for objects; `class B(A)` makes B inherit what A has. An **exception** is an object that is "raised" to signal an error and travels up the call stack until a `try/except` catches it, or the program stops. A **context manager** is an object used with `with`; it does set-up on entry and clean-up on exit, even when an error happens.

The layers in this package may only import downward: `interfaces` can use `infrastructure`, which can use `application`, which can use `domain`. `domain` imports nothing from the project's other layers. [import-linter.md](import-linter.md) enforces it.

## Walkthrough of this repository's use

### The package marker

```python
"""The data layer of an equipment-rental shop: a relational model where the database refuses a double booking."""

__version__ = "0.1.0"
```

A string literal as the first statement of a file is the **docstring** of the module: documentation that tools and `help()` can read. `__version__ = "0.1.0"` is a plain variable by convention.

```python
"""Domain: rental periods, the shop's entities and their named errors. Depends on the standard library only."""
```

```python
"""Application: use cases and the ports they need. Depends on the domain only."""
```

The `__init__.py` files make each folder a package, and their docstrings state what the layer may depend on.

### `domain/errors.py`: named errors

```python
"""Named errors of the domain."""

from __future__ import annotations


class RentalShopError(Exception):
    """Base class for every error the shop's rules raise."""


class InvalidPeriodError(RentalShopError, ValueError):
    """A rental period is empty, reversed or otherwise unusable."""


class ItemAlreadyBookedError(RentalShopError):
    """The item is already rented for dates that overlap the request (SQLSTATE 23P01 in PostgreSQL)."""

    def __init__(self, item_id: int, first_day: str, return_day: str) -> None:
        super().__init__(f"item {item_id} is already booked for dates overlapping {first_day} to {return_day}")
        self.item_id = item_id

```

- `from __future__ import annotations` changes how type hints are stored: as text, evaluated only when needed. The effect is that a hint may name a class that is defined later or is being defined (such as a method returning its own class). It is placed in nearly every module here.
- `class RentalShopError(Exception):` defines a new error type that **inherits** from the built-in `Exception`. Its body is only a docstring, which is a legal body. All the shop's errors derive from it, so code can catch "any shop error" with one `except`.
- `class InvalidPeriodError(RentalShopError, ValueError)` inherits from two classes. It can be caught as a shop error or as the standard `ValueError`.
- `ItemAlreadyBookedError` defines `__init__`, the **constructor**: the method that runs when an object is created. `self` is the object being built. `item_id: int, first_day: str, return_day: str` are the parameters with hints and `-> None` says it returns nothing. `super().__init__(...)` calls the parent class's constructor with the message; the `f"..."` is an **f-string**: text in which `{name}` is replaced by the value of the expression. `self.item_id = item_id` stores the id on the object so a handler can read it.

```python
class UnknownItemError(RentalShopError):
    """No item has this id."""

    def __init__(self, item_id: int) -> None:
        super().__init__(f"unknown item {item_id}")
        self.item_id = item_id


class UnknownCustomerError(RentalShopError):
    """No customer has this id."""

    def __init__(self, customer_id: int) -> None:
        super().__init__(f"unknown customer {customer_id}")
        self.customer_id = customer_id


class BookingDeadlockError(RentalShopError):
    """The database picked this booking as a deadlock victim (SQLSTATE 40P01); nothing was written, so a retry is safe.

    Two inserts for overlapping dates each wait for the other's uncommitted row while checking the exclusion
    constraint. PostgreSQL ends one of them after `deadlock_timeout`; the retry then meets the winner's committed row.
    """
```

The three remaining errors follow the same pattern. `UnknownItemError` and `UnknownCustomerError` carry the missing id. `BookingDeadlockError` has no constructor: a docstring is its only body. Its docstring records the meaning (see [postgresql.md](postgresql.md)): SQLSTATE `40P01` is PostgreSQL's code for "chosen as the victim of a deadlock", where nothing was written so a retry is safe.

### `domain/period.py`: the half-open period

```python
"""The half-open rental period: the first rental day up to, not including, the day the item comes back."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from .errors import InvalidPeriodError


@dataclass(frozen=True, slots=True, order=True)
class RentalPeriod:
    """Dates `[first_day, return_day)`. The return day is free again, so back-to-back rentals touch without clashing."""

    first_day: date
    return_day: date
```

- `from dataclasses import dataclass` and `from datetime import date, timedelta` import names from the standard library: `date` is a calendar date, `timedelta` a length of time. `from .errors import InvalidPeriodError` is a **relative import**: the leading dot means "the same package as this file".
- `@dataclass(frozen=True, slots=True, order=True)` is a **decorator**: a line starting with `@` that wraps the class that follows. `dataclass` writes the boring methods from the field list below it: `__init__`, `__repr__` (the text shown when printing the object) and `__eq__` (equality by fields). The options: `frozen=True` makes instances immutable (assigning to a field raises an error), `slots=True` stores the fields in a fixed layout, saving memory and refusing stray attributes, and `order=True` adds `<`, `<=`, `>` and `>=` that compare the fields in order, first day first.
- `first_day: date` and `return_day: date` are the **fields**: annotated names in the class body.

```python
    def __post_init__(self) -> None:
        if self.return_day <= self.first_day:
            raise InvalidPeriodError(f"the return day {self.return_day} must be after the first day {self.first_day}")

    @classmethod
    def starting(cls, first_day: date, days: int) -> RentalPeriod:
        """A period of `days` rental days beginning on `first_day`."""
        if days < 1:
            raise InvalidPeriodError(f"a rental lasts at least one day, got {days}")
        return cls(first_day, first_day + timedelta(days=days))
```

- `__post_init__` is a hook that a dataclass calls right after the generated `__init__`. It validates: a period must end after it begins, otherwise it raises `InvalidPeriodError` with an f-string message. So an invalid `RentalPeriod` can never exist.
- `@classmethod` makes `starting` a method that receives the class (`cls`) instead of an object. `RentalPeriod.starting(first_day, 3)` is a named constructor: it checks `days < 1`, and builds `cls(first_day, first_day + timedelta(days=days))`. Adding a `timedelta` to a `date` gives a later date.

```python
    @property
    def days(self) -> int:
        """Number of rental days: the return day itself is not one."""
        return (self.return_day - self.first_day).days

    def overlaps(self, other: RentalPeriod) -> bool:
        """True when some day belongs to both periods. Periods that only touch do not overlap."""
        return self.first_day < other.return_day and other.first_day < self.return_day

    def shifted(self, days: int) -> RentalPeriod:
        """The same length, moved by `days` (negative moves it earlier)."""
        offset = timedelta(days=days)
        return RentalPeriod(self.first_day + offset, self.return_day + offset)

    def __str__(self) -> str:
        return f"{self.first_day.isoformat()} to {self.return_day.isoformat()}"
```

- `@property` makes `days` readable as `period.days` without parentheses. `(a - b).days` subtracts two dates to get a `timedelta` and reads its `days` attribute.
- `overlaps` implements the same rule PostgreSQL's `&&` operator applies: the periods share a day exactly when each starts before the other ends. Because the end is excluded, `[1st, 4th)` and `[4th, 6th)` do not overlap.
- `shifted` returns a new period moved by `days`; because the object is frozen, a change is always a new object.
- `__str__` is the method `str(period)` calls; `isoformat()` gives `2026-11-01`.

### `domain/model.py`: entities

```python
"""Immutable entities and report rows of the rental shop."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from .period import RentalPeriod


@dataclass(frozen=True, slots=True)
class Customer:
    """Someone who rents."""

    customer_id: int
    name: str


@dataclass(frozen=True, slots=True)
class Item:
    """Something for rent, with a price per rental day."""

    item_id: int
    name: str
    daily_rate: Decimal


@dataclass(frozen=True, slots=True)
class Rental:
    """One item rented by one customer for a period."""

    rental_id: int
    item_id: int
    customer_id: int
    period: RentalPeriod

```

- `Decimal` (from the `decimal` module) is an exact decimal number, used for money because `0.1 + 0.2` on ordinary floating-point numbers is not exactly `0.3`.
- Each class is a frozen dataclass with annotated fields: `Customer(customer_id, name)`, `Item(item_id, name, daily_rate)` and `Rental(rental_id, item_id, customer_id, period)`. The `period` field's type is the class from `period.py`.

```python
@dataclass(frozen=True, slots=True)
class ReturnDue:
    """A rental whose return day has come, with the names a counter clerk needs."""

    rental_id: int
    item_name: str
    customer_name: str


@dataclass(frozen=True, slots=True)
class MonthlyRevenue:
    """Revenue of one item for the rentals that start in one month."""

    item_name: str
    month: str
    amount: Decimal

    @classmethod
    def of(cls, item_name: str, first_day: date, amount: Decimal) -> MonthlyRevenue:
        """Build a row, naming the month as `YYYY-MM`."""
        return cls(item_name, first_day.strftime("%Y-%m"), amount)

```

- `ReturnDue` is a read model: the names a counter clerk needs.
- `MonthlyRevenue.of(...)` is a class method that builds a row: `first_day.strftime("%Y-%m")` formats a date with the pattern year-month. The return type `MonthlyRevenue` names the class being defined, which works because of `from __future__ import annotations`.

```python
@dataclass(frozen=True, slots=True)
class RaceTally:
    """The outcome of one race: how many requests for overlapping dates won, were refused, or failed otherwise.

    `deadlocked` counts contenders that gave up after every retry was a deadlock victim; `failed` counts any
    other error.
    """

    contenders: int
    successes: int
    refused: int
    failed: int
    deadlocked: int = 0
    deadlock_retries: int = 0

    @property
    def one_winner(self) -> bool:
        """The safety property: exactly one contender got the item, whatever happened to the others."""
        return self.successes == 1

    @property
    def is_correct(self) -> bool:
        """Exactly one winner, everyone else refused by the database, nothing else went wrong."""
        return self.one_winner and self.refused == self.contenders - 1 and self.failed == 0 and self.deadlocked == 0
```

`RaceTally` records one race. The fields after `failed` have **default values** (`= 0`), and in a dataclass fields with defaults must come last. The two `@property` methods compute answers from the fields: `one_winner` is "exactly one success"; `is_correct` is "one winner, everyone else refused, nothing failed and no contender gave up after deadlocks". `and` is true only if all conditions are.

### `application/ports.py`: what the use cases need

```python
"""Ports: what the use cases need from the outside world. Adapters in `infrastructure` implement them."""

from __future__ import annotations

from contextlib import AbstractContextManager
from datetime import date
from decimal import Decimal
from typing import Protocol

from ..domain.model import Customer, Item, MonthlyRevenue, Rental, ReturnDue
from ..domain.period import RentalPeriod

```

`Protocol` (from `typing`) defines an interface by shape. Any class with matching methods satisfies it without inheriting from it, which is called **structural typing**. `AbstractContextManager` is the type of an object usable in a `with` statement. The imports reach the domain only.

```python
class RentalBooking(Protocol):
    """Writes: the one operation that needs a rule, booking, and the catalog setup around it."""

    def book(self, item_id: int, customer_id: int, period: RentalPeriod) -> Rental:
        """Insert a rental. Raises `ItemAlreadyBookedError` when the dates overlap an existing rental of the item,
        `UnknownItemError` or `UnknownCustomerError` when a referenced row is missing."""
        ...

    def add_item(self, name: str, daily_rate: Decimal) -> Item:
        """Create an item."""
        ...

    def add_customer(self, name: str) -> Customer:
        """Create a customer."""
        ...

```

`RentalBooking` lists the write operations. The body of each method is a docstring and `...` (the **Ellipsis**, a placeholder that means "no code here"): a protocol declares signatures only. `book(...)` takes ids and a `RentalPeriod` and returns a `Rental`.

```python
class RentalQueries(Protocol):
    """Reads: the shop's five questions."""

    def is_item_free(self, item_id: int, period: RentalPeriod) -> bool:
        """True when no rental of the item overlaps the period."""
        ...

    def free_items(self, period: RentalPeriod) -> list[Item]:
        """Items with no rental that overlaps the period, by id."""
        ...

    def history(self, customer_id: int) -> list[Rental]:
        """A customer's rentals, oldest first."""
        ...

    def returns_on(self, day: date) -> list[ReturnDue]:
        """Rentals whose return day is `day`."""
        ...

    def revenue_by_item_and_month(self) -> list[MonthlyRevenue]:
        """Revenue per item and start month, by item name then month."""
        ...

    def never_rented(self) -> list[Item]:
        """Items that no rental refers to."""
        ...

    def find_customer(self, name: str) -> Customer | None:
        """The customer with this name, if there is exactly one."""
        ...
```

`RentalQueries` has one method per shop question. `list[Item]` is a **generic** type: a list whose items are `Item`. `Customer | None` is a **union**: either a `Customer` or `None` (the absence of a value).

```python
class RentalGateway(RentalBooking, RentalQueries, Protocol):
    """Everything a session with the rental database can do."""


class GatewayOpener(Protocol):
    """Opens a new, independent session (a new connection) and closes it when the block ends."""

    def __call__(self) -> AbstractContextManager[RentalGateway]: ...


class Clock(Protocol):
    """Today's date, injected so tests are deterministic."""

    def today(self) -> date: ...


class HealthProbe(Protocol):
    """One dependency check."""

    name: str

    def check(self) -> str:
        """Return a short description when usable; raise `ProbeFailedError` otherwise."""
        ...
```

- `RentalGateway(RentalBooking, RentalQueries, Protocol)` combines two protocols into one.
- `GatewayOpener` describes something you call with no arguments to get a context manager yielding a gateway; the `def __call__(self) -> ...: ...` is written on one line.
- `Clock` returns today's date; it is injected so tests can fix the date.
- `HealthProbe` has an attribute `name: str` and a `check` method.

### `application/health.py`

```python
"""Use case: ask every dependency whether it is usable."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from .ports import HealthProbe


class ProbeFailedError(Exception):
    """A dependency is not usable; the message says why."""


@dataclass(frozen=True, slots=True)
class ProbeResult:
    """The outcome of one health probe."""

    name: str
    ok: bool
    detail: str


@dataclass(frozen=True, slots=True)
class HealthReport:
    """The outcomes of every probe; healthy only when all of them are."""

    results: tuple[ProbeResult, ...]

    @property
    def healthy(self) -> bool:
        return all(result.ok for result in self.results)


def check_health(probes: Iterable[HealthProbe]) -> HealthReport:
    """Run every probe and collect the outcomes; a failed probe is reported, not raised."""
    results = []
    for probe in probes:
        try:
            results.append(ProbeResult(probe.name, True, probe.check()))
        except ProbeFailedError as error:
            results.append(ProbeResult(probe.name, False, str(error)))
    return HealthReport(tuple(results))
```

- `ProbeFailedError` is a plain `Exception` subclass.
- `ProbeResult` and `HealthReport` are frozen dataclasses. `tuple[ProbeResult, ...]` means a tuple of any length with items of that type.
- `healthy` uses `all(result.ok for result in self.results)`: `result.ok for result in ...` is a **generator expression**, a lazily produced sequence, and `all` is true if every item is true.
- `check_health` loops over the probes. In a `try`, a successful `probe.check()` becomes `ProbeResult(name, True, detail)`. `except ProbeFailedError as error:` catches that one kind of error, binding it to `error`, and `str(error)` is its message. A failing probe is reported, not raised, so one broken dependency does not hide the others.

### `application/shop_questions.py`

```python
"""Use case: the five questions of the rental shop, each as one call, for the report program."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from ..domain.errors import RentalShopError
from ..domain.model import Customer, Item, MonthlyRevenue, Rental, ReturnDue
from ..domain.period import RentalPeriod
from .ports import Clock, RentalQueries


class UnknownCustomerNameError(RentalShopError):
    """No single customer has this name."""

    def __init__(self, name: str) -> None:
        super().__init__(f"no customer named {name!r}")


@dataclass(frozen=True, slots=True)
class ShopReport:
    """The answers to the five questions for one set of inputs."""

    free_items: list[Item]
    customer: Customer
    history: list[Rental]
    returns_today: list[ReturnDue]
    today: date
    revenue: list[MonthlyRevenue]
    never_rented: list[Item]

```

`UnknownCustomerNameError` builds its message with `{name!r}`: the `!r` converts the value with `repr`, which puts quotes around text. `ShopReport` bundles the answers; every field is annotated, nothing is computed.

```python
@dataclass(frozen=True, slots=True)
class ShopQuestions:
    """Asks the repository the five questions of lesson step 1."""

    queries: RentalQueries
    clock: Clock

    def report(self, weekend: RentalPeriod, customer_name: str, today: date | None = None) -> ShopReport:
        """Answer all five. `today` defaults to the injected clock's date."""
        customer = self.queries.find_customer(customer_name)
        if customer is None:
            raise UnknownCustomerNameError(customer_name)
        day = today or self.clock.today()
        return ShopReport(
            free_items=self.queries.free_items(weekend),
            customer=customer,
            history=self.queries.history(customer.customer_id),
            returns_today=self.queries.returns_on(day),
            today=day,
            revenue=self.queries.revenue_by_item_and_month(),
            never_rented=self.queries.never_rented(),
        )
```

`ShopQuestions` holds two collaborators, `queries` and `clock`, passed in when it is created (**dependency injection**: the class does not create its own database connection). `report` calls the repository five times. `today: date | None = None` is an optional parameter; `today or self.clock.today()` picks the argument if given and the clock otherwise. The call to `ShopReport(...)` uses **keyword arguments**, which name each field.

### `application/book_item.py`

```python
"""Use case: book an item. The database decides; the application reports the refusal in the shop's words."""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date

from ..domain.errors import BookingDeadlockError
from ..domain.model import Rental
from ..domain.period import RentalPeriod
from .ports import RentalBooking

logger = logging.getLogger(__name__)


def _ignore(_attempt: int) -> None:
    """Default for `on_retry`: nothing to report."""

```

- `logging.getLogger(__name__)` creates a logger named after the module; see [python-logging.md](python-logging.md).
- `_ignore(_attempt)` is a function whose body is only a docstring; the leading underscores say "internal, not for outside use".

```python
@dataclass(frozen=True, slots=True)
class BookItem:
    """Books an item for a customer. There is no availability check here on purpose: checking and then inserting
    races (two requests both see "free"), so the insert is the check and the database's constraint is the rule.

    A booking the database ended as a deadlock victim wrote nothing, so it is tried again (up to `attempts` times).
    The pause doubles each time and is scaled by a random factor in [0.5, 1.0], so victims do not come back in step
    and start a new deadlock; the retry then meets the winner's row and is refused as already booked.
    """

    rentals: RentalBooking
    attempts: int = 8
    pause_seconds: float = 0.05
    sleep: Callable[[float], None] = time.sleep
    rng: random.Random = field(default_factory=random.Random)
    on_retry: Callable[[int], None] = field(default=_ignore)
```

The long docstring is the design note: do not check then insert (two requests could both see "free"); insert and let the constraint decide. The fields are the object's settings: `rentals` is the port; `attempts`, `pause_seconds` are numbers; `sleep: Callable[[float], None] = time.sleep` is a function that takes a float and returns nothing, defaulting to the real `time.sleep`, so tests can pass a fake; `field(default_factory=random.Random)` gives each object its own fresh random generator (a plain mutable default would be shared); `on_retry` is a callback.

```python
    def __call__(self, item_id: int, customer_id: int, first_day: date, days: int) -> Rental:
        """Raises `InvalidPeriodError` for a period that cannot exist, `ItemAlreadyBookedError` when the dates are
        taken, `BookingDeadlockError` when every attempt was a deadlock victim."""
        period = RentalPeriod.starting(first_day, days)
        for attempt in range(1, self.attempts + 1):
            try:
                return self.rentals.book(item_id, customer_id, period)
            except BookingDeadlockError:
                if attempt == self.attempts:
                    raise
                logger.warning("retrying booking after a deadlock: item %d, attempt %d", item_id, attempt)
                self.on_retry(attempt)
                self.sleep(self.pause_seconds * 2 ** (attempt - 1) * self.rng.uniform(0.5, 1.0))
        raise AssertionError("unreachable")  # pragma: no cover
```

- `__call__` makes the object callable like a function: `book_item(1, 2, day, 3)`.
- `for attempt in range(1, self.attempts + 1)` counts from 1 to `attempts`.
- In the `try` the booking is attempted and returned. `except BookingDeadlockError:` catches only the victim error. On the last attempt a bare `raise` re-raises the same error to the caller. Otherwise it logs a warning (the `%d` placeholders are filled in by logging only if the message is emitted), calls the callback, and sleeps.
- The sleep is `pause * 2 ** (attempt - 1) * rng.uniform(0.5, 1.0)`: `**` is the power operator, so the pause doubles each attempt; `uniform(0.5, 1.0)` is a random number between the two, so victims do not retry in lockstep.
- The final `raise AssertionError("unreachable")  # pragma: no cover` satisfies the type checker, which cannot see that the loop always returns or raises; the comment tells the coverage tool to skip the line.

## Try it yourself

```bash
make install && .venv/bin/python -c "from rental_shop.domain.period import RentalPeriod as P; from datetime import date; a=P(date(2026,11,1),date(2026,11,4)); b=P(date(2026,11,4),date(2026,11,6)); print(a.days, a.overlaps(b), str(a))"
```
Expect `3 False 2026-11-01 to 2026-11-04`.

```bash
.venv/bin/python -c "from rental_shop.domain.period import RentalPeriod as P; from datetime import date; P(date(2026,11,4),date(2026,11,4))"
```
Expect a traceback ending in `InvalidPeriodError: the return day 2026-11-04 must be after the first day 2026-11-04`.

```bash
.venv/bin/python -c "from rental_shop.domain.errors import *; print(InvalidPeriodError.__mro__)"
```
Shows the inheritance chain (`InvalidPeriodError`, `RentalShopError`, `ValueError`, `Exception`, ...).

```bash
make test
```
Runs the unit tests of these two layers with a coverage check.

## Mistakes people make

- **Mutable default values** (`def f(x=[])`) shared between calls; the repository uses `field(default_factory=...)`.
- **Float money**; it uses `Decimal`.
- **Catching `Exception` everywhere**; each handler here catches a named error.
- **Mixing layers**: the domain imports no driver, which the import contracts enforce.
- **Time arithmetic by hand**; it uses `date` and `timedelta`.

## Check yourself

1. What does `frozen=True` change? *Fields cannot be assigned after the object is created.*
2. Why does `[1st, 4th)` not overlap `[4th, 6th)`? *The return day is excluded, so no day is in both.*
3. What does `Protocol` give the ports? *An interface that any class with matching methods satisfies, without inheriting.*
4. Why does `BookItem` not check availability first? *Check-then-insert races; the database constraint is the only safe check.*
5. What does a bare `raise` do inside `except`? *It re-raises the error being handled.*

## Further reading

- Python 3.13 documentation: https://docs.python.org/3.13/
- `dataclasses`: https://docs.python.org/3.13/library/dataclasses.html
- `typing.Protocol`: https://docs.python.org/3.13/library/typing.html#typing.Protocol
- Exceptions: https://docs.python.org/3.13/tutorial/errors.html
