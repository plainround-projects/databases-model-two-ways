import random
from datetime import date

import pytest

from rental_shop.application.book_item import BookItem
from rental_shop.domain.errors import (
    BookingDeadlockError,
    InvalidPeriodError,
    ItemAlreadyBookedError,
    UnknownCustomerError,
    UnknownItemError,
)

from .fakes import lesson_shop

NOV_3 = date(2026, 11, 3)


def test_a_free_item_is_booked_and_the_rental_comes_back():
    shop = lesson_shop()
    rental = BookItem(shop)(4, 1, NOV_3, 2)
    assert (rental.item_id, rental.customer_id, str(rental.period)) == (4, 1, "2026-11-03 to 2026-11-05")


def test_overlapping_dates_are_refused_with_a_message_naming_the_item():
    with pytest.raises(ItemAlreadyBookedError, match="item 1 is already booked"):
        BookItem(lesson_shop())(1, 2, NOV_3, 2)


def test_a_rental_that_starts_on_the_return_day_is_allowed():
    rental = BookItem(lesson_shop())(1, 2, date(2026, 11, 6), 2)
    assert str(rental.period) == "2026-11-06 to 2026-11-08"


def test_a_period_that_cannot_exist_is_refused_before_the_database_is_asked():
    shop = lesson_shop()
    with pytest.raises(InvalidPeriodError):
        BookItem(shop)(4, 1, NOV_3, 0)
    assert len(shop.rentals) == 7


def test_unknown_references_are_named():
    with pytest.raises(UnknownItemError):
        BookItem(lesson_shop())(99, 1, NOV_3, 1)
    with pytest.raises(UnknownCustomerError):
        BookItem(lesson_shop())(4, 99, NOV_3, 1)


def test_a_deadlock_victim_is_retried_with_doubling_pauses_inside_the_jitter_band():
    shop = lesson_shop()
    shop.deadlocks_to_raise = 3
    pauses: list[float] = []
    retried: list[int] = []
    book = BookItem(shop, pause_seconds=0.1, sleep=pauses.append, on_retry=retried.append, rng=random.Random(1))
    book(4, 1, NOV_3, 1)
    for pause, ceiling in zip(pauses, (0.1, 0.2, 0.4), strict=True):
        assert ceiling * 0.5 <= pause <= ceiling
    assert retried == [1, 2, 3]
    assert len(shop.rentals) == 8


def test_a_retry_after_a_deadlock_can_still_be_refused_as_booked():
    shop = lesson_shop()
    shop.deadlocks_to_raise = 1
    with pytest.raises(ItemAlreadyBookedError):
        BookItem(shop, sleep=lambda _: None)(1, 2, NOV_3, 2)


def test_the_deadlock_is_raised_when_every_attempt_loses():
    shop = lesson_shop()
    shop.deadlocks_to_raise = 10
    with pytest.raises(BookingDeadlockError):
        BookItem(shop, attempts=3, sleep=lambda _: None)(4, 1, NOV_3, 1)
    assert shop.deadlocks_to_raise == 7
