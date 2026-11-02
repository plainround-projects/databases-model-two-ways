# setuptools

## What it is

setuptools is the long-standing Python tool that **builds** a package: it reads the project's description, collects the Python files, and produces an installable package. It is called a **build backend**. pip does not build packages itself; it asks the backend named in `pyproject.toml`. This repository requires setuptools 75 or newer.

## Why this repository uses it

To make `rental_shop` an installable package with four console commands (`rental-shop-book`, `rental-shop-race`, `rental-shop-report`, `rental-shop-health`). Installing in editable mode (`pip install -e .`) is how tests and the Makefile import the code, and the Docker image runs `pip install --no-deps .` to install a normal copy.

## Where it appears

| Place | Role |
|---|---|
| `pyproject.toml` `[build-system]` | Names setuptools as the backend. |
| `pyproject.toml` `[tool.setuptools.packages.find]` | Says where the packages are (`src`). |
| `Makefile`, `Dockerfile` | The `pip install` commands that trigger the build. |

## How it works underneath

When pip must install a project from a folder, it creates a temporary isolated environment, installs the packages listed in `build-system.requires`, and calls the function named in `build-backend`. setuptools reads `[project]` for the metadata and `[tool.setuptools...]` for its own settings, finds the packages (a package is a folder with an `__init__.py`), and either copies them into the target environment, or for an editable install, writes a small file that makes Python look in the source folder.

## Walkthrough of this repository's use

```toml
[build-system]
requires = ["setuptools>=75"]
build-backend = "setuptools.build_meta"
```

```toml
[tool.setuptools.packages.find]
where = ["src"]
```

These lines are explained in [toml.md](toml.md). In summary: `requires` makes pip fetch setuptools 75 or newer, `build-backend` names the entry point, and `where = ["src"]` points the package search at the `src` folder, so `rental_shop` is found there. Packages not under `src` (such as `tests`) are not installed.

## Try it yourself

```bash
.venv/bin/pip show -f databases-model-two-ways | head -20
```
Shows the installed package metadata and its files.

```bash
.venv/bin/python -c "import rental_shop, sys; print(rental_shop.__file__)"
```
Prints a path inside `src/` because the install is editable.

```bash
.venv/bin/pip list --format=freeze | grep -i setuptools
```
Shows whether setuptools itself is in the virtual environment.

## Mistakes people make

- **Putting code at the repository root**, so tests import files that are not installed. The src layout avoids it.
- **Forgetting to list packages**, so an installed copy is empty.
- **Treating setuptools as a runtime dependency.** It is needed only to build.

## Check yourself

1. What is a build backend? *The tool pip calls to turn a source folder into an installable package.*
2. Where is it named? *In `[build-system]`.*
3. What does `where = ["src"]` do? *Search for packages in `src`.*
4. What is an editable install? *An install that points at the source folder.*
5. Is setuptools needed at run time? *No.*

## Further reading

- setuptools 75 documentation: https://setuptools.pypa.io/en/latest/
