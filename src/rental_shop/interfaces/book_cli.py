"""Book an item for a customer.

python -m rental_shop.interfaces.book_cli --item 1 --customer 2 --from 2026-11-03 --days 2

Exit code 0 when booked, 3 when the dates are taken (the database refused), 2 for bad input or configuration.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from datetime import date

from ..application.book_item import BookItem
from ..domain.errors import InvalidPeriodError, ItemAlreadyBookedError, UnknownCustomerError, UnknownItemError
from ..infrastructure.postgres import session
from ..infrastructure.postgres_rentals import PostgresRentals
from .common import load_settings


def build_parser() -> argparse.ArgumentParser:
    """The command line of the book program."""
    parser = argparse.ArgumentParser(description="Book an item for a customer.")
    parser.add_argument("--item", type=int, required=True, help="item id")
    parser.add_argument("--customer", type=int, required=True, help="customer id")
    parser.add_argument(
        "--from", dest="first_day", type=date.fromisoformat, required=True, help="first rental day, YYYY-MM-DD"
    )
    parser.add_argument(
        "--days", type=int, required=True, help="number of rental days; the item comes back on the next day"
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Book once and say what happened in the shop's words."""
    arguments = build_parser().parse_args(argv)
    settings = load_settings()
    if settings is None:
        return 2
    with session(settings.postgres) as connection:
        book = BookItem(PostgresRentals(connection))
        try:
            rental = book(arguments.item, arguments.customer, arguments.first_day, arguments.days)
        except ItemAlreadyBookedError as error:
            print(f"already booked: {error}")
            return 3
        except (InvalidPeriodError, UnknownItemError, UnknownCustomerError) as error:
            print(f"cannot book: {error}")
            return 2
    print(f"booked rental {rental.rental_id}: item {rental.item_id} for {rental.period}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
