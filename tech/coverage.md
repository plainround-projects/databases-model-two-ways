# coverage and pytest-cov

## What it is

**Code coverage** measures which lines (and which branches of `if` statements) ran while the tests ran. `coverage` is the Python tool that records it; `pytest-cov` is the pytest plug-in that turns it on with `--cov`. A **branch** is one of the two ways an `if` can go. This repository locks coverage 7.17.0 and pytest-cov 7.1.0.

## Why this repository uses it

The domain and application layers hold all the rules, and the unit tests run them with fakes. A coverage threshold (95 percent) makes sure no rule goes untested.

## Where it appears

| File | Role |
|---|---|
| `pyproject.toml` | `[tool.coverage.run]` and `[tool.coverage.report]`. |
| `Makefile` | `test` runs `pytest --cov=rental_shop` and `coverage report --fail-under=95`. |

## How it works underneath

While the tests run, coverage watches the interpreter and records each executed line in a data file (`.coverage`, ignored by Git). Afterwards `coverage report` compares the record with the source and prints, per file, how many statements and branches exist, how many were missed, and which line numbers.

## Walkthrough of this repository's use

```toml
[tool.coverage.run]
source = ["rental_shop"]
branch = true

[tool.coverage.report]
show_missing = true
skip_covered = false
```

- `source = ["rental_shop"]` measures only the project package, not the tests or libraries.
- `branch = true` also records whether each `if` was taken both ways.
- `show_missing = true` lists the numbers of the lines that never ran. `skip_covered = false` still lists files at 100 percent, so every file appears.

The Makefile (see [make.md](make.md)) does two steps: `pytest tests/unit --cov=rental_shop --cov-report=term` runs the tests and prints a report; `coverage report --include='src/rental_shop/domain/*,src/rental_shop/application/*' --fail-under=95` restricts the check to the domain and application and makes the command fail if the total is below 95. The unreachable lines are marked `# pragma: no cover` in the source.

## Try it yourself

```bash
make test
```
Prints a table with `Stmts Miss Branch BrPart Cover Missing` columns and a total for domain and application.

```bash
.venv/bin/coverage report --include='src/rental_shop/domain/*' --show-missing
```
After `make test`, shows the domain only.

```bash
.venv/bin/coverage html && ls htmlcov | head -3; rm -rf htmlcov
```
Writes a browsable report and then removes it.

## Mistakes people make

- **Chasing 100 percent** with tests that execute lines but assert nothing.
- **Measuring tests themselves**, which inflates the number. `source` limits it.
- **Counting integration tests** as unit coverage. The gate runs on the unit tests only.

## Check yourself

1. What does branch coverage add? *Whether each `if` was taken both ways.*
2. Which files does the gate check? *Everything under domain and application.*
3. What does `--fail-under=95` do? *Exit non-zero if the total is below 95 percent.*
4. What is `# pragma: no cover`? *A comment telling coverage to skip that line.*
5. Where is the raw data kept? *In `.coverage`, which Git ignores.*

## Further reading

- coverage (docs for 7.17.0): https://coverage.readthedocs.io/en/7.17.0/
- pytest-cov (latest docs; locked at 7.1.0): https://pytest-cov.readthedocs.io/en/latest/
