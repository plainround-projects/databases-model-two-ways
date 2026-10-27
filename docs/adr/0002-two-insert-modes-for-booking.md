# 2. Book with ON CONFLICT DO NOTHING; keep the plain INSERT as a mode

Status: accepted, 2026-10-26

## Context

The lesson's race script inserts from 20 connections at once and expects one success and nineteen exclusion violations (SQLSTATE 23P01). Run as written against PostgreSQL 18, a plain `INSERT` does give exactly one winner every time, but some rounds also produce deadlocks (SQLSTATE 40P01): each contender inserts its row, then checks the constraint, finds another contender's uncommitted row, and waits for it, while that contender waits for the first. PostgreSQL detects the cycle after `deadlock_timeout` and ends one contender. In 20-round runs on a laptop about one round in five had a deadlock, and in the worst rounds the same contenders lost to deadlocks again on every retry.

## Decision

- The default insert is `INSERT ... ON CONFLICT ON CONSTRAINT rentals_item_id_during_excl DO NOTHING RETURNING rental_id`. A clash returns no row, which the adapter reports as `ItemAlreadyBookedError`. For this form PostgreSQL lets an inserter wait only for a transaction older than itself, so waits cannot form a cycle and there are no deadlocks.
- The plain `INSERT` stays as `InsertMode.RAISE` (`make race-plain`). A deadlock victim is reported as `BookingDeadlockError`, and `BookItem` retries it with doubling, jittered pauses. The safety property, one winner, holds in both modes; only the way the losers lose differs.
- The compose file sets `deadlock_timeout=100ms` so the plain mode's deadlocks resolve in tenths of a second. The default is one second.

## Alternatives considered

- **Only the plain insert, retrying forever:** keeps 23P01 in the output but turns a refusal into a long retry storm.
- **An advisory lock around the insert:** removes the deadlocks but is application-level locking, which the lesson rules out and which protects only callers that take it.

## Consequences

- The constraint is still the only rule. `ON CONFLICT DO NOTHING` swallows only that constraint (a foreign-key or check violation still raises).
- The default race output says "refused by the exclusion constraint"; the plain mode prints "exclusion violations (23P01)" as the lesson does.
- The retry code exists for the plain mode and for any other deadlock; it is covered by unit tests.
