"""Use case: book an item. The database decides; the application reports the refusal in the shop's words."""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date

from ..domain.errors import BookingDeadlockError
from ..domain.model import Rental
from ..domain.period import RentalPeriod
from .ports import RentalBooking

logger = logging.getLogger(__name__)


def _ignore(_attempt: int) -> None:
    """Default for `on_retry`: nothing to report."""


@dataclass(frozen=True, slots=True)
class BookItem:
    """Books an item for a customer. There is no availability check here on purpose: checking and then inserting
    races (two requests both see "free"), so the insert is the check and the database's constraint is the rule.

    A booking the database ended as a deadlock victim wrote nothing, so it is tried again (up to `attempts` times).
    The pause doubles each time and is scaled by a random factor in [0.5, 1.0], so victims do not come back in step
    and start a new deadlock; the retry then meets the winner's row and is refused as already booked.
    """

    rentals: RentalBooking
    attempts: int = 8
    pause_seconds: float = 0.05
    sleep: Callable[[float], None] = time.sleep
    rng: random.Random = field(default_factory=random.Random)
    on_retry: Callable[[int], None] = field(default=_ignore)

    def __call__(self, item_id: int, customer_id: int, first_day: date, days: int) -> Rental:
        """Raises `InvalidPeriodError` for a period that cannot exist, `ItemAlreadyBookedError` when the dates are
        taken, `BookingDeadlockError` when every attempt was a deadlock victim."""
        period = RentalPeriod.starting(first_day, days)
        for attempt in range(1, self.attempts + 1):
            try:
                return self.rentals.book(item_id, customer_id, period)
            except BookingDeadlockError:
                if attempt == self.attempts:
                    raise
                logger.warning("retrying booking after a deadlock: item %d, attempt %d", item_id, attempt)
                self.on_retry(attempt)
                self.sleep(self.pause_seconds * 2 ** (attempt - 1) * self.rng.uniform(0.5, 1.0))
        raise AssertionError("unreachable")  # pragma: no cover
