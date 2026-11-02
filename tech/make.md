# Make

## What it is

Make is a command-line tool that runs named recipes from a file called `Makefile`. A **recipe** is a list of shell commands. A **target** is the name of a recipe (or of a file the recipe produces). A target may list **prerequisites**: other targets that must be finished first. Make was invented to rebuild only what is out of date, and it is also the most common way to give a project short commands such as `make test`.

## Why this repository uses it

Running the lesson needs many long commands: start PostgreSQL, run a SQL file inside the container, run a Python module, run linters. The `Makefile` gives each of them a short name, and it records the exact flags in one place so the README can say `make run` instead of pasting forty lines. Every target that talks to the database uses the same two `psql` command lines, defined once at the top.

## Where it appears

| File | What it does with Make |
|---|---|
| `Makefile` | The 25 phony targets of the project and the install stamp: set up, database, lesson steps, tests, lint, audit, clean-up. |
| `scripts/capture_explain.sh` | Is started by the `explain` target, with `PSQL_CMD` handed over. See [bash.md](bash.md). |
| `.github/workflows/ci.yml` | Calls `make check`, `make audit` and `make test-integration test-e2e`. See [github-actions.md](github-actions.md). |
| `.editorconfig` | Says the Makefile must be indented with tabs. See [editorconfig.md](editorconfig.md). |

## How it works underneath

When you type `make up`, the `make` program reads `Makefile`, builds a graph of targets and prerequisites, and then walks that graph. For each target it first makes sure every prerequisite is done, then runs the recipe. A target is done once per `make` run: if two targets both need `db`, `db` runs one time.

For a target that is a **file**, Make compares modification times. If the file exists and is newer than all its prerequisite files, Make skips the recipe. For a target that is not a file (a name such as `test`), you declare it `.PHONY`, which tells Make "always run this, never look for a file of this name".

Each recipe line is sent to a new shell (`/bin/sh -c "<line>"`). So `cd` on one line does not carry over to the next, and a variable set on one line is gone on the next. A recipe line starts with a **tab character**, not spaces. Make prints each command before running it, unless the line starts with `@`. If any command exits with a non-zero code, Make stops and itself exits with an error.

**Variables** are written `NAME = value` and read as `$(NAME)`. Make expands them before the shell sees the line. This is why a real shell dollar sign must be doubled (`$$`) inside a recipe. Make also exports its variables to child processes as **environment variables** (named values every program can read) when told to.

## Walkthrough of this repository's use

### The first line

```make
# make up | db | run | test | lint | down   (make help lists all)
```

This line is a comment (it starts with `#`). It lists the main targets so a reader sees them on opening the file.

### Variables

```make
PYTHON ?= $(shell command -v python3.13 || command -v python3.12 || command -v python3)
VENV := .venv
PY := $(VENV)/bin/python
STAMP := $(VENV)/.installed
RUNS ?= 20
POSTGRES_USER ?= shop
POSTGRES_DB ?= rentals
PSQL := docker compose exec -T postgres psql -U $(POSTGRES_USER) -d $(POSTGRES_DB) -v ON_ERROR_STOP=1 -q
PSQL_LOUD := docker compose exec -T postgres psql -U $(POSTGRES_USER) -d $(POSTGRES_DB) -v ON_ERROR_STOP=1
```

- `PYTHON ?= $(shell ...)`: `?=` means "assign only if `PYTHON` is not already set", so `make PYTHON=python3.12 install` overrides it. `$(shell command)` runs a command and uses its output. `command -v python3.13` prints the full path of the program if it exists and fails otherwise. `a || b || c` runs `b` only if `a` failed, so the result is the first of Python 3.13, 3.12 or 3 that exists.
- `VENV := .venv` uses `:=`, which evaluates the right side once, immediately. `.venv` is the folder of the **virtual environment**: a private copy of Python and its installed libraries, kept inside the project so that nothing is installed on the whole machine.
- `PY := $(VENV)/bin/python` is the Python program inside that folder.
- `STAMP := $(VENV)/.installed` is a marker file (see the next section) that records "the dependencies are installed".
- `RUNS ?= 20` is the number of races, and can be changed with `make race RUNS=5`.
- `POSTGRES_USER ?= shop` and `POSTGRES_DB ?= rentals` are defaults for the database user and database name.
- `PSQL := docker compose exec -T postgres psql -U $(POSTGRES_USER) -d $(POSTGRES_DB) -v ON_ERROR_STOP=1 -q` is the command that runs `psql` inside the running container. `docker compose exec` runs a command in a running service; `-T` switches off the pseudo-terminal (a fake keyboard-and-screen), which is required when a file is piped in; `postgres` is the service name; `psql` is the PostgreSQL command-line client; `-U` is the user and `-d` the database; `-v ON_ERROR_STOP=1` sets a psql variable so a failing statement ends the run with an error instead of carrying on; `-q` is quiet (no banner and no `CREATE TABLE` echoes). See [psql.md](psql.md).
- `PSQL_LOUD` is the same without `-q`, used when the printed result is the point.

### Reading `.env`

```make
-include .env
export
```

`-include .env` reads the file `.env` as if its lines were written in the Makefile. The leading `-` means "do not complain if the file does not exist". Lines such as `POSTGRES_PORT=5441` are valid Make assignments, so Make now knows the port and the password. The word `export` on its own line means "send every variable Make knows to every command it starts". That is how `docker compose` (which reads `${POSTGRES_PASSWORD}` from its environment) and the Python programs (which read `POSTGRES_HOST` and friends) receive the settings. See [dotenv.md](dotenv.md).

### Phony targets

```make
.PHONY: help install env up db bulk queries demo demo-documents book race race-plain report explain run health lint format \
        test test-integration test-e2e audit check docker-build psql down clean
```

`.PHONY` lists the targets that are names and not files. The `\` at the end of line 15 continues the list on line 16. Without this line, creating a file called `test` in the folder would make `make test` say "nothing to do".

### `help`

```make
help: ## list the targets
	@grep -hE '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | sed -E 's/:.*## /\t/' | sort
```

A comment starting with `##` after a target is used as its description. The recipe starts with `@` so the command itself is not printed. `$(MAKEFILE_LIST)` is the list of makefiles read (`Makefile` and `.env`). The pipeline works like this: `grep -hE` keeps only lines that look like `name: ... ## text` (`-E` means extended regular expressions, `-h` hides the file name that grep would add when it reads two files); `sed -E 's/:.*## /\t/'` replaces everything from the first colon through `## ` with a tab; `sort` puts the targets in alphabetical order.

### The install stamp

```make
$(STAMP): requirements-dev.lock pyproject.toml
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/pip install -q --require-hashes -r requirements-dev.lock
	$(VENV)/bin/pip install -q --no-deps -e .
	touch $@

install: $(STAMP) ## create .venv from the lock file
```

- `$(STAMP): requirements-dev.lock pyproject.toml` is a **file target** with two file prerequisites. If `.venv/.installed` is missing, or older than either file, the recipe runs.
- `$(PYTHON) -m venv $(VENV)` creates the virtual environment (`-m venv` runs the standard library module `venv` as a program).
- `pip install -q --require-hashes -r requirements-dev.lock` installs the exact versions in the lock file. `-q` is quiet. `--require-hashes` makes pip refuse any package whose file does not match the cryptographic fingerprint recorded in the lock, which protects against a tampered download. `-r` reads the list from a file.
- `pip install -q --no-deps -e .` installs this project itself in **editable** mode (`-e`): the installed copy points at the `src/` folder, so edits take effect without reinstalling. `--no-deps` stops pip from pulling dependencies again, because the lock file already installed them.
- `touch $@` creates or updates the stamp. `$@` is an **automatic variable** holding the target's name, here `.venv/.installed`.
- `install: $(STAMP) ## ...` is a named shortcut with no recipe of its own.

### `env`, `up`, `db`

```make
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
```

- `env`: `[ -f .env ]` is a shell test that is true when the file `.env` exists. `||` runs the right side only when the left side failed. `{ cp .env.example .env; echo "..."; }` is a command group: copy the example file to `.env`, then print a message. So `.env` is created on first use and never overwritten.
- `up: env $(STAMP)` has two prerequisites, so `.env` and the virtual environment exist before PostgreSQL starts. `docker compose up -d --wait` starts the services from `docker-compose.yml`; `-d` detaches (runs in the background); `--wait` does not return until every service's health check passes. See [docker-compose.md](docker-compose.md).
- `db` runs four SQL files in order: reset (drops the tables), schema, seed, and the exclusion-constraint migration. Each line feeds a file into `psql` with `<`. The comment above it says it is safe to rerun. See [sql.md](sql.md).

### `bulk` and the lesson queries

```make
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
```

- `bulk` first drops the constraint if it exists (`-c` runs one SQL command), loads 100,000 rentals, adds the constraint back, and runs `ANALYZE rentals` so the planner knows the new size. The comment explains the reason: checking every row through the index during the load takes minutes, while building the index once afterwards is fast.
- `queries`, `demo` and `demo-documents` run the lesson's SQL files. They use `$(PSQL_LOUD)` or `$(PSQL)` depending on whether the result is the point.

### The Python programs

```make
book: $(STAMP) ## book one rental: make book ITEM=1 CUSTOMER=2 FROM=2026-11-03 DAYS=2
	$(PY) -m rental_shop.interfaces.book_cli --item $(ITEM) --customer $(CUSTOMER) --from $(FROM) --days $(DAYS)

race: $(STAMP) ## step 5: 20 connections race for one item, 20 times; exactly one wins each time
	$(PY) -m rental_shop.interfaces.race_cli --runs $(RUNS)

race-plain: $(STAMP) ## the same race with a plain INSERT (SQLSTATE 23P01); deadlock victims are retried and counted
	$(PY) -m rental_shop.interfaces.race_cli --runs $(RUNS) --insert raise

report: $(STAMP) ## the five questions through the application code
	$(PY) -m rental_shop.interfaces.report_cli
```

Each of these targets depends on `$(STAMP)`, so the virtual environment is created on demand. `$(PY) -m rental_shop.interfaces.book_cli` runs a module of the package as a program (`-m`). `$(ITEM)`, `$(CUSTOMER)`, `$(FROM)` and `$(DAYS)` are Make variables supplied on the command line (`make book ITEM=1 ...`). `race-plain` passes `--insert raise` to use the plain insert. See [argparse.md](argparse.md) for the flags.

### `explain`, `run`, `health`

```make
# Capture the plans on 100,000 rentals. Rebuilds the database and leaves the bulk data in place.
explain: db bulk ## step 6: write EXPLAIN (ANALYZE, BUFFERS) plans to sql/explain/*.txt
	PSQL_CMD="$(PSQL)" ./scripts/capture_explain.sh

run: db queries demo demo-documents report race ## the whole lesson: build, query, refuse, race

health: $(STAMP) ## exit 0 when PostgreSQL has the tables and the exclusion constraint
	$(PY) -m rental_shop.interfaces.health_cli
```

- `explain: db bulk` lists two prerequisites, which run in order, before the recipe. The recipe sets `PSQL_CMD` for that one command only (`NAME=value command` is a shell feature) and runs the Bash script.
- `run` chains the whole lesson. Make runs the prerequisites from left to right, and runs a target only once per invocation, which is why `db` appears once.
- `health` exits 0 only if the tables and the constraint exist.

### Lint and format

```make
lint: $(STAMP) ## ruff check, ruff format check, mypy, import-linter
	$(VENV)/bin/ruff check .
	$(VENV)/bin/ruff format --check .
	$(VENV)/bin/mypy
	$(VENV)/bin/lint-imports

format: $(STAMP) ## apply ruff's formatting and safe fixes
	$(VENV)/bin/ruff check --fix .
	$(VENV)/bin/ruff format .
```

`lint` runs the four checkers in turn (`ruff check`, `ruff format --check`, `mypy`, `lint-imports`); if one fails, Make stops. `format` applies the fixes (`ruff check --fix`, `ruff format`). See [ruff.md](ruff.md), [mypy.md](mypy.md) and [import-linter.md](import-linter.md).

### Tests, audit, check

```make
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
```

- `test` runs only `tests/unit` with coverage (`--cov=rental_shop` measures which lines of the package ran), prints a report, then `coverage report ... --fail-under=95` fails when the domain or application code is below 95 percent. The `--include` pattern limits the check to those two folders. See [pytest.md](pytest.md).
- `test-integration` and `test-e2e` select tests by **marker** (`-m integration`, `-m e2e`). They need the database from `make up`.
- `audit` checks the pinned packages against a database of known vulnerabilities. `--no-deps` and `--disable-pip` stop `pip-audit` from resolving anything itself, so it audits exactly the lock file. See [pip-audit.md](pip-audit.md).
- `check` has no recipe, only prerequisites: it means "lint, then test".

### Docker, psql, down, clean

```make
docker-build: ## build the container image of the command-line programs
	docker build -t databases-model-two-ways:dev .

psql: ## an interactive psql session
	docker compose exec postgres psql -U $(POSTGRES_USER) -d $(POSTGRES_DB)

down: ## stop PostgreSQL and delete its data
	docker compose down -v

clean: down
	rm -rf $(VENV) logs .pytest_cache .mypy_cache .ruff_cache .import_linter_cache .coverage
```

- `docker-build` builds the image from the `Dockerfile` and tags it (`-t`) `databases-model-two-ways:dev`; the final `.` is the build context (the folder sent to Docker). See [docker.md](docker.md).
- `psql` opens an interactive session; there is no `-T` here because a human is typing.
- `down` stops the services and deletes their volumes (`-v`), so the data is gone.
- `clean` depends on `down`, then removes the virtual environment and every cache folder with `rm -rf` (`-r` recursive, `-f` no complaint if missing).

## Try it yourself

```bash
make help
```
A sorted list: each target name, a tab, its description.

```bash
make -n run
```
`-n` prints the commands without running them. You see the `docker compose exec` lines for `db`, then `queries`, `demo`, `demo-documents`, `report` and `race`.

```bash
make -n install; make install; make -n install
```
First a dry run shows the `venv` and `pip` commands (if the stamp is missing); after the real run the last command prints `Nothing to be done for `install'.`, because the stamp is newer than both files.

```bash
make PYTHON=python3.12 -n install
```
Shows the command line with the override applied.

```bash
make check
```
Runs lint and the unit tests with coverage, with no services needed.

## Mistakes people make

- **Spaces instead of a tab** in a recipe line gives the error `missing separator`. The `.editorconfig` says Makefiles use tabs.
- **Forgetting `.PHONY`**: a file named like a target hides it. All non-file targets are listed.
- **A single `$` in a recipe**: Make eats it. This repository has no shell variable in recipes, and `scripts/` holds the script that needs them.
- **Thinking `cd` carries over** to the next line: each line is a new shell. This repository never relies on it.
- **Running a dependency twice**: Make runs each target once per invocation, so a prerequisite is never repeated; the repository's `run` target lists `db` once.

## Check yourself

1. What does `?=` do that `=` does not? *It assigns only when the variable has no value yet, so the command line can override it.*
2. Why is `touch $@` the last line of the `$(STAMP)` recipe? *It records success: Make compares the stamp's time with the lock file's time to decide whether to install again.*
3. What does the leading `@` before a command do? *It stops Make from printing the command before running it.*
4. What does `-include .env` do when `.env` is missing? *Nothing; the leading `-` ignores the error.*
5. What is the difference between `$(PSQL)` and `$(PSQL_LOUD)`? *`$(PSQL)` adds `-q`, hiding the status lines; the loud form prints them.*

## Further reading

- GNU Make manual (this repository is used with GNU Make 3.81 or newer; macOS ships 3.81): https://www.gnu.org/software/make/manual/make.html
- Automatic variables: https://www.gnu.org/software/make/manual/make.html#Automatic-Variables
- Phony targets: https://www.gnu.org/software/make/manual/make.html#Phony-Targets
