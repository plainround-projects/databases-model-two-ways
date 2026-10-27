"""Use case: race several connections for the same item and the same dates (lesson step 5)."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from ..domain.errors import BookingDeadlockError, ItemAlreadyBookedError
from ..domain.model import RaceTally
from ..domain.period import RentalPeriod
from .book_item import BookItem
from .ports import GatewayOpener

logger = logging.getLogger(__name__)

CONTENDER_STAGGER_DAYS = 3  # contenders start up to two days apart; every pair of their periods still overlaps
CONTENDER_LENGTH_DAYS = 4
BARRIER_TIMEOUT_SECONDS = 30.0


@dataclass(frozen=True, slots=True)
class Race:
    """Runs rounds in which `contenders` independent connections book one fresh item at the same instant.

    Each contender opens its own session before a barrier releases them all, so the inserts really run at the same
    time. There is no lock in the application: the exclusion constraint has to pick the one winner.
    """

    open_session: GatewayOpener
    contenders: int = 20
    first_day: date = date(2027, 1, 4)
    sleep: Callable[[float], None] = time.sleep

    def run_round(self, label: str) -> RaceTally:
        """One round against a new item, with distinct but pairwise overlapping periods. Returns the tally."""
        with self.open_session() as setup:
            item = setup.add_item(f"Race item {label}", Decimal("10.00"))
            customer = setup.add_customer(f"Racer {label}")
        barrier = threading.Barrier(self.contenders)
        outcomes: list[str] = []
        retries = [0]
        guard = threading.Lock()

        def count_retry(_attempt: int) -> None:
            with guard:
                retries[0] += 1

        def contend(index: int) -> None:
            period = RentalPeriod.starting(self.first_day, CONTENDER_LENGTH_DAYS).shifted(
                index % CONTENDER_STAGGER_DAYS
            )
            result = "failed"
            released = False
            try:
                with self.open_session() as session:
                    barrier.wait(timeout=BARRIER_TIMEOUT_SECONDS)
                    released = True
                    BookItem(session, sleep=self.sleep, on_retry=count_retry)(
                        item.item_id, customer.customer_id, period.first_day, period.days
                    )
                    result = "success"
            except ItemAlreadyBookedError:
                result = "refused"
            except BookingDeadlockError:
                result = "deadlocked"
            except threading.BrokenBarrierError:
                logger.error("contender %d could not reach the barrier", index)
            except Exception:
                logger.exception("a contender failed for a reason other than the constraint")
            finally:
                if not released:
                    barrier.abort()  # a contender that never reached the barrier must not leave the others waiting
            with guard:
                outcomes.append(result)

        threads = [
            threading.Thread(target=contend, args=(index,), name=f"contender-{index}")
            for index in range(self.contenders)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        return RaceTally(
            contenders=self.contenders,
            successes=outcomes.count("success"),
            refused=outcomes.count("refused"),
            failed=outcomes.count("failed"),
            deadlocked=outcomes.count("deadlocked"),
            deadlock_retries=retries[0],
        )
