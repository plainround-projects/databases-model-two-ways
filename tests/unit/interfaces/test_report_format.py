from datetime import date

from rental_shop.application.shop_questions import ShopQuestions
from rental_shop.domain.period import RentalPeriod
from rental_shop.interfaces.book_cli import build_parser as book_parser
from rental_shop.interfaces.race_cli import build_parser as race_parser
from rental_shop.interfaces.report_cli import build_parser as report_parser
from rental_shop.interfaces.report_cli import format_report

from ..application.fakes import FixedClock, lesson_shop


def test_the_report_prints_the_lessons_expected_output():
    report = ShopQuestions(lesson_shop(), FixedClock(date(2026, 11, 4))).report(
        RentalPeriod(date(2026, 11, 7), date(2026, 11, 9)), "Ada"
    )
    assert format_report(report) == [
        "free next weekend: Drill, Kayak",
        "Ada's history: 1, 3, 5 and 6",
        "returns on 2026-11-04: rental 1 (Drill, Ada)",
        "revenue per item and month: Drill 2026-11 50.00 | Drill 2026-12 20.00 | Ladder 2026-10 24.00 | "
        "Ladder 2026-11 56.00 | Tent 2026-10 45.00 | Tent 2026-11 45.00",
        "never rented: Kayak",
    ]


def test_an_empty_answer_reads_as_none():
    shop = lesson_shop()
    shop.rentals.clear()
    report = ShopQuestions(shop, FixedClock(date(2026, 11, 4))).report(
        RentalPeriod(date(2026, 11, 7), date(2026, 11, 9)), "Ada"
    )
    lines = format_report(report)
    assert lines[1] == "Ada's history: none"
    assert lines[2] == "returns on 2026-11-04: (none)"


def test_the_report_defaults_are_the_lessons_hand_checked_inputs():
    arguments = report_parser().parse_args([])
    assert (arguments.today, arguments.weekend_from, arguments.weekend_to, arguments.customer) == (
        date(2026, 11, 4),
        date(2026, 11, 7),
        date(2026, 11, 9),
        "Ada",
    )


def test_the_book_program_needs_an_item_a_customer_a_date_and_a_length():
    arguments = book_parser().parse_args(["--item", "1", "--customer", "2", "--from", "2026-11-03", "--days", "2"])
    assert (arguments.item, arguments.customer, arguments.first_day, arguments.days) == (1, 2, date(2026, 11, 3), 2)


def test_the_race_defaults_to_twenty_runs_of_twenty_connections():
    arguments = race_parser().parse_args([])
    assert (arguments.runs, arguments.contenders) == (20, 20)
