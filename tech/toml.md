# TOML and `pyproject.toml`

## What it is

TOML is a plain-text format for configuration, designed to be obvious to read. A file is a list of `key = value` lines grouped under **tables**, whose names are written in square brackets: `[project]`. `[[double.brackets]]` starts one more item of a **list of tables**. Values can be text in double quotes, numbers, `true`/`false`, lists in `[ ... ]` and inline tables in `{ ... }`. `#` starts a comment. `pyproject.toml` is the standard file where a Python project describes itself (name, version, dependencies, how to build) and where tools keep their settings, each in a table called `[tool.<name>]`.

## Why this repository uses it

One file holds the package metadata and the configuration of every tool (ruff, mypy, pytest, coverage, import-linter). A reader finds all rules of the project in one place.

## Where it appears

| Section of `pyproject.toml` | Explained in |
|---|---|
| `[build-system]`, `[project]`, `[project.optional-dependencies]`, `[project.scripts]`, `[tool.setuptools.packages.find]` | this file |
| `[tool.ruff*]` | [ruff.md](ruff.md) |
| `[tool.mypy*]` | [mypy.md](mypy.md) |
| `[tool.pytest.ini_options]` | [pytest.md](pytest.md) |
| `[tool.coverage.*]` | [coverage.md](coverage.md) |
| `[tool.importlinter*]` | [import-linter.md](import-linter.md) |

## How it works underneath

To install the project, pip reads `[build-system]` to learn which tool turns the source into an installable package (a **build backend**; here setuptools). It downloads that tool, runs it, and the tool reads `[project]`. Installing creates the package files in the virtual environment and, for each entry of `[project.scripts]`, a small executable named after the key that imports the function and calls it. Other tools read only their own `[tool.<name>]` tables and ignore the rest.

## Walkthrough of this repository's use

```toml
[build-system]
requires = ["setuptools>=75"]
build-backend = "setuptools.build_meta"
```

`[build-system]` says: to build this project, install `setuptools` at version 75 or newer (`>=75`), and use its entry point `setuptools.build_meta`, the standard hook that build front-ends such as pip call.

```toml
[project]
name = "databases-model-two-ways"
version = "0.1.0"
description = "An equipment-rental shop modeled as tables and as documents; the PostgreSQL version refuses a double booking with an exclusion constraint."
readme = "README.md"
requires-python = ">=3.12"
license = { text = "MIT" }
authors = [{ name = "Sumit Srivastava" }]
dependencies = ["psycopg[binary]>=3.2,<4"]
```

- `name` and `version` identify the package. `description` is one sentence. `readme = "README.md"` names the long description (the Dockerfile copies the README for this reason).
- `requires-python = ">=3.12"`: pip refuses to install on an older Python.
- `license = { text = "MIT" }` is an inline table. `authors = [{ name = "Sumit Srivastava" }]` is a list with one inline table.
- `dependencies = ["psycopg[binary]>=3.2,<4"]`: the only run-time dependency. The version rule means 3.2 or newer but below 4. `[binary]` selects the extra described in [psycopg.md](psycopg.md).

```toml
[project.optional-dependencies]
dev = [
    "pytest>=8,<10",
    "pytest-cov>=5",
    "ruff>=0.6",
    "mypy>=1.11",
    "import-linter>=2.0",
    "pip-audit>=2.7",
]
```

`[project.optional-dependencies]` defines groups installed only on request. The group `dev` lists the development tools: pytest and its coverage plug-in, ruff, mypy, import-linter and pip-audit, each with a minimum version. Pip does not install them for a user of the package. The exact versions used are fixed in `requirements-dev.lock` (see [pip-and-venv.md](pip-and-venv.md)).

```toml
[project.scripts]
rental-shop-book = "rental_shop.interfaces.book_cli:main"
rental-shop-race = "rental_shop.interfaces.race_cli:main"
rental-shop-report = "rental_shop.interfaces.report_cli:main"
rental-shop-health = "rental_shop.interfaces.health_cli:main"
```

`[project.scripts]` maps command names to Python functions: `rental-shop-book = "rental_shop.interfaces.book_cli:main"` means "create a command `rental-shop-book` that imports module `rental_shop.interfaces.book_cli` and calls `main()`". The returned number becomes the exit code. The Dockerfile's `HEALTHCHECK` uses `rental-shop-health` (see [docker.md](docker.md)).

```toml
[tool.setuptools.packages.find]
where = ["src"]
```

`[tool.setuptools.packages.find]` with `where = ["src"]` tells setuptools to look for packages in the `src` folder, not at the root. This is the **src layout**: the code is importable only after installation, so tests exercise the installed package and not stray files in the current folder.

The remaining sections are quoted where their tool is explained, in the files listed above.

## Try it yourself

```bash
python3 -c "import tomllib, pprint; pprint.pprint(tomllib.load(open('pyproject.toml','rb'))['project'])"
```
Prints the `[project]` table as a Python dictionary (`tomllib` is in the standard library since Python 3.11).

```bash
.venv/bin/rental-shop-health; echo "exit=$?"
```
The installed command; it prints a result and an exit code (1 or 2 without a database or settings, 0 when healthy).

```bash
.venv/bin/pip show databases-model-two-ways
```
Shows the installed name, version and where it lives (editable install).

```bash
ls .venv/bin | grep rental
```
Four commands, one per `[project.scripts]` entry.

## Mistakes people make

- **A missing quote or comma in a list** is a parse error; use `tomllib` to check.
- **Forgetting the `where` for a src layout**, so the package is not found.
- **Mixing up `dependencies` and `optional-dependencies`**, which ships test tools to users.
- **Putting a secret here.** There is none.

## Check yourself

1. What does `[[tool.importlinter.contracts]]` mean? *One more item of a list of tables: a contract.*
2. What does `psycopg[binary]>=3.2,<4` allow? *3.2 or newer, below 4, with the binary extra.*
3. What does `[project.scripts]` create? *A command that imports a function and calls it.*
4. What is the src layout for? *To make tests use the installed package.*
5. Which tool reads `[build-system]`? *pip (and any build front-end).*

## Further reading

- TOML 1.0.0: https://toml.io/en/v1.0.0
- Python Packaging User Guide, `pyproject.toml`: https://packaging.python.org/en/latest/guides/writing-pyproject-toml/
- setuptools 75: https://setuptools.pypa.io/en/latest/userguide/pyproject_config.html
