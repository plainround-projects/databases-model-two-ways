# make up | db | run | test | lint | down   (make help lists all)
PYTHON ?= $(shell command -v python3.13 || command -v python3.12 || command -v python3)
VENV := .venv
PY := $(VENV)/bin/python
STAMP := $(VENV)/.installed
RUNS ?= 20
POSTGRES_USER ?= shop
POSTGRES_DB ?= rentals
PSQL := docker compose exec -T postgres psql -U $(POSTGRES_USER) -d $(POSTGRES_DB) -v ON_ERROR_STOP=1 -q
PSQL_LOUD := docker compose exec -T postgres psql -U $(POSTGRES_USER) -d $(POSTGRES_DB) -v ON_ERROR_STOP=1

-include .env
export

.PHONY: help install env up db bulk queries demo demo-documents book race race-plain report explain run health lint format \
        test test-integration test-e2e audit check docker-build psql down clean

help: ## list the targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | sed -E 's/:.*## /\t/' | sort

$(STAMP): requirements-dev.lock pyproject.toml
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/pip install -q --require-hashes -r requirements-dev.lock
	$(VENV)/bin/pip install -q --no-deps -e .
	touch $@

install: $(STAMP) ## create .venv from the lock file

env:
	@[ -f .env ] || { cp .env.example .env; echo "created .env from .env.example"; }

up: env $(STAMP) ## start PostgreSQL and wait until it accepts connections
	docker compose up -d --wait

# Drops and rebuilds the three tables, so it is safe to run again: schema (step 2), seed, then the step-4 migration.
db: ## rebuild the schema, load the hand-checked seed, add the exclusion constraint
	$(PSQL) < sql/reset.sql
	$(PSQL) < sql/001_schema.sql
	$(PSQL) < sql/002_seed.sql
	$(PSQL) < sql/migrations/001_exclusion_constraint.sql

# With the constraint in place every inserted row is checked through the GiST index, which takes minutes for
# 100,000 rows. Dropping it for the load and adding it back builds the index once and re-checks every row.
bulk: ## add 100,000 rentals (step 6); make db restores the hand-checked data
	$(PSQL) -c "ALTER TABLE rentals DROP CONSTRAINT IF EXISTS rentals_item_id_during_excl"
	$(PSQL) < sql/bulk/100k_rentals.sql
	$(PSQL) < sql/migrations/001_exclusion_constraint.sql
	$(PSQL) -c "ANALYZE rentals"

queries: ## the five questions on the seed data (sql/003_queries.sql)
	$(PSQL_LOUD) < sql/003_queries.sql

demo: ## the constraint refusing an overlap and allowing a touching range (sql/004_constraint_demo.sql)
	$(PSQL_LOUD) < sql/004_constraint_demo.sql

demo-documents: ## the document design accepting the same double booking (sql/document_model/)
	$(PSQL) < sql/document_model/001_documents.sql
	$(PSQL_LOUD) < sql/document_model/002_double_booking.sql

book: $(STAMP) ## book one rental: make book ITEM=1 CUSTOMER=2 FROM=2026-11-03 DAYS=2
	$(PY) -m rental_shop.interfaces.book_cli --item $(ITEM) --customer $(CUSTOMER) --from $(FROM) --days $(DAYS)

race: $(STAMP) ## step 5: 20 connections race for one item, 20 times; exactly one wins each time
	$(PY) -m rental_shop.interfaces.race_cli --runs $(RUNS)

race-plain: $(STAMP) ## the same race with a plain INSERT (SQLSTATE 23P01); deadlock victims are retried and counted
	$(PY) -m rental_shop.interfaces.race_cli --runs $(RUNS) --insert raise

report: $(STAMP) ## the five questions through the application code
	$(PY) -m rental_shop.interfaces.report_cli

# Capture the plans on 100,000 rentals. Rebuilds the database and leaves the bulk data in place.
explain: db bulk ## step 6: write EXPLAIN (ANALYZE, BUFFERS) plans to sql/explain/*.txt
	PSQL_CMD="$(PSQL)" ./scripts/capture_explain.sh

run: db queries demo demo-documents db report race ## the whole lesson: build, query, refuse, race

health: $(STAMP) ## exit 0 when PostgreSQL has the tables and the exclusion constraint
	$(PY) -m rental_shop.interfaces.health_cli

lint: $(STAMP) ## ruff check, ruff format check, mypy, import-linter
	$(VENV)/bin/ruff check .
	$(VENV)/bin/ruff format --check .
	$(VENV)/bin/mypy
	$(VENV)/bin/lint-imports

format: $(STAMP) ## apply ruff's formatting and safe fixes
	$(VENV)/bin/ruff check --fix .
	$(VENV)/bin/ruff format .

# Unit tests need no database. Coverage is reported for the package; domain and application must stay at 95% or more.
test: $(STAMP) ## unit tests with coverage (no PostgreSQL needed)
	$(PY) -m pytest tests/unit --cov=rental_shop --cov-report=term
	$(PY) -m coverage report --include='src/rental_shop/domain/*,src/rental_shop/application/*' --fail-under=95

test-integration: $(STAMP) ## the adapter against the running database (make up first)
	$(PY) -m pytest tests/integration -m integration

test-e2e: $(STAMP) ## the lesson's scenario through the command-line programs (make up first)
	$(PY) -m pytest tests/e2e -m e2e

audit: $(STAMP) ## check the locked dependencies for known vulnerabilities
	$(VENV)/bin/pip-audit --no-deps --disable-pip -r requirements-dev.lock

check: lint test ## everything that needs no services

docker-build: ## build the container image of the command-line programs
	docker build -t databases-model-two-ways:dev .

psql: ## an interactive psql session
	docker compose exec postgres psql -U $(POSTGRES_USER) -d $(POSTGRES_DB)

down: ## stop PostgreSQL and delete its data
	docker compose down -v

clean: down
	rm -rf $(VENV) logs .pytest_cache .mypy_cache .ruff_cache .import_linter_cache .coverage
