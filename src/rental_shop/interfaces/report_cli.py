"""Answer the shop's five questions: python -m rental_shop.interfaces.report_cli [--today 2026-11-04] [--customer Ada]

The defaults are the lesson's hand-checked inputs; the output on the seed data is the lesson's expected output.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from datetime import date

from ..application.shop_questions import ShopQuestions, ShopReport, UnknownCustomerNameError
from ..domain.errors import InvalidPeriodError
from ..domain.model import Rental
from ..domain.period import RentalPeriod
from ..infrastructure.clock import SystemClock
from ..infrastructure.postgres import session
from ..infrastructure.postgres_rentals import PostgresRentals
from .common import load_settings


def build_parser() -> argparse.ArgumentParser:
    """The command line of the report program."""
    parser = argparse.ArgumentParser(description="Answer the rental shop's five questions.")
    parser.add_argument(
        "--today", type=date.fromisoformat, default=date(2026, 11, 4), help="the day for today's returns"
    )
    parser.add_argument(
        "--weekend-from", type=date.fromisoformat, default=date(2026, 11, 7), help="first day of the weekend"
    )
    parser.add_argument(
        "--weekend-to", type=date.fromisoformat, default=date(2026, 11, 9), help="day after the weekend"
    )
    parser.add_argument("--customer", default="Ada", help="customer whose history to show")
    return parser


def _join(words: list[str]) -> str:
    return ", ".join(words) if words else "(none)"


def _ids(rentals: list[Rental]) -> str:
    ids = [str(rental.rental_id) for rental in sorted(rentals, key=lambda rental: rental.rental_id)]
    return "none" if not ids else ", ".join(ids[:-1]) + (" and " if len(ids) > 1 else "") + ids[-1]


def format_report(report: ShopReport) -> list[str]:
    """The five answers as lines, in the order of the lesson's expected output."""
    returns = [f"rental {due.rental_id} ({due.item_name}, {due.customer_name})" for due in report.returns_today]
    revenue = " | ".join(f"{row.item_name} {row.month} {row.amount:.2f}" for row in report.revenue)
    return [
        f"free next weekend: {_join([item.name for item in report.free_items])}",
        f"{report.customer.name}'s history: {_ids(report.history)}",
        f"returns on {report.today.isoformat()}: {_join(returns)}",
        f"revenue per item and month: {revenue}",
        f"never rented: {_join([item.name for item in report.never_rented])}",
    ]


def main(argv: Sequence[str] | None = None) -> int:
    """Print the five answers."""
    arguments = build_parser().parse_args(argv)
    settings = load_settings()
    if settings is None:
        return 2
    try:
        weekend = RentalPeriod(arguments.weekend_from, arguments.weekend_to)
        with session(settings.postgres) as connection:
            questions = ShopQuestions(PostgresRentals(connection), SystemClock())
            report = questions.report(weekend, arguments.customer, arguments.today)
    except (InvalidPeriodError, UnknownCustomerNameError) as error:
        print(f"cannot answer: {error}")
        return 2
    print("\n".join(format_report(report)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
