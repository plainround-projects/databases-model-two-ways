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
