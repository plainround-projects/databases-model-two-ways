"""The PostgreSQL adapter and the schema's own rules, against the real database (make up first)."""

import threading
from datetime import date
from decimal import Decimal
from typing import Any

import psycopg
import pytest
from psycopg import errors
from psycopg.types.range import Range

from rental_shop.application.book_item import BookItem
from rental_shop.application.health import ProbeFailedError
from rental_shop.application.race import Race
from rental_shop.application.shop_questions import ShopQuestions
from rental_shop.domain.errors import ItemAlreadyBookedError, UnknownCustomerError, UnknownItemError
from rental_shop.domain.period import RentalPeriod
from rental_shop.infrastructure import postgres
from rental_shop.infrastructure.clock import SystemClock
from rental_shop.infrastructure.health_probes import PostgresSchemaProbe
from rental_shop.infrastructure.postgres_rentals import (
    INSERT_RENTAL,
    INSERT_RENTAL_SKIPPING_CLASH,
    InsertMode,
    PostgresRentals,
    gateway_opener,
)
from rental_shop.infrastructure.settings import PostgresSettings

from ..conftest import SQL

pytestmark = pytest.mark.integration


def period(first_day: str, return_day: str) -> RentalPeriod:
    return RentalPeriod(date.fromisoformat(first_day), date.fromisoformat(return_day))


@pytest.fixture
def rentals(connection: psycopg.Connection[Any]) -> PostgresRentals:
    return PostgresRentals(connection)


def test_an_overlapping_rental_is_refused_by_the_database_with_the_exclusion_sqlstate(
    connection: psycopg.Connection[Any],
):
    with pytest.raises(errors.ExclusionViolation) as raised:
        connection.execute(
            "INSERT INTO rentals (item_id, customer_id, during) VALUES (1, 2, daterange('2026-11-03', '2026-11-05'))"
        )
    assert raised.value.sqlstate == "23P01"
    assert raised.value.diag.constraint_name == "rentals_item_id_during_excl"


@pytest.mark.parametrize("mode", list(InsertMode))
def test_the_adapter_turns_a_clash_into_already_booked_in_both_insert_modes(
    connection: psycopg.Connection[Any], mode: InsertMode
):
    with pytest.raises(ItemAlreadyBookedError, match="item 1 is already booked"):
        PostgresRentals(connection, mode).book(1, 2, period("2026-11-03", "2026-11-05"))


@pytest.mark.parametrize("mode", list(InsertMode))
def test_a_clash_with_the_plain_insert_raises_23p01_and_with_on_conflict_returns_no_row(
    connection: psycopg.Connection[Any], mode: InsertMode
):
    statement = INSERT_RENTAL if mode is InsertMode.RAISE else INSERT_RENTAL_SKIPPING_CLASH
    values = (1, 2, Range(date(2026, 11, 3), date(2026, 11, 5), "[)"))
    if mode is InsertMode.RAISE:
        with pytest.raises(errors.ExclusionViolation):
            connection.execute(statement, values)
    else:
        assert connection.execute(statement, values).fetchone() is None


def test_a_rental_that_starts_on_the_return_day_is_accepted(rentals: PostgresRentals):
    rental = rentals.book(1, 2, period("2026-11-06", "2026-11-08"))
    assert rental.period == period("2026-11-06", "2026-11-08")
    assert rental.rental_id > 7


def test_the_same_dates_for_another_item_are_accepted(rentals: PostgresRentals):
    assert rentals.book(4, 1, period("2026-11-01", "2026-11-04")).item_id == 4


def test_a_refused_rental_leaves_nothing_behind(connection: psycopg.Connection[Any], rentals: PostgresRentals):
    with pytest.raises(ItemAlreadyBookedError):
        rentals.book(1, 2, period("2026-11-03", "2026-11-05"))
    assert connection.execute("SELECT count(*) FROM rentals").fetchone() == (7,)


def test_unknown_references_are_named(rentals: PostgresRentals):
    with pytest.raises(UnknownItemError):
        rentals.book(99, 1, period("2027-01-01", "2027-01-02"))
    with pytest.raises(UnknownCustomerError):
        rentals.book(4, 99, period("2027-01-01", "2027-01-02"))


def test_an_empty_range_violates_the_check(connection: psycopg.Connection[Any]):
    with pytest.raises(errors.CheckViolation):
        connection.execute("INSERT INTO rentals (item_id, customer_id, during) VALUES (4, 1, 'empty')")


def test_postgres_stores_a_closed_range_as_half_open(connection: psycopg.Connection[Any]):
    row = connection.execute("SELECT '[2026-11-01,2026-11-04]'::daterange::text").fetchone()
    assert row == ("[2026-11-01,2026-11-05)",)


def test_a_closed_range_makes_a_touching_rental_clash(connection: psycopg.Connection[Any]):
    connection.execute("INSERT INTO rentals (item_id, customer_id, during) VALUES (4, 1, '[2026-11-01,2026-11-04]')")
    with pytest.raises(errors.ExclusionViolation):
        connection.execute(
            "INSERT INTO rentals (item_id, customer_id, during) VALUES (4, 2, daterange('2026-11-04', '2026-11-06'))"
        )


def test_the_five_questions_have_the_hand_checked_answers(rentals: PostgresRentals):
    report = ShopQuestions(rentals, SystemClock()).report(period("2026-11-07", "2026-11-09"), "Ada", date(2026, 11, 4))
    assert [item.name for item in report.free_items] == ["Drill", "Kayak"]
    assert sorted(rental.rental_id for rental in report.history) == [1, 3, 5, 6]
    assert [(due.rental_id, due.item_name, due.customer_name) for due in report.returns_today] == [(1, "Drill", "Ada")]
    assert [(row.item_name, row.month, row.amount) for row in report.revenue] == [
        ("Drill", "2026-11", Decimal("50.00")),
        ("Drill", "2026-12", Decimal("20.00")),
        ("Ladder", "2026-10", Decimal("24.00")),
        ("Ladder", "2026-11", Decimal("56.00")),
        ("Tent", "2026-10", Decimal("45.00")),
        ("Tent", "2026-11", Decimal("45.00")),
    ]
    assert [item.name for item in report.never_rented] == ["Kayak"]


def test_one_item_can_be_asked_about_alone(rentals: PostgresRentals):
    weekend = period("2026-11-07", "2026-11-09")
    assert not rentals.is_item_free(2, weekend)
    assert rentals.is_item_free(1, weekend)


def test_a_customer_is_found_by_name_only_when_there_is_exactly_one(rentals: PostgresRentals):
    assert rentals.find_customer("Ada") is not None
    assert rentals.find_customer("Nobody") is None
    rentals.add_customer("Ada")
    assert rentals.find_customer("Ada") is None


def test_items_and_customers_can_be_added_with_generated_ids(rentals: PostgresRentals):
    assert rentals.add_item("Saw", Decimal("7.50")).item_id == 5
    assert rentals.add_customer("Cleo").customer_id == 3


def test_the_script_of_queries_runs_as_written(connection: psycopg.Connection[Any]):
    connection.execute((SQL / "003_queries.sql").read_text())


def test_the_document_design_accepts_the_double_booking_the_relational_design_refuses(
    connection: psycopg.Connection[Any],
):
    connection.execute((SQL / "document_model" / "001_documents.sql").read_text())
    connection.execute((SQL / "document_model" / "002_double_booking.sql").read_text())
    booked = connection.execute(
        "SELECT jsonb_array_length(doc->'booked') FROM item_documents WHERE item_id = 1"
    ).fetchone()
    assert booked == (2,)


def test_every_statement_is_bounded_by_the_statement_timeout(lab: PostgresSettings):
    import dataclasses

    impatient = dataclasses.replace(lab, statement_timeout_ms=100)
    with postgres.session(impatient) as connection, pytest.raises(errors.QueryCanceled):
        connection.execute("SELECT pg_sleep(2)")


def test_a_connection_to_nowhere_gives_up_after_its_retries(lab: PostgresSettings):
    import dataclasses

    unreachable = dataclasses.replace(lab, port=1, connect_timeout_seconds=1)
    with pytest.raises(psycopg.OperationalError):
        postgres.connect(unreachable, attempts=2)


def test_the_health_probe_passes_on_the_lab_schema(lab: PostgresSettings):
    assert "exclusion constraint" in PostgresSchemaProbe(lab).check()


def test_the_health_probe_names_what_is_missing(lab: PostgresSettings, connection: psycopg.Connection[Any]):
    connection.execute("ALTER TABLE rentals DROP CONSTRAINT rentals_item_id_during_excl")
    with pytest.raises(ProbeFailedError, match="exclusion constraint"):
        PostgresSchemaProbe(lab).check()
    connection.execute("DROP TABLE rentals")
    with pytest.raises(ProbeFailedError, match="missing tables"):
        PostgresSchemaProbe(lab).check()


def test_twenty_connections_racing_for_the_same_item_give_exactly_one_winner_and_nineteen_refusals(
    lab: PostgresSettings,
):
    race = Race(gateway_opener(lab), contenders=20)
    tallies = [race.run_round(str(run)) for run in range(3)]
    assert all(tally.is_correct for tally in tallies), tallies


def test_with_a_plain_insert_one_contender_still_wins_whatever_happens_to_the_others(lab: PostgresSettings):
    race = Race(gateway_opener(lab, InsertMode.RAISE), contenders=20)
    tallies = [race.run_round(str(run)) for run in range(3)]
    assert all(tally.one_winner and tally.failed == 0 for tally in tallies), tallies


def test_two_sessions_booking_the_same_dates_at_once_never_both_win(lab: PostgresSettings):
    barrier = threading.Barrier(2)
    results: list[str] = []

    def contend(customer_id: int) -> None:
        with gateway_opener(lab)() as session:
            barrier.wait()
            try:
                BookItem(session)(4, customer_id, date(2027, 3, 1), 3)
                results.append("won")
            except ItemAlreadyBookedError:
                results.append("refused")

    threads = [threading.Thread(target=contend, args=(customer,)) for customer in (1, 2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(results) == ["refused", "won"]
