# Changelog

All notable changes to this project are recorded here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Drawn architecture and flow figures in `docs/diagrams/`, light and dark, shown in the README.
- `tech/`: one note per technology the repository uses, from zero, with every source file quoted and explained (start with `tech/README.md`).

### Fixed

- `make help` printed the file name instead of the target name when `.env` was read; `make run` no longer lists `db` twice (Make runs a target once per invocation).

## [0.1.0] - 2026-10-26

### Added

- PostgreSQL 18 in `docker-compose.yml`.
- SQL scripts: the relational schema (customers, items, rentals as a half-open `daterange`), the hand-checked seed, the five queries, a constraint demo, the step-4 migration that adds the exclusion constraint, a 100,000-rental bulk load, and the document design as JSONB.
- `EXPLAIN (ANALYZE, BUFFERS)` plans on 100,000 rentals, with the availability query captured before and after the constraint.
- Layered package (`domain`, `application`, `infrastructure`, `interfaces`) with the dependency rule enforced by import-linter: a booking use case that lets the database decide, the five-question report, a race of concurrent bookings, and a health command.
- Two insert modes for booking (`ON CONFLICT DO NOTHING` by default, a plain `INSERT` that raises SQLSTATE 23P01), with a retry for deadlock victims in the plain mode.
- Unit, integration (per-test schema) and end-to-end tests, ruff, mypy, hash-pinned lock files and a CI workflow.
- Documents: access patterns, the document model, decision records.
