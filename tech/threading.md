# Threads (Python's `threading` module)

## What it is

A **thread** is a path of execution inside a running program. A program (one **process**) can start many threads; they share the same memory but each runs its own sequence of steps, so several things can wait or work at the same time. Python's `threading` module creates and coordinates them. A thread that waits for a database answer lets another thread run meanwhile.

## Why this repository uses it

Lesson step 5 is a race: 20 customers try to rent the same drill for overlapping dates at the same instant. To produce that on one machine the program starts 20 threads, each with its own database connection, and holds them at a starting line until all are ready. If the database is correct, exactly one thread wins.

## Where it appears

| File | What it does with threads |
|---|---|
| `src/rental_shop/application/race.py` | Starts the contenders and counts how each one ended. |
| `src/rental_shop/infrastructure/shutdown.py` | Uses `threading.Event` as the "please stop" flag; see [python-stdlib.md](python-stdlib.md). |
| `tests/unit/application/test_race.py` | Runs the race against fakes. See [pytest.md](pytest.md). |

## How it works underneath

All threads of a process see the same variables. If two threads change the same variable at once, the result can be wrong (a **race condition**). A **lock** (`threading.Lock`) is an object only one thread can hold at a time: `with lock:` waits for the lock, runs the block, and releases it. A **barrier** (`threading.Barrier(n)`) makes each thread that calls `wait()` stop until `n` threads have arrived, then lets them all go together. `Thread.start()` begins running the thread's function; `Thread.join()` waits until it has finished.

Python's interpreter lets only one thread run Python instructions at a moment, but a thread that waits for the network or the database gives its turn away. That is exactly what these contenders do, so the 20 inserts are really in flight at PostgreSQL together. The database server is a separate process, and each connection is served by its own server process.

A **closure** is a function defined inside another function that can read the outer function's variables. The code below uses closures so each thread's function can reach the shared lists.

## Walkthrough of this repository's use

### Settings of the race

```python
"""Use case: race several connections for the same item and the same dates (lesson step 5)."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from ..domain.errors import BookingDeadlockError, ItemAlreadyBookedError
from ..domain.model import RaceTally
from ..domain.period import RentalPeriod
from .book_item import BookItem
from .ports import GatewayOpener

logger = logging.getLogger(__name__)

CONTENDER_STAGGER_DAYS = 3  # contenders start up to two days apart; every pair of their periods still overlaps
CONTENDER_LENGTH_DAYS = 4
BARRIER_TIMEOUT_SECONDS = 30.0

```

- The imports bring in `threading` and `time` plus the shop's errors and types. `logger` is this module's logger (see [python-logging.md](python-logging.md)).
- The three constants are named numbers. Each contender books four days (`CONTENDER_LENGTH_DAYS`), and starts 0, 1 or 2 days after the base date (`index % 3`, with `CONTENDER_STAGGER_DAYS = 3`), so every pair still shares at least two days: the periods are different but all overlap. `BARRIER_TIMEOUT_SECONDS` bounds how long a contender waits at the starting line.

### The `Race` object

```python
@dataclass(frozen=True, slots=True)
class Race:
    """Runs rounds in which `contenders` independent connections book one fresh item at the same instant.

    Each contender opens its own session before a barrier releases them all, so the inserts really run at the same
    time. There is no lock in the application: the exclusion constraint has to pick the one winner.
    """

    open_session: GatewayOpener
    contenders: int = 20
    first_day: date = date(2027, 1, 4)
    sleep: Callable[[float], None] = time.sleep

    def run_round(self, label: str) -> RaceTally:
        """One round against a new item, with distinct but pairwise overlapping periods. Returns the tally."""
```

`Race` is a frozen dataclass (see [python.md](python.md)). `open_session` is a function that returns a new database session when used in a `with`; passing it in keeps this module free of any database driver. `contenders` is 20 by default; `first_day` is a fixed date in 2027, far from the seed's rentals; `sleep` is replaceable for tests. `run_round` runs one round with a label.

### Preparation of one round

```python
        with self.open_session() as setup:
            item = setup.add_item(f"Race item {label}", Decimal("10.00"))
            customer = setup.add_customer(f"Racer {label}")
        barrier = threading.Barrier(self.contenders)
        outcomes: list[str] = []
        retries = [0]
        guard = threading.Lock()

        def count_retry(_attempt: int) -> None:
            with guard:
                retries[0] += 1

```

- The first `with self.open_session() as setup:` opens one session, creates a fresh item and a fresh customer, and closes the session. A new item each round means rounds never interfere.
- `threading.Barrier(self.contenders)` is the starting line. `outcomes` collects one text result per contender. `retries = [0]` is a one-element list, used as a counter that a closure can change (a closure may modify a list's content but not rebind a plain number from the outer function). `guard = threading.Lock()` protects both lists.
- `count_retry` is called by the booking code each time a deadlock victim retries; `with guard:` makes the increment safe.

### What each contender does

```python
        def contend(index: int) -> None:
            period = RentalPeriod.starting(self.first_day, CONTENDER_LENGTH_DAYS).shifted(
                index % CONTENDER_STAGGER_DAYS
            )
            result = "failed"
            released = False
            try:
                with self.open_session() as session:
                    barrier.wait(timeout=BARRIER_TIMEOUT_SECONDS)
                    released = True
                    BookItem(session, sleep=self.sleep, on_retry=count_retry)(
                        item.item_id, customer.customer_id, period.first_day, period.days
                    )
                    result = "success"
            except ItemAlreadyBookedError:
                result = "refused"
            except BookingDeadlockError:
                result = "deadlocked"
            except threading.BrokenBarrierError:
                logger.error("contender %d could not reach the barrier", index)
            except Exception:
                logger.exception("a contender failed for a reason other than the constraint")
            finally:
                if not released:
                    barrier.abort()  # a contender that never reached the barrier must not leave the others waiting
            with guard:
                outcomes.append(result)

```

- `contend(index)` is the function each thread runs. It builds its own period from its index.
- `result = "failed"` is the default outcome; `released` becomes true once the thread has passed the barrier.
- `with self.open_session() as session:` gives the contender its own connection (a connection must not be shared between threads). `barrier.wait(timeout=...)` blocks until all 20 contenders have connected, then releases them in the same instant. Then `BookItem(...)(...)` books the item: the constructor receives the session, and the second pair of parentheses calls the object (see `__call__` in [python.md](python.md)). If no error occurs, the result is `"success"`.
- The `except` clauses translate what happened into a word: `ItemAlreadyBookedError` becomes `"refused"` (the database said no, which is the correct outcome for 19 of the 20), `BookingDeadlockError` becomes `"deadlocked"` (every retry was a victim), `BrokenBarrierError` means the starting line failed, and the last, `except Exception`, logs any other failure with its traceback (`logger.exception`).
- `finally:` always runs. If a contender never reached the barrier, `barrier.abort()` releases the others with an error instead of leaving them waiting forever.
- At the end, still inside the thread, `with guard: outcomes.append(result)` records the result under the lock.

### Starting, joining and counting

```python
        threads = [
            threading.Thread(target=contend, args=(index,), name=f"contender-{index}")
            for index in range(self.contenders)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        return RaceTally(
            contenders=self.contenders,
            successes=outcomes.count("success"),
            refused=outcomes.count("refused"),
            failed=outcomes.count("failed"),
            deadlocked=outcomes.count("deadlocked"),
            deadlock_retries=retries[0],
        )
```

A list comprehension creates 20 `Thread` objects: `target=contend` is the function, `args=(index,)` its arguments (a one-item tuple needs the comma) and `name` a label that appears in logs. The first loop starts them all, the second `join`s each, so the function continues only when every contender has finished. `RaceTally(...)` then counts outcomes with `list.count`, and `deadlock_retries` is the shared counter. The safety property the lesson wants is `tally.one_winner`; the full check is `tally.is_correct` (see [python.md](python.md)).

## Try it yourself

```bash
make up && make db && make race RUNS=3
```
Three rounds. Each line reports 1 success and 19 refused (the plain-insert mode, `make race-plain`, can show deadlock retries).

```bash
.venv/bin/python -c "
import threading
b = threading.Barrier(3)
def go(i):
    b.wait()
    print('released', i)
ts = [threading.Thread(target=go, args=(i,)) for i in range(3)]
[t.start() for t in ts]; [t.join() for t in ts]"
```
Nothing prints until the third thread arrives; then three `released` lines appear.

```bash
.venv/bin/python -m pytest tests/unit/application/test_race.py -q
```
The race logic against fake sessions, with no database.

## Mistakes people make

- **Sharing one database connection between threads.** Each contender opens its own.
- **Changing shared data without a lock.** The outcome list and retry counter are changed under `guard`.
- **Forgetting `join`**, so the main thread reads results before the workers finish.
- **A barrier nobody can complete**, which hangs. The `timeout` and `abort()` prevent it.
- **Trusting that the application decides the winner.** The race shows the database decides.

## Check yourself

1. What does `Barrier(20)` do? *Holds each thread that calls `wait()` until 20 have arrived, then releases all.*
2. Why `retries = [0]` and not `retries = 0`? *A closure can modify a list's content, but cannot rebind the outer number without `nonlocal`.*
3. Why does each contender open its own session? *A connection must not be shared between threads, and separate connections make the inserts really concurrent.*
4. What does `finally` guarantee? *The abort of the barrier runs even if an error escaped.*
5. What outcome is expected for 19 of the 20? *`refused`: the exclusion constraint rejects them.*

## Further reading

- `threading` (Python 3.13): https://docs.python.org/3.13/library/threading.html
- `Barrier`: https://docs.python.org/3.13/library/threading.html#barrier-objects
