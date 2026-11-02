# pip, venv and the lock files

## What it is

**pip** is Python's package installer: it downloads libraries (**packages**) from the Python Package Index (PyPI) and installs them. A **virtual environment** (made with the standard `venv` module) is a private folder holding its own Python and its own installed packages, so one project's libraries do not mix with another's. A **lock file** lists every package, down to the exact version and a cryptographic fingerprint of each file, so every install gets the same thing.

## Why this repository uses it

Reproducibility and safety. `requirements.lock` fixes the run-time dependencies (used by the Docker image) and `requirements-dev.lock` fixes those plus the development tools (used by `make install` and CI). With `--require-hashes`, pip refuses any file whose fingerprint differs from the lock, which blocks a swapped or tampered download.

## Where it appears

| File | Role |
|---|---|
| `requirements.lock` | Exact run-time dependencies: psycopg and psycopg-binary with their hashes. |
| `requirements-dev.lock` | Run-time plus development tools, all pinned with hashes. |
| `Makefile` (`$(STAMP)` target) | Creates `.venv` and installs from the lock. See [make.md](make.md). |
| `Dockerfile` | `pip install --require-hashes -r requirements.lock`. See [docker.md](docker.md). |
| `.gitignore`, `.dockerignore` | Keep `.venv` out of Git and out of the image. |

## How it works underneath

`python3 -m venv .venv` copies (or links) the Python program into `.venv/bin/` and creates an empty `site-packages` folder where installed packages go. Running `.venv/bin/python` uses that folder first. `.venv/bin/pip install ...` installs into it. No activation is needed if you call the programs in `.venv/bin/` by path, which is what the Makefile does.

A **hash** is a short fixed-size fingerprint computed from a file's bytes; if one byte changes, the hash changes completely. A lock line looks like `package==version \` followed by `--hash=sha256:...` lines (one per downloadable file, since each platform has its own). `# via ...` comment lines record why a package is there. `-e .` installs the project **editable**: the installed copy points at your source, so changes apply immediately.

## Walkthrough of this repository's use

The install recipe (from `Makefile`, explained line by line in [make.md](make.md)):

```make
$(STAMP): requirements-dev.lock pyproject.toml
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/pip install -q --require-hashes -r requirements-dev.lock
	$(VENV)/bin/pip install -q --no-deps -e .
	touch $@

install: $(STAMP) ## create .venv from the lock file
```

- `$(PYTHON) -m venv $(VENV)` creates the environment.
- `pip install -q --require-hashes -r requirements-dev.lock` installs exactly the locked packages. `--require-hashes` also forces every dependency to be pinned with `==`, otherwise pip stops.
- `pip install -q --no-deps -e .` installs this project in editable mode without touching dependencies.

The Dockerfile uses the run-time lock only (no development tools in the image), then installs the project:

```dockerfile
WORKDIR /app
COPY requirements.lock ./
RUN pip install --require-hashes -r requirements.lock

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-deps .
```

The first lines of a lock file show how it was generated (`uv pip compile pyproject.toml --universal --generate-hashes --python-version 3.12`, see [uv.md](uv.md)): `--universal` resolves for all platforms at once, which is why a line can end with a marker such as `; implementation_name != 'pypy'` (install only on the standard CPython interpreter).

## Try it yourself

```bash
make install && .venv/bin/python -c "import sys; print(sys.prefix)"
```
Prints the `.venv` folder: the interpreter is the private copy.

```bash
.venv/bin/pip list | head -20
```
Lists installed packages with versions; compare with `requirements-dev.lock`.

```bash
head -8 requirements.lock
```
Shows the header comment and the first pinned package with its hashes.

```bash
.venv/bin/pip install --require-hashes psycopg==3.3.6
```
Fails with `Hashes are required in --require-hashes mode`, because no hash was given on the command line.

## Mistakes people make

- **Installing into the system Python.** Use a virtual environment.
- **Committing `.venv`.** It is ignored.
- **Unpinned installs** (`pip install psycopg`), which give a different version on each date. The lock pins everything.
- **Editing a lock file by hand.** Regenerate it.

## Check yourself

1. What does a virtual environment isolate? *Installed packages (and the Python copy) for one project.*
2. What does `--require-hashes` check? *Every downloaded file matches the fingerprint in the lock.*
3. What does `-e .` do? *Installs the project so edits take effect without reinstalling.*
4. Why two lock files? *Run-time only for the image; run-time plus tools for development.*
5. Why call `.venv/bin/python` instead of activating? *The path itself selects the environment; there is nothing to forget.*

## Further reading

- pip 24 user guide (hash-checking mode): https://pip.pypa.io/en/stable/topics/secure-installs/
- `venv`: https://docs.python.org/3.13/library/venv.html
- Requirements file format: https://pip.pypa.io/en/stable/reference/requirements-file-format/
