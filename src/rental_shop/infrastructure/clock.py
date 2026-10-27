"""Adapter: the wall clock. Implements the `Clock` port."""

from __future__ import annotations

from datetime import date


class SystemClock:
    """Today's date from the machine's clock."""

    def today(self) -> date:
        return date.today()
