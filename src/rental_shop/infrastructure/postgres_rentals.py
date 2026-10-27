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


class PostgresRentals:
    """One connection's view of the rental database.

    Not safe to share between threads: give each thread its own connection and its own `PostgresRentals`.
    """

    def __init__(self, connection: psycopg.Connection[Any], insert_mode: InsertMode = InsertMode.SKIP) -> None:
        self._connection = connection
        self._insert = INSERT_RENTAL if insert_mode is InsertMode.RAISE else INSERT_RENTAL_SKIPPING_CLASH

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


def gateway_opener(settings: PostgresSettings, insert_mode: InsertMode = InsertMode.SKIP) -> GatewayOpener:
    """An opener that gives every caller its own connection, closed when the caller's block ends."""

    @contextmanager
    def open_gateway() -> Iterator[RentalGateway]:
        with session(settings) as connection:
            yield PostgresRentals(connection, insert_mode)

    return open_gateway
