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


@pytest.fixture
def connection(lab: PostgresSettings) -> Iterator[psycopg.Connection[Any]]:
    """A connection whose search path is the test's schema."""
    with postgres.session(lab) as db:
        yield db
