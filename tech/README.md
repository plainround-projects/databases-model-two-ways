# Technology notes

One file per technology that this repository uses, each written for a reader who has never seen it. Every file explains the idea from zero and then walks through this repository's own code line by line. The code quoted in the notes is copied from the repository's files, so a quoted line is the real line.

## The files

| File | Role in this repository |
|---|---|
| [python.md](python.md) | Python 3.13: the language, and the `domain` and `application` layers (periods, entities, ports, use cases). |
| [python-stdlib.md](python-stdlib.md) | Standard library: settings from the environment, retry with backoff, signals, the clock. |
| [python-logging.md](python-logging.md) | The `logging` module and the logfmt formatter. |
| [threading.md](threading.md) | Threads, a lock and a barrier: the 20-way race. |
| [argparse.md](argparse.md) | The four command-line programs and their exit codes. |
| [psycopg.md](psycopg.md) | The PostgreSQL driver: connections, parameters, error mapping, the adapter. |
| [pytest.md](pytest.md) | The unit, integration and end-to-end tests, fixtures and fakes. |
| [coverage.md](coverage.md) | Coverage measurement and the 95 percent gate. |
| [ruff.md](ruff.md) | Linting and formatting rules. |
| [mypy.md](mypy.md) | Static type checking in strict mode. |
| [import-linter.md](import-linter.md) | The two architecture contracts. |
| [toml.md](toml.md) | The TOML format and `pyproject.toml`. |
| [setuptools.md](setuptools.md) | The build backend. |
| [pip-and-venv.md](pip-and-venv.md) | Installing with hashes into a virtual environment. |
| [uv.md](uv.md) | The tool that generated the lock files. |
| [pip-audit.md](pip-audit.md) | Checking locked packages for known vulnerabilities. |
| [sql.md](sql.md) | Every SQL file: tables, seed, queries, constraint, bulk load, JSONB documents, plans. |
| [postgresql.md](postgresql.md) | The database server: indexes, exclusion constraints, deadlocks, plans. |
| [psql.md](psql.md) | The command-line client that runs the SQL files. |
| [bash.md](bash.md) | The script that captures the query plans. |
| [make.md](make.md) | The `Makefile`: every target. |
| [docker.md](docker.md) | The `Dockerfile` and `.dockerignore`. |
| [docker-compose.md](docker-compose.md) | The PostgreSQL service. |
| [yaml.md](yaml.md) | The YAML format used by Compose and CI. |
| [github-actions.md](github-actions.md) | The CI workflow. |
| [dotenv.md](dotenv.md) | The `.env` settings file. |
| [editorconfig.md](editorconfig.md) | `.editorconfig` and `.gitignore`. |

## Reading order

1. **The data first:** [sql.md](sql.md), then [postgresql.md](postgresql.md), then [psql.md](psql.md). The lesson is the database; everything else serves it.
2. **The language:** [python.md](python.md), then [python-stdlib.md](python-stdlib.md), [python-logging.md](python-logging.md), [threading.md](threading.md), [argparse.md](argparse.md) and [psycopg.md](psycopg.md).
3. **The build and run tools:** [make.md](make.md), [bash.md](bash.md), [docker-compose.md](docker-compose.md) (with [yaml.md](yaml.md)), [dotenv.md](dotenv.md), [docker.md](docker.md).
4. **The packaging:** [toml.md](toml.md), [setuptools.md](setuptools.md), [pip-and-venv.md](pip-and-venv.md), [uv.md](uv.md).
5. **The checks:** [pytest.md](pytest.md), [coverage.md](coverage.md), [ruff.md](ruff.md), [mypy.md](mypy.md), [import-linter.md](import-linter.md), [pip-audit.md](pip-audit.md), [github-actions.md](github-actions.md), [editorconfig.md](editorconfig.md).

## If you have ten minutes

Read these three:

1. [sql.md](sql.md): the tables, and the one constraint that makes a double booking impossible.
2. [postgresql.md](postgresql.md): how the server enforces it, and what a deadlock is.
3. [threading.md](threading.md): the 20-connection race that proves it.
