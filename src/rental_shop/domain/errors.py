"""Named errors of the domain."""

from __future__ import annotations


class RentalShopError(Exception):
    """Base class for every error the shop's rules raise."""


class InvalidPeriodError(RentalShopError, ValueError):
    """A rental period is empty, reversed or otherwise unusable."""


class ItemAlreadyBookedError(RentalShopError):
    """The item is already rented for dates that overlap the request (SQLSTATE 23P01 in PostgreSQL)."""

    def __init__(self, item_id: int, first_day: str, return_day: str) -> None:
        super().__init__(f"item {item_id} is already booked for dates overlapping {first_day} to {return_day}")
        self.item_id = item_id


class UnknownItemError(RentalShopError):
    """No item has this id."""

    def __init__(self, item_id: int) -> None:
        super().__init__(f"unknown item {item_id}")
        self.item_id = item_id


class UnknownCustomerError(RentalShopError):
    """No customer has this id."""

    def __init__(self, customer_id: int) -> None:
        super().__init__(f"unknown customer {customer_id}")
        self.customer_id = customer_id


class BookingDeadlockError(RentalShopError):
    """The database picked this booking as a deadlock victim (SQLSTATE 40P01); nothing was written, so a retry is safe.

    Two inserts for overlapping dates each wait for the other's uncommitted row while checking the exclusion
    constraint. PostgreSQL ends one of them after `deadlock_timeout`; the retry then meets the winner's committed row.
    """
