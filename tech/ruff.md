# ruff

## What it is

ruff is a very fast tool that reads Python source and reports **lint** findings (code that is probably wrong or inconsistent) and **formats** the code (fixes spacing, quotes, line breaks). It replaces several older tools (flake8, isort, pyupgrade and black). This repository locks ruff 0.17.2.

## Why this repository uses it

Reviewers should read behaviour, not argue about style. `make lint` fails on a bug-prone pattern or on formatting that differs from the one standard, and `make format` fixes it automatically.

## Where it appears

| File | Role |
|---|---|
| `pyproject.toml` | `[tool.ruff]`, `[tool.ruff.lint]`, `[tool.ruff.lint.per-file-ignores]`. |
| `Makefile` | `lint` runs `ruff check .` and `ruff format --check .`; `format` runs `ruff check --fix .` and `ruff format .`. |

## How it works underneath

ruff parses each file into a tree of the program's structure, applies **rules**, each with a code (a letter prefix and a number, such as `E501`), and prints a finding for each violation. A **rule group** is a prefix: `B` selects every rule starting with B. `ruff format` rewrites the file to one canonical style. `--check` makes it only report that a file would change, and exit non-zero.

## Walkthrough of this repository's use

```toml
[tool.ruff]
line-length = 120
target-version = "py312"
src = ["src", "tests"]
# The tech/ notes quote fragments of the code in Markdown fences; they are not source files to format.
extend-exclude = ["tech"]

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "SIM", "N", "C4", "RUF", "PT", "D100", "D101", "D103", "D104"]

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["D"]
```

- `line-length = 120` is the longest allowed line. `target-version = "py312"` tells ruff which Python syntax to assume (so it does not suggest features that are newer). `src = ["src", "tests"]` says where first-party code lives, so the import sorter puts project imports in their own block, after the standard library and third-party ones.
- `extend-exclude = ["tech"]` keeps ruff away from the `tech/` notes. Recent ruff versions also format the Python code fences inside Markdown files; the notes quote single lines and fragments (an indented line out of a function, for example), which are not valid stand-alone programs, so they are excluded.
- `select` lists the rule groups:
  - `E`: style errors (for example, over-long lines).
  - `F`: real mistakes found by static analysis (an unused import, an undefined name).
  - `I`: import order and grouping.
  - `B`: likely bugs (for example, a mutable default argument).
  - `UP`: modernise old syntax to the target version.
  - `SIM`: simplifiable code.
  - `N`: naming conventions (classes in `CapWords`, functions in `snake_case`).
  - `C4`: simpler comprehensions.
  - `RUF`: ruff's own rules.
  - `PT`: pytest style (for example, how fixtures and `raises` are written).
  - `D100`, `D101`, `D103`, `D104`: a docstring must exist on every module, public class, public function and package. Documentation is required in `src`.
- `[tool.ruff.lint.per-file-ignores]` gives `"tests/**" = ["D"]`: no docstring rules in tests, whose function names state the behaviour.

## Try it yourself

```bash
make lint
```
Expect `All checks passed!`, then `... files already formatted`, `Success: no issues found ...`, and the import-linter contracts kept.

```bash
.venv/bin/ruff check --select F401 --show-fixes src
```
Looks for unused imports only. Expect none.

```bash
.venv/bin/ruff rule B006
```
Prints the explanation of one rule (mutable default arguments).

```bash
printf 'import os\nx = 1\n' > /tmp/demo_ruff.py && .venv/bin/ruff check /tmp/demo_ruff.py; rm /tmp/demo_ruff.py
```
Shows `F401 os imported but unused` for a throwaway file outside the repository.

## Mistakes people make

- **Formatting by hand** and arguing about it. One formatter decides.
- **Disabling a rule for the whole project** to silence one finding. Here only docstring rules are off, and only in tests.
- **Running ruff with a different config** than CI. Both use `pyproject.toml`.

## Check yourself

1. What is the difference between `ruff check` and `ruff format`? *Check reports rule violations; format rewrites the layout.*
2. What does `select = ["E", "F"]` mean? *Enable every rule starting with those letters.*
3. Why does `src` matter for the `I` rules? *It tells which imports are first-party.*
4. What does `--check` do? *Reports without changing files.*
5. Why `D` is ignored in tests? *Test names state the behaviour; docstrings add noise.*

## Further reading

- ruff 0.17 documentation: https://docs.astral.sh/ruff/
- Rules: https://docs.astral.sh/ruff/rules/
- Settings: https://docs.astral.sh/ruff/settings/
