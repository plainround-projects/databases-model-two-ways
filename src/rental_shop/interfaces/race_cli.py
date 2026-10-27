"""Race 20 connections for one item on overlapping dates, 20 times (lesson step 5).

python -m rental_shop.interfaces.race_cli [--runs 20] [--contenders 20]
Exit code 0 only when every run has exactly one winner. With the default insert (ON CONFLICT DO NOTHING) every
other contender is refused by the exclusion constraint; with --insert raise (the lesson's plain INSERT) a contender
may instead be a deadlock victim, which is counted and retried.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from ..application.race import Race
from ..domain.model import RaceTally
from ..infrastructure.postgres_rentals import InsertMode, gateway_opener
from ..infrastructure.shutdown import ShutdownSignal
from .common import load_settings


def build_parser() -> argparse.ArgumentParser:
    """The command line of the race program."""
    parser = argparse.ArgumentParser(description="Race connections for the same item and overlapping dates.")
    parser.add_argument("--runs", type=int, default=20, help="rounds, each against a fresh item (default 20)")
    parser.add_argument("--contenders", type=int, default=20, help="concurrent connections per round (default 20)")
    parser.add_argument(
        "--insert",
        choices=[mode.value for mode in InsertMode],
        default=InsertMode.SKIP.value,
        help="skip: INSERT ... ON CONFLICT DO NOTHING (default); raise: a plain INSERT that raises 23P01",
    )
    return parser


def describe(run: int, tally: RaceTally, mode: InsertMode) -> str:
    """One line per round: the winner, how the others were refused, and anything unusual."""
    refusal = "exclusion violations (23P01)" if mode is InsertMode.RAISE else "refused by the exclusion constraint"
    line = f"run {run:2d}: {tally.successes} success, {tally.refused} {refusal}"
    if tally.deadlocked:
        line += f", {tally.deadlocked} gave up after deadlocks"
    if tally.failed:
        line += f", {tally.failed} other failures"
    if tally.deadlock_retries:
        line += f" [{tally.deadlock_retries} deadlock retries]"
    return line


def main(argv: Sequence[str] | None = None) -> int:
    """Run the rounds, print one line per round, stop cleanly on SIGINT or SIGTERM between rounds."""
    arguments = build_parser().parse_args(argv)
    if arguments.runs < 1 or arguments.contenders < 2:
        print("--runs must be at least 1 and --contenders at least 2")
        return 2
    settings = load_settings()
    if settings is None:
        return 2
    shutdown = ShutdownSignal()
    shutdown.install()
    race = Race(gateway_opener(settings.postgres, InsertMode(arguments.insert)), contenders=arguments.contenders)
    correct = 0
    done = 0
    for run in range(1, arguments.runs + 1):
        if shutdown.requested:
            print("stopped by signal")
            break
        tally = race.run_round(f"{run}")
        done += 1
        correct += tally.one_winner
        print(describe(run, tally, InsertMode(arguments.insert)))
    print(f"{correct} of {done} runs had exactly one winner")
    return 0 if done == arguments.runs and correct == done else 1


if __name__ == "__main__":
    raise SystemExit(main())
