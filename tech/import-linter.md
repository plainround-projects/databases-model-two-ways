# import-linter

## What it is

import-linter is a tool that checks the **import rules** of a Python project: which module is allowed to import which. A **contract** is one rule written in the configuration file. The tool builds a graph of every `import` in the package and fails when a contract is broken. This repository locks import-linter 2.15 (which uses a graph library called grimp).

## Why this repository uses it

The design says the domain knows nothing about databases and that dependencies point inward. Without a check, one careless import would break that and nothing would notice. The contracts turn the architecture drawing into a test.

## Where it appears

| File | Role |
|---|---|
| `pyproject.toml` | `[tool.importlinter]` and its two contracts. |
| `Makefile` | `lint` runs `.venv/bin/lint-imports`. |

## How it works underneath

`lint-imports` reads the configuration, finds the root package (`rental_shop`), parses every module to find its imports, and builds a graph where an arrow means "imports". A **layers** contract lists layers from highest to lowest; a lower layer must never import a higher one, directly or through other modules. A **forbidden** contract lists modules that must not import (directly or indirectly) certain other modules. `include_external_packages = true` adds third-party packages such as `psycopg` to the graph so they can be named in a contract.

## Walkthrough of this repository's use

```toml
[tool.importlinter]
root_package = "rental_shop"
include_external_packages = true

[[tool.importlinter.contracts]]
name = "Layers: interfaces -> infrastructure -> application -> domain, never upward"
type = "layers"
layers = [
    "rental_shop.interfaces",
    "rental_shop.infrastructure",
    "rental_shop.application",
    "rental_shop.domain",
]

[[tool.importlinter.contracts]]
name = "Domain and application know nothing about PostgreSQL"
type = "forbidden"
source_modules = ["rental_shop.domain", "rental_shop.application"]
forbidden_modules = ["psycopg"]
```

- `root_package = "rental_shop"` is the package to analyse; `include_external_packages = true` allows `psycopg` to be named.
- The first `[[tool.importlinter.contracts]]` is of type `layers` with four layers from top to bottom: interfaces, infrastructure, application, domain. Interfaces may import everything below; infrastructure may import application and domain; application may import only domain; domain imports none of the others. This is the dependency rule of ports-and-adapters.
- The second contract is of type `forbidden`: the sources are `rental_shop.domain` and `rental_shop.application`, and the forbidden module is `psycopg`. Neither layer may reach the driver, even through another module. This is why `application/ports.py` declares `Protocol`s and the adapter implements them.

## Try it yourself

```bash
.venv/bin/lint-imports
```
Expect two lines ending `KEPT` and `Contracts: 2 kept, 0 broken.`

```bash
printf 'import psycopg\n' >> src/rental_shop/domain/period.py && .venv/bin/lint-imports; git checkout src/rental_shop/domain/period.py
```
Adds a forbidden import, shows the broken contract and the offending line, and then restores the file with Git.

```bash
.venv/bin/lint-imports --verbose | head -20
```
More detail about each contract.

## Mistakes people make

- **Relying on code review** to spot a bad import. The contract does it every time.
- **Contracts that only check direct imports.** These also catch indirect chains.
- **Forgetting `include_external_packages`**, so external modules cannot be named.

## Check yourself

1. What does the layers contract forbid? *A lower layer importing a higher one.*
2. What does the forbidden contract protect? *The domain and application from knowing about `psycopg`.*
3. Why is `include_external_packages` needed? *To mention `psycopg` in a contract.*
4. Which command runs the check? *`lint-imports`, run by `make lint`.*
5. Does the check run the program? *No; it parses imports.*

## Further reading

- import-linter 2.15: https://import-linter.readthedocs.io/en/v2.15/
- Contract types: https://import-linter.readthedocs.io/en/v2.15/contract_types/
