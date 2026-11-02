# mypy

## What it is

mypy is a **static type checker** for Python. It reads the type hints (`x: int`, `-> str`) without running the program and reports places where a value of the wrong kind is used. "Static" means before the program runs. Python itself ignores hints at run time. This repository locks mypy 2.4.0.

## Why this repository uses it

The ports (interfaces) are declared with `Protocol`. mypy checks that the PostgreSQL adapter and the in-memory fake really have the methods and types the use cases expect. This is what keeps the layers honest.

## Where it appears

| File | Role |
|---|---|
| `pyproject.toml` | `[tool.mypy]` and its override for tests. |
| `Makefile` | `lint` runs `.venv/bin/mypy`. |
| every `.py` file | The hints it checks. |

## How it works underneath

mypy builds a model of every function's parameter and return types, then walks the code and checks that each call, assignment and return fits. A result like `Item | None` means the value may be `None`; mypy then insists that the code check for `None` before using it. A comment `# type: ignore[code]` silences one named finding on that line.

## Walkthrough of this repository's use

```toml
[tool.mypy]
python_version = "3.12"
strict = true
files = ["src", "tests"]

# Test functions are named for the behavior they check; annotating every one adds noise, not safety.
[[tool.mypy.overrides]]
module = ["tests.*"]
disallow_untyped_defs = false
disallow_incomplete_defs = false
disallow_untyped_calls = false
```

- `python_version = "3.12"` is the version to assume.
- `strict = true` switches on all the optional strict checks at once: every function must be fully annotated (`disallow_untyped_defs`), calls into untyped code are reported, `Any` is not allowed to leak, unused ignores are flagged, and more.
- `files = ["src", "tests"]` is what a bare `mypy` command checks.
- The comment above the override states the reasoning: test functions are named for the behavior they check; annotating every one adds noise, not safety. `[[tool.mypy.overrides]]` starts an override for the modules matching `tests.*`. The three `false` lines turn off the three checks that demand annotations on test functions.

The code relies on hints to pass strict mode: `assert row is not None` narrows `tuple | None` to `tuple`; the unreachable `raise AssertionError` at the end of the retry loops satisfies the "missing return" check; `Connection[Any]` marks rows of any shape.

## Try it yourself

```bash
.venv/bin/mypy
```
Expect `Success: no issues found in N source files`.

```bash
printf 'def f(x: int) -> str:\n    return x\n' > /tmp/demo_mypy.py && .venv/bin/mypy /tmp/demo_mypy.py; rm /tmp/demo_mypy.py
```
mypy reports an incompatible return value (int where str is declared), on a throwaway file outside the repository.

```bash
.venv/bin/mypy --strict src/rental_shop/domain
```
Checks just the domain package.

## Mistakes people make

- **Treating hints as run-time checks.** Only mypy enforces them.
- **Sprinkling `# type: ignore`** to make errors go away. This repository has one, on a test line that deliberately passes the wrong type.
- **Using `Any`** everywhere, which disables checking.

## Check yourself

1. Does Python check hints when it runs? *No; mypy does it before.*
2. What does `strict = true` do? *Turns on all the strict options.*
3. Why does the code use `assert row is not None`? *To narrow `tuple | None` to `tuple` for the checker.*
4. Why are the tests partially exempt? *Annotating every test function adds noise.*
5. What is a `Protocol` check? *mypy verifies a class has the required methods and types.*

## Further reading

- mypy 2.4 documentation: https://mypy.readthedocs.io/en/stable/
- Command line and config file: https://mypy.readthedocs.io/en/stable/config_file.html
- Protocols: https://mypy.readthedocs.io/en/stable/protocols.html
