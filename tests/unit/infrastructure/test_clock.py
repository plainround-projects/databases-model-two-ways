from datetime import date

from rental_shop.infrastructure.clock import SystemClock


def test_the_system_clock_reports_a_date():
    assert isinstance(SystemClock().today(), date)
