# 1. The database decides whether a booking is allowed

Status: accepted, 2026-10-26

## Context

Two requests can ask for the same item on overlapping dates at the same moment. The rule "one item is never rented twice for overlapping dates" has to hold for every client, including scripts and other services that never go through this code.

## Decision

The rule is a PostgreSQL exclusion constraint on `rentals`: `EXCLUDE USING gist (item_id WITH =, during WITH &&)`, with `during` a half-open `daterange`. The application inserts and reports the outcome; it does not check availability first. The check-then-insert pattern is the race the lesson's step 5 proves.

## Alternatives considered

- **Check availability in the application, then insert:** two requests both read "free" and both insert.
- **Serializable transactions with a retry:** correct, but every writer must use it and retry; the constraint needs neither.
- **An advisory lock per item in the application:** correct for clients that take the lock, silent for any that do not.
- **Two date columns and a trigger:** works, but re-implements what the range type and the constraint do.

## Consequences

- The constraint needs the `btree_gist` extension and a GiST index; its index also answers the availability question.
- A refusal is SQLSTATE `23P01` (or no row, with `ON CONFLICT DO NOTHING`; see ADR 0002), mapped to the named error `ItemAlreadyBookedError`.
- Half-open ranges let a rental start on the day another ends.
