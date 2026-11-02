# Logging (Python's `logging` module)

## What it is

Logging is how a program writes down what it is doing, as short lines with a time, a severity and a message. Python's standard `logging` module separates three jobs: a **logger** is the object your code calls (`logger.warning(...)`); a **handler** decides where a record goes (a stream, a file); a **formatter** decides what the line looks like. A **record** is the object that carries one event between them. Severity levels, from least to most serious, are `DEBUG`, `INFO`, `WARNING`, `ERROR`.

## Why this repository uses it

The programs run unattended (tests, containers). Their output must be both readable and searchable. The repository writes **logfmt**: one line per event, `key=value` pairs separated by spaces, so a person can read it and `grep` or a log tool can split it. Output goes to standard error, so the programs' standard output stays clean for results.

## Where it appears

| File | Role |
|---|---|
| `src/rental_shop/infrastructure/logging.py` | The formatter, the `fields` helper and `configure_logging`. |
| `src/rental_shop/application/book_item.py`, `race.py`, `infrastructure/postgres.py` | Create loggers and write events. |
| `src/rental_shop/interfaces/*.py` | Call `configure_logging` at startup (see [argparse.md](argparse.md)). |
| `tests/unit/infrastructure/test_logging_and_shutdown.py` | Tests of the format (see [pytest.md](pytest.md)). |

## How it works underneath

`logging.getLogger("a.b")` returns the same logger object each time for the same name; names form a tree and a record travels from the logger up to the **root logger**, where handlers are normally attached. A logger or handler drops records below its level. The `extra=` argument of a logging call adds keys to the record as attributes, which is how this repository passes structured fields. Calls such as `logger.warning("item %d", item_id)` pass a **format string** and its values separately; the text is built only if the record is actually emitted.

## Walkthrough of this repository's use

```python
"""Structured logging: one logfmt line per event (`ts=... level=... logger=... msg=... key=value`)."""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any, TextIO

```

The docstring shows the line format. `json` is used only to quote text. `sys` gives `sys.stderr`. `UTC` is a constant for Coordinated Universal Time (no local time zone); `Any` and `TextIO` are type-hint names meaning "any value" and "a text stream such as a file".

```python
def _quote(value: object) -> str:
    text = str(value)
    return json.dumps(text) if not text or any(char in text for char in ' ="\n') else text

```

`_quote(value)` turns a value into text. `json.dumps(text)` wraps it in double quotes and escapes special characters. It is used when the text is empty or contains a space, an equals sign, a double quote or a newline (`any(char in text for char in ' ="\n')` checks each character); otherwise the plain text is returned. So `msg="retrying database connection"` is quoted and `level=INFO` is not.

```python
class LogfmtFormatter(logging.Formatter):
    """Format a log record as one logfmt line, with the record's extra fields as key=value pairs."""

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.fromtimestamp(record.created, tz=UTC).isoformat(timespec="milliseconds")
        parts = [
            f"ts={timestamp}",
            f"level={record.levelname}",
            f"logger={record.name}",
            f"msg={_quote(record.getMessage())}",
        ]
        parts.extend(f"{key}={_quote(value)}" for key, value in getattr(record, "fields", {}).items())
        if record.exc_info:
            parts.append(f"exc={_quote(self.formatException(record.exc_info))}")
        return " ".join(parts)
```

`LogfmtFormatter` subclasses `logging.Formatter` and overrides `format`, which turns a record into a string.

- `datetime.fromtimestamp(record.created, tz=UTC)` converts the record's creation time (seconds since 1970) into a time-zone-aware date and time; `isoformat(timespec="milliseconds")` prints it like `2026-11-02T09:55:01.123+00:00`.
- `parts` is a list of the four standard pairs: `ts`, `level` (`levelname`), `logger` (`name`) and `msg` (`getMessage()`, the final message after `%` values are filled in).
- `parts.extend(... for key, value in getattr(record, "fields", {}).items())` appends one pair per extra field. `getattr(record, "fields", {})` reads the attribute `fields` or, if it is absent, an empty dictionary; `.items()` yields the key-value pairs.
- If the record has `exc_info` (an error was being handled), the traceback text from `self.formatException` is added as `exc=`.
- `" ".join(parts)` glues the pairs with spaces.

```python
def fields(**values: Any) -> dict[str, Any]:
    """Use as `logger.info("message", extra=fields(order_id=...))` to attach key=value pairs."""
    return {"fields": values}

```

`fields(**values)` collects the keyword arguments into a dictionary named `values` (the `**` in a signature means "gather all named arguments"). It returns `{"fields": values}`, which is exactly the shape `extra=` needs: the record gets an attribute `fields` holding the dictionary. Usage: `logger.warning("retrying database connection", extra=fields(attempt=2))`.

```python
def configure_logging(level: str, stream: TextIO | None = None) -> None:
    """Send every log record to `stream` (stderr by default) as logfmt. Safe to call twice."""
    handler = logging.StreamHandler(stream or sys.stderr)
    handler.setFormatter(LogfmtFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
```

`configure_logging` builds the pipeline once. `logging.StreamHandler(stream or sys.stderr)` creates a handler that writes to the given stream or to standard error. `setFormatter` attaches the logfmt formatter. `logging.getLogger()` with no name is the root logger. `root.handlers[:] = [handler]` replaces the whole list of handlers in place, which is why it is safe to call twice (no duplicated lines). `root.setLevel(level)` sets the threshold from the `LOG_LEVEL` setting.

## Try it yourself

```bash
.venv/bin/python -c "
import logging
from rental_shop.infrastructure.logging import configure_logging, fields
configure_logging('INFO')
log = logging.getLogger('demo')
log.info('hello world', extra=fields(attempt=2, name='a b'))
log.debug('hidden')"
```
One line on standard error: `ts=... level=INFO logger=demo msg="hello world" attempt=2 name="a b"`. The debug event is dropped.

```bash
.venv/bin/python -m pytest tests/unit/infrastructure/test_logging_and_shutdown.py -q
```

```bash
.venv/bin/python -c "
import logging
from rental_shop.infrastructure.logging import configure_logging
configure_logging('INFO')
try:
    1 / 0
except ZeroDivisionError:
    logging.getLogger('demo').exception('failed')"
```
One line ending with `exc="Traceback (most recent call last): ..."`: the traceback is attached to the record as one quoted value.

## Mistakes people make

- **Building the message with an f-string** in the logging call; `%d` style arguments avoid work when the level is off.
- **Adding a handler on every call**, which duplicates lines. `configure_logging` replaces the list.
- **Logging secrets.** Settings hide the password from `repr` (see [python-stdlib.md](python-stdlib.md)), and no log line passes it.
- **Writing logs to standard output**, mixing them with program results.

## Check yourself

1. Which three jobs do logger, handler and formatter do? *Logger: called by code. Handler: chooses the destination. Formatter: shapes the line.*
2. What does `extra=fields(a=1)` produce? *A record with an attribute `fields` = `{"a": 1}`, which the formatter prints as `a=1`.*
3. Why `root.handlers[:] =`? *It replaces the handler list in place so a second call does not duplicate output.*
4. When does `_quote` add quotes? *When the text is empty or has a space, `=`, `"` or newline.*
5. Where do log lines go by default? *Standard error.*

## Further reading

- `logging` (Python 3.13): https://docs.python.org/3.13/library/logging.html
- Logging HOWTO: https://docs.python.org/3.13/howto/logging.html
- logfmt (informal format): https://brandur.org/logfmt
