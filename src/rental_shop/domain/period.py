"""The half-open rental period: the first rental day up to, not including, the day the item comes back."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from .errors import InvalidPeriodError


@dataclass(frozen=True, slots=True, order=True)
class RentalPeriod:
    """Dates `[first_day, return_day)`. The return day is free again, so back-to-back rentals touch without clashing."""

    first_day: date
    return_day: date

    def __post_init__(self) -> None:
        if self.return_day <= self.first_day:
            raise InvalidPeriodError(f"the return day {self.return_day} must be after the first day {self.first_day}")

    @classmethod
    def starting(cls, first_day: date, days: int) -> RentalPeriod:
        """A period of `days` rental days beginning on `first_day`."""
        if days < 1:
            raise InvalidPeriodError(f"a rental lasts at least one day, got {days}")
        return cls(first_day, first_day + timedelta(days=days))

    @property
    def days(self) -> int:
        """Number of rental days: the return day itself is not one."""
        return (self.return_day - self.first_day).days

    def overlaps(self, other: RentalPeriod) -> bool:
        """True when some day belongs to both periods. Periods that only touch do not overlap."""
        return self.first_day < other.return_day and other.first_day < self.return_day

    def shifted(self, days: int) -> RentalPeriod:
        """The same length, moved by `days` (negative moves it earlier)."""
        offset = timedelta(days=days)
        return RentalPeriod(self.first_day + offset, self.return_day + offset)

    def __str__(self) -> str:
        return f"{self.first_day.isoformat()} to {self.return_day.isoformat()}"
