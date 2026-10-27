"""The lesson's scenario through the command-line programs, as the Makefile runs them (make up first)."""

import os
import re
import subprocess
import sys

import pytest

from rental_shop.infrastructure.settings import PostgresSettings

pytestmark = pytest.mark.e2e


def program(module: str, lab: PostgresSettings, *args: str) -> subprocess.CompletedProcess[str]:
    environment = {**os.environ, "POSTGRES_SCHEMA": lab.schema}
    return subprocess.run(
        [sys.executable, "-m", f"rental_shop.interfaces.{module}", *args],
        capture_output=True,
        text=True,
        env=environment,
        timeout=300,
        check=False,
    )


def test_the_report_prints_the_lessons_expected_answers(lab: PostgresSettings):
    result = program("report_cli", lab)
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        "free next weekend: Drill, Kayak",
        "Ada's history: 1, 3, 5 and 6",
        "returns on 2026-11-04: rental 1 (Drill, Ada)",
        "revenue per item and month: Drill 2026-11 50.00 | Drill 2026-12 20.00 | Ladder 2026-10 24.00 | "
        "Ladder 2026-11 56.00 | Tent 2026-10 45.00 | Tent 2026-11 45.00",
        "never rented: Kayak",
    ]


def test_an_overlap_is_refused_a_touching_range_is_booked_and_the_exit_codes_say_so(lab: PostgresSettings):
    refused = program("book_cli", lab, "--item", "1", "--customer", "2", "--from", "2026-11-03", "--days", "2")
    assert refused.returncode == 3
    assert "already booked" in refused.stdout

    touching = program("book_cli", lab, "--item", "1", "--customer", "2", "--from", "2026-11-06", "--days", "2")
    assert touching.returncode == 0, touching.stderr
    # the refused insert used up a number from the identity sequence, so the new rental is 9, not 8
    assert re.fullmatch(r"booked rental (8|9): item 1 for 2026-11-06 to 2026-11-08\n", touching.stdout)

    nonsense = program("book_cli", lab, "--item", "1", "--customer", "2", "--from", "2026-11-06", "--days", "0")
    assert nonsense.returncode == 2


def test_twenty_races_of_twenty_connections_each_have_exactly_one_winner(lab: PostgresSettings):
    result = program("race_cli", lab, "--runs", "20")
    assert result.returncode == 0, result.stderr + result.stdout
    lines = [line for line in result.stdout.splitlines() if line.startswith("run ")]
    assert len(lines) == 20
    assert all(
        line == f"run {number:2d}: 1 success, 19 refused by the exclusion constraint"
        for number, line in enumerate(lines, 1)
    )
    assert "20 of 20 runs had exactly one winner" in result.stdout


def test_the_plain_insert_race_also_has_one_winner_each_time_whatever_happens_to_the_others(lab: PostgresSettings):
    result = program("race_cli", lab, "--runs", "5", "--insert", "raise")
    assert result.returncode == 0, result.stderr + result.stdout
    lines = [line for line in result.stdout.splitlines() if line.startswith("run ")]
    assert len(lines) == 5
    assert all(": 1 success, " in line for line in lines)
    assert "5 of 5 runs had exactly one winner" in result.stdout


def test_the_health_command_is_green_on_the_lab_and_red_without_a_password(lab: PostgresSettings):
    assert program("health_cli", lab).returncode == 0
    broken = subprocess.run(
        [sys.executable, "-m", "rental_shop.interfaces.health_cli"],
        capture_output=True,
        text=True,
        env={key: value for key, value in os.environ.items() if key != "POSTGRES_PASSWORD"},
        timeout=60,
        check=False,
    )
    assert broken.returncode == 2
    assert "POSTGRES_PASSWORD" in broken.stderr
