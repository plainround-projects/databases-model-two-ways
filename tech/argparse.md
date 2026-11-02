# argparse and the command-line programs

## What it is

`argparse` is the standard Python module that reads the **command line**: the words typed after a program's name. In `python -m rental_shop.interfaces.book_cli --item 1 --days 2`, the words `--item 1` and `--days 2` are **arguments**. A word that starts with two dashes and takes a value is an **option** (or flag). `argparse` turns the text into typed values, checks them, creates `--help` output and prints a usage message on a mistake.

## Why this repository uses it

The lesson is run from a terminal, not a web page. Four small programs (`book`, `race`, `report`, `health`) are the "interfaces" layer: each reads the command line, builds the real objects (a database connection, a use case) and prints the result. They also own the **exit code**: the number a program leaves behind for the shell (`0` success; here `1` a failed check, `2` bad input or configuration, `3` the item is already booked).

## Where it appears

| File | The program it implements |
|---|---|
| `src/rental_shop/interfaces/common.py` | `load_settings`, shared start-up of all programs. |
| `src/rental_shop/interfaces/book_cli.py` | Book one rental (`make book`). |
| `src/rental_shop/interfaces/race_cli.py` | The 20-connection race (`make race`). |
| `src/rental_shop/interfaces/report_cli.py` | The five questions as text (`make report`). |
| `src/rental_shop/interfaces/health_cli.py` | The health check (`make health`, the Docker `HEALTHCHECK`). |
| `pyproject.toml` | Declares each `main` as a console command; see [toml.md](toml.md). |

## How it works underneath

The operating system starts the process with a list of strings (`sys.argv`). `parser.parse_args(argv)` walks this list, matches each option to a declared one, converts the value with the declared `type` function (`int`, or a function such as `date.fromisoformat`) and returns an object whose attributes are the values. On bad input it prints a message to standard error and exits with code 2. If `argv` is `None` it reads the real command line; tests pass a list instead.

The special line `if __name__ == "__main__":` is true only when the file is run as a program, not when it is imported. `raise SystemExit(main())` ends the process with the number `main` returns, which becomes the exit code.

Each program only wires parts together: it builds an adapter (from [psycopg.md](psycopg.md)), hands it to a use case (from [python.md](python.md)) and turns the result or the named error into a line of text and an exit code.

## Walkthrough of this repository's use

### `common.py`: shared start-up

```python
"""Interfaces: the command-line programs. They wire adapters into use cases and own exit codes."""
```

```python
"""Startup shared by the programs: settings or a clear exit code 2."""

from __future__ import annotations

import sys

from ..infrastructure.logging import configure_logging
from ..infrastructure.settings import ConfigurationError, Settings


def load_settings() -> Settings | None:
    """Read and validate the environment, configure logging, or print the problem and return None."""
    try:
        settings = Settings.from_env()
    except ConfigurationError as error:
        print(f"configuration error: {error}", file=sys.stderr)
        return None
    configure_logging(settings.log_level)
    return settings
```

`load_settings` reads the settings (see [python-stdlib.md](python-stdlib.md)). If a variable is wrong it prints `configuration error: ...` to standard error (`file=sys.stderr`) and returns `None`, which each `main` turns into exit code 2. Only after the settings are valid does it call `configure_logging` (see [python-logging.md](python-logging.md)). The return type `Settings | None` makes the caller handle both cases.

### `book_cli.py`

```python
"""Book an item for a customer.

python -m rental_shop.interfaces.book_cli --item 1 --customer 2 --from 2026-11-03 --days 2

Exit code 0 when booked, 3 when the dates are taken (the database refused), 2 for bad input or configuration.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from datetime import date

from ..application.book_item import BookItem
from ..domain.errors import InvalidPeriodError, ItemAlreadyBookedError, UnknownCustomerError, UnknownItemError
from ..infrastructure.postgres import session
from ..infrastructure.postgres_rentals import PostgresRentals
from .common import load_settings

```

The docstring is the program's manual page: the command and the exit codes. The imports show the layering: an interface may import the application, the domain and the infrastructure.

```python
def build_parser() -> argparse.ArgumentParser:
    """The command line of the book program."""
    parser = argparse.ArgumentParser(description="Book an item for a customer.")
    parser.add_argument("--item", type=int, required=True, help="item id")
    parser.add_argument("--customer", type=int, required=True, help="customer id")
    parser.add_argument(
        "--from", dest="first_day", type=date.fromisoformat, required=True, help="first rental day, YYYY-MM-DD"
    )
    parser.add_argument(
        "--days", type=int, required=True, help="number of rental days; the item comes back on the next day"
    )
    return parser

```

`argparse.ArgumentParser(description=...)` starts a parser. Each `add_argument` declares one option: `"--item"` is its name, `type=int` converts the text to a whole number (and rejects text such as `abc`), `required=True` makes it mandatory, and `help` is shown by `--help`. `--from` is a Python keyword (`from`), so it cannot be an attribute name; `dest="first_day"` stores it under another name. `type=date.fromisoformat` uses the standard function that parses `2026-11-03`, so a malformed date is rejected by `argparse` itself.

```python
def main(argv: Sequence[str] | None = None) -> int:
    """Book once and say what happened in the shop's words."""
    arguments = build_parser().parse_args(argv)
    settings = load_settings()
    if settings is None:
        return 2
    with session(settings.postgres) as connection:
        book = BookItem(PostgresRentals(connection))
        try:
            rental = book(arguments.item, arguments.customer, arguments.first_day, arguments.days)
        except ItemAlreadyBookedError as error:
            print(f"already booked: {error}")
            return 3
        except (InvalidPeriodError, UnknownItemError, UnknownCustomerError) as error:
            print(f"cannot book: {error}")
            return 2
    print(f"booked rental {rental.rental_id}: item {rental.item_id} for {rental.period}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- `main(argv: Sequence[str] | None = None) -> int` returns the exit code instead of exiting, so tests can call it and check the number.
- It parses, loads settings (returning 2 on a problem), opens a database `session` (see [psycopg.md](psycopg.md)) in a `with` that closes it afterwards, builds the use case `BookItem(PostgresRentals(connection))` and calls it.
- `except ItemAlreadyBookedError` prints `already booked: ...` and returns 3. The second `except` catches a tuple of three errors for bad input and returns 2. Because the `return`s are inside the `with`, the connection is closed on every path.
- On success it prints `booked rental N: item I for <period>` and returns 0.
- The last two lines run `main` only when the file is executed as a program.

### `health_cli.py`

```python
"""Health command: exit 0 when PostgreSQL has the rental tables and the exclusion constraint.

python -m rental_shop.interfaces.health_cli
"""

from __future__ import annotations

from collections.abc import Sequence

from ..application.health import check_health
from ..infrastructure.health_probes import PostgresSchemaProbe
from .common import load_settings


def main(_argv: Sequence[str] | None = None) -> int:
    """Check PostgreSQL; returns 0 when healthy."""
    settings = load_settings()
    if settings is None:
        return 2
    report = check_health([PostgresSchemaProbe(settings.postgres)])
    for result in report.results:
        print(f"{'ok' if result.ok else 'FAIL'} {result.name}: {result.detail}")
    return 0 if report.healthy else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

The health program loads settings and runs `check_health` with the one PostgreSQL probe. It prints `ok postgres: ...` or `FAIL postgres: ...` for each result and returns `0` if healthy, `1` otherwise. `_argv` starts with an underscore because the program reads no options. The expression `'ok' if result.ok else 'FAIL'` inside the f-string chooses the word. This exit code is what Docker's `HEALTHCHECK` reads.

### `race_cli.py`

```python
"""Race 20 connections for one item on overlapping dates, 20 times (lesson step 5).

python -m rental_shop.interfaces.race_cli [--runs 20] [--contenders 20]
Exit code 0 only when every run has exactly one winner. With the default insert (ON CONFLICT DO NOTHING) every
other contender is refused by the exclusion constraint; with --insert raise (the lesson's plain INSERT) a contender
may instead be a deadlock victim, which is counted and retried.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from ..application.race import Race
from ..domain.model import RaceTally
from ..infrastructure.postgres_rentals import InsertMode, gateway_opener
from ..infrastructure.shutdown import ShutdownSignal
from .common import load_settings


def build_parser() -> argparse.ArgumentParser:
    """The command line of the race program."""
    parser = argparse.ArgumentParser(description="Race connections for the same item and overlapping dates.")
    parser.add_argument("--runs", type=int, default=20, help="rounds, each against a fresh item (default 20)")
    parser.add_argument("--contenders", type=int, default=20, help="concurrent connections per round (default 20)")
    parser.add_argument(
        "--insert",
        choices=[mode.value for mode in InsertMode],
        default=InsertMode.SKIP.value,
        help="skip: INSERT ... ON CONFLICT DO NOTHING (default); raise: a plain INSERT that raises 23P01",
    )
    return parser

```

`--runs` and `--contenders` are integers with defaults. `--insert` uses `choices=[mode.value for mode in InsertMode]`, a list comprehension over the enum (`["raise", "skip"]`), so any other word is rejected. Its default is the text of `InsertMode.SKIP`.

```python
def describe(run: int, tally: RaceTally, mode: InsertMode) -> str:
    """One line per round: the winner, how the others were refused, and anything unusual."""
    refusal = "exclusion violations (23P01)" if mode is InsertMode.RAISE else "refused by the exclusion constraint"
    line = f"run {run:2d}: {tally.successes} success, {tally.refused} {refusal}"
    if tally.deadlocked:
        line += f", {tally.deadlocked} gave up after deadlocks"
    if tally.failed:
        line += f", {tally.failed} other failures"
    if tally.deadlock_retries:
        line += f" [{tally.deadlock_retries} deadlock retries]"
    return line

```

`describe` builds one report line per round with an f-string. `{run:2d}` formats the number in a width of at least two characters. The `if` statements append the optional parts only when there were deadlock give-ups, other failures or retries.

```python
def main(argv: Sequence[str] | None = None) -> int:
    """Run the rounds, print one line per round, stop cleanly on SIGINT or SIGTERM between rounds."""
    arguments = build_parser().parse_args(argv)
    if arguments.runs < 1 or arguments.contenders < 2:
        print("--runs must be at least 1 and --contenders at least 2")
        return 2
    settings = load_settings()
    if settings is None:
        return 2
    shutdown = ShutdownSignal()
    shutdown.install()
    race = Race(gateway_opener(settings.postgres, InsertMode(arguments.insert)), contenders=arguments.contenders)
    correct = 0
    done = 0
    for run in range(1, arguments.runs + 1):
        if shutdown.requested:
            print("stopped by signal")
            break
        tally = race.run_round(f"{run}")
        done += 1
        correct += tally.one_winner
        print(describe(run, tally, InsertMode(arguments.insert)))
    print(f"{correct} of {done} runs had exactly one winner")
    return 0 if done == arguments.runs and correct == done else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

`main` checks the numbers (at least one run and two contenders), loads settings, installs the signal handler (see [python-stdlib.md](python-stdlib.md)) and builds the `Race` (see [threading.md](threading.md)) with `gateway_opener`, which gives every contender its own connection. Between rounds it checks `shutdown.requested`, so Ctrl-C ends the program after the current round with `stopped by signal`. `correct += tally.one_winner` adds a boolean to a number (`True` counts as 1). The final line says how many runs had one winner, and the exit code is 0 only if every planned run completed with exactly one winner.

### `report_cli.py`

```python
"""Answer the shop's five questions: python -m rental_shop.interfaces.report_cli [--today 2026-11-04] [--customer Ada]

The defaults are the lesson's hand-checked inputs; the output on the seed data is the lesson's expected output.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from datetime import date

from ..application.shop_questions import ShopQuestions, ShopReport, UnknownCustomerNameError
from ..domain.errors import InvalidPeriodError
from ..domain.model import Rental
from ..domain.period import RentalPeriod
from ..infrastructure.clock import SystemClock
from ..infrastructure.postgres import session
from ..infrastructure.postgres_rentals import PostgresRentals
from .common import load_settings


def build_parser() -> argparse.ArgumentParser:
    """The command line of the report program."""
    parser = argparse.ArgumentParser(description="Answer the rental shop's five questions.")
    parser.add_argument(
        "--today", type=date.fromisoformat, default=date(2026, 11, 4), help="the day for today's returns"
    )
    parser.add_argument(
        "--weekend-from", type=date.fromisoformat, default=date(2026, 11, 7), help="first day of the weekend"
    )
    parser.add_argument(
        "--weekend-to", type=date.fromisoformat, default=date(2026, 11, 9), help="day after the weekend"
    )
    parser.add_argument("--customer", default="Ada", help="customer whose history to show")
    return parser

```

The defaults are the lesson's inputs: today is 2026-11-04 and the weekend is 2026-11-07 up to 2026-11-09. Options `--today`, `--weekend-from` and `--weekend-to` parse dates; `--customer` defaults to `Ada`.

```python
def _join(words: list[str]) -> str:
    return ", ".join(words) if words else "(none)"


def _ids(rentals: list[Rental]) -> str:
    ids = [str(rental.rental_id) for rental in sorted(rentals, key=lambda rental: rental.rental_id)]
    return "none" if not ids else ", ".join(ids[:-1]) + (" and " if len(ids) > 1 else "") + ids[-1]


def format_report(report: ShopReport) -> list[str]:
    """The five answers as lines, in the order of the lesson's expected output."""
    returns = [f"rental {due.rental_id} ({due.item_name}, {due.customer_name})" for due in report.returns_today]
    revenue = " | ".join(f"{row.item_name} {row.month} {row.amount:.2f}" for row in report.revenue)
    return [
        f"free next weekend: {_join([item.name for item in report.free_items])}",
        f"{report.customer.name}'s history: {_ids(report.history)}",
        f"returns on {report.today.isoformat()}: {_join(returns)}",
        f"revenue per item and month: {revenue}",
        f"never rented: {_join([item.name for item in report.never_rented])}",
    ]

```

- `_join` joins words with commas or gives `(none)` when the list is empty.
- `_ids` sorts the rentals by id (`key=lambda rental: rental.rental_id` is an inline one-expression function) and writes `1, 3 and 5`-style text: all ids but the last joined with commas, `and` only when there is more than one, then the last.
- `format_report` returns the five output lines. `f"{row.amount:.2f}"` formats the `Decimal` with exactly two decimals. `" | ".join(...)` over a generator expression builds the revenue line.

```python
def main(argv: Sequence[str] | None = None) -> int:
    """Print the five answers."""
    arguments = build_parser().parse_args(argv)
    settings = load_settings()
    if settings is None:
        return 2
    try:
        weekend = RentalPeriod(arguments.weekend_from, arguments.weekend_to)
        with session(settings.postgres) as connection:
            questions = ShopQuestions(PostgresRentals(connection), SystemClock())
            report = questions.report(weekend, arguments.customer, arguments.today)
    except (InvalidPeriodError, UnknownCustomerNameError) as error:
        print(f"cannot answer: {error}")
        return 2
    print("\n".join(format_report(report)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

`main` builds the weekend period (an invalid one raises `InvalidPeriodError`), opens a session, builds `ShopQuestions` with the real clock and asks for the report. Both known errors print `cannot answer: ...` and return 2. Otherwise it prints the lines and returns 0.

## Try it yourself

```bash
make install && .venv/bin/python -m rental_shop.interfaces.book_cli --help
```
Shows usage, the four options and their help texts.

```bash
.venv/bin/python -m rental_shop.interfaces.book_cli --item x --customer 1 --from 2026-11-03 --days 2; echo "exit=$?"
```
`argparse` prints `argument --item: invalid int value: 'x'` and exits with 2.

```bash
POSTGRES_PASSWORD= .venv/bin/python -m rental_shop.interfaces.health_cli; echo "exit=$?"
```
Prints `configuration error: POSTGRES_PASSWORD must be set and not empty` and `exit=2`.

```bash
make up && make db && make report; echo "exit=$?"
```
Prints the five answers of the lesson and `exit=0`.

```bash
make book ITEM=1 CUSTOMER=2 FROM=2026-11-03 DAYS=2; echo "exit=$?"
```
Prints `already booked: ...` and `exit=3` on the seed data (a Drill rental exists there).

## Mistakes people make

- **Calling `sys.exit` inside deep code.** Here only `__main__` exits; `main` returns a number.
- **Parsing dates by hand.** `type=date.fromisoformat` rejects bad input before any code runs.
- **Reading settings after doing work.** Settings are validated first.
- **Leaving connections open on an error return.** The `with` closes them.
- **Letting an option name clash with a keyword** (`--from`): use `dest`.

## Check yourself

1. What does `type=int` do? *Converts the text and rejects non-numbers.*
2. Why does `main` return an int instead of calling `exit`? *Tests can call it and check the number.*
3. What do exit codes 0, 2 and 3 mean here? *Success, bad input or configuration, item already booked.*
4. What does `if __name__ == "__main__":` guard? *The `raise SystemExit(main())`: it runs only when executed as a program.*
5. Why `dest="first_day"`? *`from` is a Python keyword and cannot be an attribute name.*

## Further reading

- `argparse` (Python 3.13): https://docs.python.org/3.13/library/argparse.html
- `__main__` (top-level code environment): https://docs.python.org/3.13/library/__main__.html
