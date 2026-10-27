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

    return retry(
        open_connection,
        attempts=attempts,
        base_delay_seconds=0.5,
        retry_on=(psycopg.OperationalError,),
        on_retry=lambda attempt, error: logger.warning(
            "retrying database connection", extra=fields(attempt=attempt, error=error)
        ),
    )


@contextmanager
def session(settings: PostgresSettings) -> Iterator[psycopg.Connection[Any]]:
    """A connection that is always closed, also when the block raises."""
    connection = connect(settings)
    try:
        yield connection
    finally:
        connection.close()
