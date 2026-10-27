#!/usr/bin/env bash
# Writes sql/explain/*.txt: EXPLAIN (ANALYZE, BUFFERS) of the shop's queries on 100,000 rentals.
# Expects the seed plus sql/bulk/100k_rentals.sql to be loaded (make explain does that) and PSQL_CMD to hold the
# command that runs a SQL file on stdin, for example: docker compose exec -T postgres psql -U shop -d rentals -q
# The availability query is captured twice, without and with the step-4 exclusion constraint.
set -euo pipefail
cd "$(dirname "$0")/.."

: "${PSQL_CMD:?set PSQL_CMD to a command that runs SQL from stdin}"
out=sql/explain

capture() { # capture <query-file> <output-file> <label>
  {
    echo "-- $3"
    echo "-- captured $(date -u +%Y-%m-%d) on $($PSQL_CMD -At -c 'SHOW server_version' | head -1), 100,000 rentals, after ANALYZE"
    echo "-- source: $1"
    echo
    $PSQL_CMD < "$1"
  } > "$2"
  echo "wrote $2"
}

# Settle statistics and warm the cache once, so the plans are not dominated by the bulk load.
echo "ANALYZE rentals; ANALYZE items; ANALYZE customers;" | $PSQL_CMD
echo "SELECT count(*) FROM rentals;" | $PSQL_CMD > /dev/null

# Before: no exclusion constraint, so no index covers (item_id, during).
echo "ALTER TABLE rentals DROP CONSTRAINT rentals_item_id_during_excl;" | $PSQL_CMD
capture "$out/q1_is_item_free.sql" "$out/q1_is_item_free_before.txt" "before the constraint: no index on (item_id, during)"

# After: the migration of lesson step 4 adds the constraint and its GiST index.
$PSQL_CMD < sql/migrations/001_exclusion_constraint.sql
echo "ANALYZE rentals;" | $PSQL_CMD
capture "$out/q1_is_item_free.sql" "$out/q1_is_item_free_after.txt" "after the constraint: its GiST index answers the check"
for query in q2_free_next_weekend q3_customer_history q4_returns_today q5_revenue_per_item_and_month q6_never_rented; do
  capture "$out/$query.sql" "$out/$query.txt" "with the constraint and the lesson's indexes"
done
