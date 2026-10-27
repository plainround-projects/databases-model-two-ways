"""Ports: what the use cases need from the outside world. Adapters in `infrastructure` implement them."""

from __future__ import annotations

from contextlib import AbstractContextManager
from datetime import date
from decimal import Decimal
from typing import Protocol

from ..domain.model import Customer, Item, MonthlyRevenue, Rental, ReturnDue
from ..domain.period import RentalPeriod


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
