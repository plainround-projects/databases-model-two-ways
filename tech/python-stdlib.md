# Python standard library modules used here

## What it is

The **standard library** is the set of modules that ship with Python, so they need no installation. This file covers the small support modules of the `infrastructure` layer, each built on a few standard modules: `os` (the operating system's environment), `re` (regular expressions), `random` and `time` (random numbers, pausing), `signal` (messages from the operating system), `threading` (one flag), `datetime`, `dataclasses` and `collections.abc`.

## Why this repository uses it

Every program needs the same four things around the real work: read settings, wait and try again when the network fails, notice when the user wants to stop, and ask what day it is. Writing them with only the standard library keeps the dependency list to one package (the PostgreSQL driver).

## Where it appears

| File | Role |
|---|---|
| `src/rental_shop/infrastructure/clock.py` | `SystemClock`: today's date. |
| `src/rental_shop/infrastructure/settings.py` | Reads and checks environment variables. |
| `src/rental_shop/infrastructure/retry.py` | Retry with exponential backoff and jitter. |
| `src/rental_shop/infrastructure/shutdown.py` | A "stop now" flag set by Ctrl-C or `kill`. |
| `src/rental_shop/infrastructure/__init__.py` | The package's docstring. |

## How it works underneath

An **environment variable** is a named piece of text a process inherits from its parent; `os.environ` is a dictionary-like view of them. A **regular expression** is a pattern language for text. A **signal** is a small message the operating system delivers to a process: `SIGINT` is sent by Ctrl-C and `SIGTERM` by a polite `kill` or by `docker stop`. A program may register a **handler** function for a signal; the default for both is to die at once.

**Exponential backoff** means waiting longer after each failure: 0.5 s, 1 s, 2 s, 4 s. **Jitter** multiplies each wait by a random factor, so many clients that failed together do not all retry at the same instant (the "thundering herd").

## Walkthrough of this repository's use

### `clock.py`

```python
"""Infrastructure: adapters for PostgreSQL, settings, logging, retry and signals."""
```

```python
"""Adapter: the wall clock. Implements the `Clock` port."""

from __future__ import annotations

from datetime import date


class SystemClock:
    """Today's date from the machine's clock."""

    def today(self) -> date:
        return date.today()
```

`SystemClock` matches the `Clock` protocol from [python.md](python.md) by having a `today` method; it does not inherit anything. It exists so the rest of the code asks the clock instead of calling `date.today()` directly, and tests can supply a fake date.

### `settings.py`: two helpers and the error

```python
"""Configuration from the environment, validated once at startup (twelve-factor). Secrets only from here."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field

_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR"}
_IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


class ConfigurationError(ValueError):
    """An environment variable is missing or has an unusable value."""


def _text(environ: Mapping[str, str], name: str, default: str | None = None) -> str:
    value = environ.get(name, default if default is not None else "").strip()
    if not value:
        raise ConfigurationError(f"{name} must be set and not empty")
    return value


def _positive_int(environ: Mapping[str, str], name: str, default: int) -> int:
    raw = environ.get(name, str(default)).strip()
    if not raw.isdigit() or int(raw) < 1:
        raise ConfigurationError(f"{name} must be a positive integer, got {raw!r}")
    return int(raw)

```

- `import os` and `import re` bring in the environment and regular-expression modules. `Mapping` (from `collections.abc`) is the type of any read-only dictionary-like object.
- `_LEVELS` is a set (an unordered collection without duplicates) of allowed log levels.
- `_IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")` compiles the pattern once. The `r"..."` prefix is a **raw string**, where backslashes are kept as typed. `^` is the start of the text. `[a-z_]` is exactly one lowercase letter or underscore. `[a-z0-9_]{0,62}` is zero to 62 lowercase letters, digits or underscores. `$` is the end. So it accepts names such as `public` or `test_ab12` and rejects `Public`, `a-b` and `1abc`. Names like that are safe to put in the connection options.
- `ConfigurationError(ValueError)` is the one error settings raise.
- `_text` reads `environ.get(name, default if default is not None else "")`: the value, or the default, or an empty string. `.strip()` removes spaces at both ends. If the result is empty it raises an error that names the variable. A variable with no default (the password) is therefore required.
- `_positive_int` reads the text, and `raw.isdigit()` is true only for text made of digits. `int(raw) < 1` rejects `0`. The message uses `{raw!r}` to show the bad value in quotes. Only then is the text turned into a number.

### `settings.py`: the two dataclasses

```python
@dataclass(frozen=True, slots=True)
class PostgresSettings:
    """The PostgreSQL part of the configuration; the password is never printed."""

    host: str
    port: int
    database: str
    user: str
    password: str = field(repr=False)  # never printed or logged
    schema: str
    connect_timeout_seconds: int
    statement_timeout_ms: int


@dataclass(frozen=True, slots=True)
class Settings:
    """Everything the programs read from the environment. See .env.example for each variable."""

    postgres: PostgresSettings
    log_level: str
```

`PostgresSettings` is a frozen dataclass of the connection settings. `password: str = field(repr=False)` hides the password from the object's printed form, so printing settings or logging them never leaks it. `Settings` holds a `PostgresSettings` and the log level.

```python
    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if environ is None else environ
        level = _text(env, "LOG_LEVEL", "INFO").upper()
        if level not in _LEVELS:
            raise ConfigurationError(f"LOG_LEVEL must be one of {sorted(_LEVELS)}, got {level!r}")
        schema = _text(env, "POSTGRES_SCHEMA", "public")
        if not _IDENTIFIER.match(schema):
            raise ConfigurationError(f"POSTGRES_SCHEMA must be a lower-case identifier, got {schema!r}")
        return cls(
            postgres=PostgresSettings(
                host=_text(env, "POSTGRES_HOST", "localhost"),
                port=_positive_int(env, "POSTGRES_PORT", 5441),
                database=_text(env, "POSTGRES_DB", "rentals"),
                user=_text(env, "POSTGRES_USER", "shop"),
                password=_text(env, "POSTGRES_PASSWORD"),
                schema=schema,
                connect_timeout_seconds=_positive_int(env, "POSTGRES_CONNECT_TIMEOUT_SECONDS", 5),
                statement_timeout_ms=_positive_int(env, "POSTGRES_STATEMENT_TIMEOUT_MS", 30_000),
            ),
            log_level=level,
        )
```

`from_env` is a class method that builds the whole configuration. `env = os.environ if environ is None else environ` lets tests pass a plain dictionary. It checks `LOG_LEVEL` (upper-cased, must be in `_LEVELS`), checks the schema name against the regular expression, then builds `PostgresSettings` with keyword arguments, using defaults that match `.env.example` (see [dotenv.md](dotenv.md)): host `localhost`, port `5441`, database `rentals`, user `shop`, 5 seconds connect timeout, and `30_000` ms statement timeout (the underscore in a number is only a visual separator). Everything is checked once at start-up, so a typo stops the program at once with a clear message rather than failing deep inside a query. This is the **twelve-factor** rule: configuration lives in the environment, not in the code.

### `retry.py`

```python
"""Retry with exponential backoff and jitter for calls that cross the network."""

from __future__ import annotations

import random
import time
from collections.abc import Callable


def retry[T](
    operation: Callable[[], T],
    *,
    attempts: int,
    base_delay_seconds: float,
    retry_on: tuple[type[BaseException], ...],
    sleep: Callable[[float], None] = time.sleep,
    rng: random.Random | None = None,
    max_delay_seconds: float = 10.0,
    on_retry: Callable[[int, BaseException], None] | None = None,
) -> T:
```

- `def retry[T](...)` declares a **generic function**: `T` stands for "whatever type `operation` returns", and the function returns that same type. This syntax is new in Python 3.12.
- `operation: Callable[[], T]` is a function that takes no arguments and returns `T`. The bare `*,` means every parameter after it must be given by name, which makes calls readable (`attempts=5`).
- `retry_on: tuple[type[BaseException], ...]` is a tuple of error classes that count as retryable. `sleep` and `rng` can be replaced by tests. `max_delay_seconds` caps the wait. `on_retry` is an optional callback taking the attempt number and the error.

```python
    """Call `operation` up to `attempts` times, doubling the pause after each failure in `retry_on`.

    The pause is `base * 2**(attempt - 1)` capped at `max_delay_seconds`, then scaled by a random
    factor in [0.5, 1.0] so many clients do not retry in step. The last failure is raised.
    """
    if attempts < 1:
        raise ValueError("attempts must be at least 1")
    jitter = rng or random.Random()
    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except retry_on as error:
            if attempt == attempts:
                raise
            if on_retry:
                on_retry(attempt, error)
            sleep(min(max_delay_seconds, base_delay_seconds * 2 ** (attempt - 1)) * jitter.uniform(0.5, 1.0))
    raise AssertionError("unreachable")  # pragma: no cover
```

- A guard rejects `attempts < 1` with `ValueError`.
- `jitter = rng or random.Random()` uses the given generator or a new one.
- The loop tries up to `attempts` times. `except retry_on as error:` catches only the listed error types. On the last attempt a bare `raise` re-raises the failure. Otherwise it calls `on_retry` (if given) and sleeps: `base * 2 ** (attempt - 1)` doubles each time, `min(max_delay, ...)` caps it, and `jitter.uniform(0.5, 1.0)` scales by a random factor.
- The final `raise AssertionError` cannot happen and exists for the type checker; `# pragma: no cover` tells the coverage tool to ignore it.

### `shutdown.py`

```python
"""Graceful shutdown: SIGINT and SIGTERM set a flag the work loops check between units of work."""

from __future__ import annotations

import signal
import threading
from types import FrameType


class ShutdownSignal:
    """A flag that SIGINT and SIGTERM set, which work loops check between units of work."""

    def __init__(self) -> None:
        self._requested = threading.Event()

    def install(self) -> None:
        """Route SIGINT and SIGTERM to `request`, so in-flight work finishes and connections close."""
        for number in (signal.SIGINT, signal.SIGTERM):
            signal.signal(number, self._handle)

    def _handle(self, _number: int, _frame: FrameType | None) -> None:
        self.request()

    def request(self) -> None:
        self._requested.set()

    @property
    def requested(self) -> bool:
        return self._requested.is_set()
```

- `threading.Event()` is a thread-safe flag: `set()` raises it, `is_set()` reads it.
- `install` loops over `(signal.SIGINT, signal.SIGTERM)` and calls `signal.signal(number, self._handle)`, which registers the method as the handler. Python calls a handler with two arguments, the signal number and the current stack frame (`FrameType | None`); the leading underscores on `_number` and `_frame` say they are unused.
- `_handle` just calls `request`, which sets the flag. The handler does nothing else, because only very small actions are safe inside a signal handler.
- The `requested` property tells work loops whether to stop between units of work, so in-flight database work finishes and connections close.

## Try it yourself

```bash
.venv/bin/python -c "
from rental_shop.infrastructure.settings import Settings
s = Settings.from_env({'POSTGRES_PASSWORD': 'x'})
print(s)"
```
Prints the settings with `password` absent from the text, and the defaults filled in.

```bash
.venv/bin/python -c "
from rental_shop.infrastructure.settings import Settings
Settings.from_env({})"
```
Fails with `ConfigurationError: POSTGRES_PASSWORD must be set and not empty`.

```bash
.venv/bin/python -c "
from rental_shop.infrastructure.retry import retry
calls = []
def flaky():
    calls.append(1)
    if len(calls) < 3: raise OSError('no')
    return 'ok'
print(retry(flaky, attempts=5, base_delay_seconds=0.01, retry_on=(OSError,)), len(calls))"
```
Prints `ok 3`.

```bash
.venv/bin/python -c "
import os, signal, time
from rental_shop.infrastructure.shutdown import ShutdownSignal
s = ShutdownSignal(); s.install()
os.kill(os.getpid(), signal.SIGTERM); time.sleep(0.1)
print(s.requested)"
```
Prints `True`: the program received SIGTERM and kept running.

## Mistakes people make

- **Reading `os.environ` all over the code.** Here it is read once in `from_env`.
- **Retrying forever or at fixed intervals.** Attempts are limited, delays grow and are jittered.
- **Retrying errors that will never succeed.** `retry_on` lists only the retryable ones.
- **Doing real work in a signal handler.** The handler only sets a flag.
- **Putting a password in `repr`.** `field(repr=False)` prevents it.

## Check yourself

1. Why does `_text` strip the value? *Spaces around a setting are almost always mistakes; stripping avoids empty-looking values.*
2. What does `retry` do on the last failed attempt? *It re-raises that error.*
3. What does the regular expression allow? *A lowercase identifier of at most 63 characters.*
4. What signals does `ShutdownSignal` handle? *`SIGINT` (Ctrl-C) and `SIGTERM`.*
5. Why is the clock a class? *So tests can pass a fake clock and fix the date.*

## Further reading

- `os.environ`: https://docs.python.org/3.13/library/os.html#os.environ
- `re`: https://docs.python.org/3.13/library/re.html
- `signal`: https://docs.python.org/3.13/library/signal.html
- Generic functions (PEP 695 syntax): https://docs.python.org/3.13/reference/compound_stmts.html#generic-functions
- The Twelve-Factor App, config: https://12factor.net/config
