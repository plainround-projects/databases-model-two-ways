from datetime import date

import pytest

from rental_shop.domain.errors import InvalidPeriodError
from rental_shop.domain.model import MonthlyRevenue, RaceTally
from rental_shop.domain.period import RentalPeriod

NOV_1 = date(2026, 11, 1)


def period(first_day: int, return_day: int) -> RentalPeriod:
    return RentalPeriod(date(2026, 11, first_day), date(2026, 11, return_day))


def test_a_period_counts_rental_days_without_the_return_day():
    assert period(1, 4).days == 3


def test_overlapping_periods_clash():
    assert period(1, 4).overlaps(period(3, 5))
    assert period(3, 5).overlaps(period(1, 4))


def test_a_period_inside_another_overlaps_it():
    assert period(1, 10).overlaps(period(3, 5))


def test_periods_that_only_touch_do_not_overlap():
    assert not period(1, 4).overlaps(period(4, 6))
    assert not period(4, 6).overlaps(period(1, 4))


def test_distant_periods_do_not_overlap():
    assert not period(1, 4).overlaps(period(10, 12))


def test_a_period_must_end_after_it_starts():
    with pytest.raises(InvalidPeriodError, match="after the first day"):
        period(4, 4)
    with pytest.raises(InvalidPeriodError):
        period(5, 3)


def test_starting_builds_a_period_from_a_length():
    assert RentalPeriod.starting(NOV_1, 3) == period(1, 4)


def test_a_rental_lasts_at_least_one_day():
    with pytest.raises(InvalidPeriodError, match="at least one day"):
        RentalPeriod.starting(NOV_1, 0)


def test_shifting_keeps_the_length():
    shifted = period(1, 4).shifted(2)
    assert shifted == period(3, 6)
    assert shifted.days == 3
    assert period(3, 6).shifted(-2) == period(1, 4)


def test_a_period_prints_as_its_two_dates():
    assert str(period(1, 4)) == "2026-11-01 to 2026-11-04"


def test_periods_sort_by_first_day():
    assert sorted([period(5, 6), period(1, 2)]) == [period(1, 2), period(5, 6)]


def test_revenue_names_its_month_as_year_and_month():
    assert MonthlyRevenue.of("Drill", date(2026, 12, 3), 20).month == "2026-12"  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("successes", "refused", "failed", "deadlocked", "correct"),
    [
        (1, 19, 0, 0, True),
        (2, 18, 0, 0, False),
        (0, 19, 1, 0, False),
        (1, 18, 1, 0, False),
        (1, 18, 0, 1, False),
        (0, 20, 0, 0, False),
    ],
)
def test_a_race_is_correct_only_with_exactly_one_winner_and_nothing_else_wrong(
    successes, refused, failed, deadlocked, correct
):
    assert RaceTally(20, successes, refused, failed, deadlocked).is_correct is correct


def test_one_winner_is_the_safety_property_even_when_some_contenders_gave_up():
    assert RaceTally(20, 1, 15, 0, 4).one_winner
    assert not RaceTally(20, 2, 18, 0, 0).one_winner
