"""In-memory stand-ins for the ports, so use cases are tested without a database."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from rental_shop.domain.errors import (
    BookingDeadlockError,
    ItemAlreadyBookedError,
    UnknownCustomerError,
    UnknownItemError,
)
from rental_shop.domain.model import Customer, Item, MonthlyRevenue, Rental, ReturnDue
from rental_shop.domain.period import RentalPeriod


@dataclass
class InMemoryShop:
    """A rental shop in memory that refuses overlaps the way the exclusion constraint does, under one lock."""

    items: dict[int, Item] = field(default_factory=dict)
    customers: dict[int, Customer] = field(default_factory=dict)
    rentals: list[Rental] = field(default_factory=list)
    deadlocks_to_raise: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)

    def book(self, item_id: int, customer_id: int, period: RentalPeriod) -> Rental:
        with self.lock:
            if self.deadlocks_to_raise > 0:
                self.deadlocks_to_raise -= 1
                raise BookingDeadlockError("deadlock")
            if item_id not in self.items:
                raise UnknownItemError(item_id)
            if customer_id not in self.customers:
                raise UnknownCustomerError(customer_id)
            if any(r.item_id == item_id and r.period.overlaps(period) for r in self.rentals):
                raise ItemAlreadyBookedError(item_id, period.first_day.isoformat(), period.return_day.isoformat())
            rental = Rental(len(self.rentals) + 1, item_id, customer_id, period)
            self.rentals.append(rental)
            return rental

    def add_item(self, name: str, daily_rate: Decimal) -> Item:
        with self.lock:
            item = Item(len(self.items) + 1, name, daily_rate)
            self.items[item.item_id] = item
            return item

    def add_customer(self, name: str) -> Customer:
        with self.lock:
            customer = Customer(len(self.customers) + 1, name)
            self.customers[customer.customer_id] = customer
            return customer

    def is_item_free(self, item_id: int, period: RentalPeriod) -> bool:
        return not any(r.item_id == item_id and r.period.overlaps(period) for r in self.rentals)

    def free_items(self, period: RentalPeriod) -> list[Item]:
        return [item for item in self.items.values() if self.is_item_free(item.item_id, period)]

    def history(self, customer_id: int) -> list[Rental]:
        return sorted((r for r in self.rentals if r.customer_id == customer_id), key=lambda r: (r.period, r.rental_id))

    def returns_on(self, day: date) -> list[ReturnDue]:
        return [
            ReturnDue(r.rental_id, self.items[r.item_id].name, self.customers[r.customer_id].name)
            for r in self.rentals
            if r.period.return_day == day
        ]

    def revenue_by_item_and_month(self) -> list[MonthlyRevenue]:
        totals: dict[tuple[str, str], Decimal] = {}
        for r in self.rentals:
            item = self.items[r.item_id]
            key = (item.name, r.period.first_day.strftime("%Y-%m"))
            totals[key] = totals.get(key, Decimal(0)) + item.daily_rate * r.period.days
        return [MonthlyRevenue(name, month, amount) for (name, month), amount in sorted(totals.items())]

    def never_rented(self) -> list[Item]:
        rented = {r.item_id for r in self.rentals}
        return [item for item in self.items.values() if item.item_id not in rented]

    def find_customer(self, name: str) -> Customer | None:
        matches = [c for c in self.customers.values() if c.name == name]
        return matches[0] if len(matches) == 1 else None

    @contextmanager
    def open(self) -> Iterator[InMemoryShop]:
        """Plays the part of `GatewayOpener`: every contender shares the one shop, as connections share a database."""
        yield self


class FixedClock:
    """A clock that always says the same day."""

    def __init__(self, day: date) -> None:
        self._day = day

    def today(self) -> date:
        return self._day


def lesson_shop() -> InMemoryShop:
    """The lesson's hand-checkable data: 2 customers, 4 items, 7 rentals."""
    shop = InMemoryShop()
    for name in ("Ada", "Bruno"):
        shop.add_customer(name)
    for name, rate in (("Drill", 10), ("Ladder", 8), ("Tent", 15), ("Kayak", 20)):
        shop.add_item(name, Decimal(rate))

    def day(text: str) -> date:
        return date.fromisoformat(text)

    for item_id, customer_id, first, last in (
        (1, 1, "2026-11-01", "2026-11-04"),
        (1, 2, "2026-11-04", "2026-11-06"),
        (2, 1, "2026-11-02", "2026-11-09"),
        (3, 2, "2026-10-20", "2026-10-23"),
        (1, 1, "2026-12-01", "2026-12-03"),
        (3, 1, "2026-11-07", "2026-11-10"),
        (2, 2, "2026-10-25", "2026-10-28"),
    ):
        shop.book(item_id, customer_id, RentalPeriod(day(first), day(last)))
    return shop
