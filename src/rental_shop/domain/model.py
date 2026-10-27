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
