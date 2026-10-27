"""Health command: exit 0 when PostgreSQL has the rental tables and the exclusion constraint.

python -m rental_shop.interfaces.health_cli
"""

from __future__ import annotations

from collections.abc import Sequence

from ..application.health import check_health
from ..infrastructure.health_probes import PostgresSchemaProbe
from .common import load_settings


def main(_argv: Sequence[str] | None = None) -> int:
    """Check PostgreSQL; returns 0 when healthy."""
    settings = load_settings()
    if settings is None:
        return 2
    report = check_health([PostgresSchemaProbe(settings.postgres)])
    for result in report.results:
        print(f"{'ok' if result.ok else 'FAIL'} {result.name}: {result.detail}")
    return 0 if report.healthy else 1


if __name__ == "__main__":
    raise SystemExit(main())
