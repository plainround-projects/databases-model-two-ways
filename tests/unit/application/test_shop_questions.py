from datetime import date

import pytest

from rental_shop.application.shop_questions import ShopQuestions, UnknownCustomerNameError
from rental_shop.domain.period import RentalPeriod

from .fakes import FixedClock, lesson_shop

WEEKEND = RentalPeriod(date(2026, 11, 7), date(2026, 11, 9))


def ask(today: date | None = date(2026, 11, 4), customer: str = "Ada"):
    return ShopQuestions(lesson_shop(), FixedClock(date(2026, 11, 4))).report(WEEKEND, customer, today)


def test_the_items_free_next_weekend_are_the_drill_and_the_kayak():
    assert [item.name for item in ask().free_items] == ["Drill", "Kayak"]


def test_adas_history_is_rentals_1_3_5_and_6():
    assert sorted(rental.rental_id for rental in ask().history) == [1, 3, 5, 6]


def test_the_history_is_in_date_order():
    assert [rental.rental_id for rental in ask().history] == [1, 3, 6, 5]


def test_todays_return_is_rental_1():
    due = ask().returns_today
    assert [(d.rental_id, d.item_name, d.customer_name) for d in due] == [(1, "Drill", "Ada")]


def test_revenue_per_item_and_month_matches_the_hand_check():
    rows = [(row.item_name, row.month, int(row.amount)) for row in ask().revenue]
    assert rows == [
        ("Drill", "2026-11", 50),
        ("Drill", "2026-12", 20),
        ("Ladder", "2026-10", 24),
        ("Ladder", "2026-11", 56),
        ("Tent", "2026-10", 45),
        ("Tent", "2026-11", 45),
    ]


def test_only_the_kayak_was_never_rented():
    assert [item.name for item in ask().never_rented] == ["Kayak"]


def test_today_comes_from_the_clock_when_not_given():
    assert ask(today=None).today == date(2026, 11, 4)


def test_an_unknown_customer_is_a_named_error():
    with pytest.raises(UnknownCustomerNameError, match="Zed"):
        ask(customer="Zed")
