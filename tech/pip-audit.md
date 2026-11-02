# pip-audit

## What it is

pip-audit checks installed or pinned Python packages against a database of known security vulnerabilities (the Python Packaging Advisory Database, and OSV). It prints each vulnerable package with the advisory number and the version that fixes it, and exits with a non-zero code if it finds any. This repository locks pip-audit 2.10.1.

## Why this repository uses it

A pinned dependency never updates by itself, so a newly found vulnerability would go unnoticed. `make audit` and the CI job look the locked versions up on every run.

## Where it appears

| File | Role |
|---|---|
| `Makefile` | The `audit` target. |
| `.github/workflows/ci.yml` | Runs `make audit` in the `check` job. |
| `requirements-dev.lock` | The input that is audited. |

## How it works underneath

pip-audit reads a list of name and version pairs and sends them to the vulnerability service over the network. The service replies with advisories that match. Because it needs network access, it is a separate step from the offline tests.

## Walkthrough of this repository's use

```make
audit: $(STAMP) ## check the locked dependencies for known vulnerabilities
	$(VENV)/bin/pip-audit --no-deps --disable-pip -r requirements-dev.lock
```

`$(VENV)/bin/pip-audit --no-deps --disable-pip -r requirements-dev.lock` audits the file given with `-r`. `--no-deps` means "do not look for other dependencies": every dependency is already listed and pinned in the lock. `--disable-pip` means "do not create a temporary environment with pip to resolve the requirements"; with fully pinned hashes in the file that step is not needed, and it keeps the check fast and exact.

## Try it yourself

```bash
make audit
```
Needs network. Expect `No known vulnerabilities found` (it may also say that some packages were skipped, which is normal for local ones).

```bash
.venv/bin/pip-audit --version
```
Prints 2.10.1.

```bash
.venv/bin/pip-audit --no-deps --disable-pip -r requirements.lock
```
Audits only the run-time lock, the packages that ship in the image.

## Mistakes people make

- **Auditing without pins**, which audits whatever pip happens to resolve today.
- **Ignoring a finding** without a note. Update the pin or record why not.
- **Running it only occasionally.** It runs in CI on every push.

## Check yourself

1. What does it compare? *Pinned versions against known advisories.*
2. Why `--no-deps`? *The lock already lists every dependency.*
3. Does it need the network? *Yes.*
4. What exit code means a finding? *A non-zero one.*
5. Which file is audited by `make audit`? *`requirements-dev.lock`.*

## Further reading

- pip-audit 2.10: https://pypi.org/project/pip-audit/2.10.1/
- Python Packaging Advisory Database: https://github.com/pypa/advisory-database
