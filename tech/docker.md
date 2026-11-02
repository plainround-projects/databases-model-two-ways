# Docker

## What it is

Docker is a tool that runs programs inside **containers**. A container is an ordinary process that the operating system has fenced off: it sees its own file system, its own network and its own list of processes, and it cannot see the rest of the machine unless you open a door on purpose. An **image** is the frozen, read-only recipe result that a container starts from: a stack of file-system layers plus a default command. A **Dockerfile** is the text file that says how to build an image.

## Why this repository uses it

Two reasons. The database itself runs from a ready-made image (`postgres:18`), see [docker-compose.md](docker-compose.md). And the lesson's command-line programs can be packaged as an image so they run the same on any machine; this is what the `Dockerfile` does. Nothing in it serves traffic: it is a way to ship the four programs and a health check.

## Where it appears

| File | What it does with Docker |
|---|---|
| `Dockerfile` | Builds the image of the Python programs. |
| `.dockerignore` | Lists what the build must not copy in. |
| `Makefile` (`docker-build`) | Runs `docker build -t databases-model-two-ways:dev .`. |
| `docker-compose.yml` | Starts PostgreSQL from an image. See [docker-compose.md](docker-compose.md). |

## How it works underneath

`docker build` sends the **build context** (the folder you name, here `.`) to the Docker engine, which is a background service. The engine reads the Dockerfile from top to bottom. Most instructions create one **layer**, a stored set of file changes. A layer is cached by the text of its instruction plus the files it used, so if nothing changed, the next build reuses it. That is why the order of the instructions matters: put the slow, rarely changing steps first and the often changing steps last.

`docker run image` creates a container: the engine stacks the layers, adds a thin writable layer on top, and starts the image's command as a process. When the process ends, the container stops. A **health check** is a command that Docker runs from time to time inside the container; its exit code (0 healthy, 1 unhealthy) is shown in `docker ps`.

An **environment variable** is a named text value that every process receives from its parent. The `ENV` instruction sets some for every container of the image.

## Walkthrough of this repository's use

### The comments and the base image

```dockerfile
# The command-line programs as an image. Nothing here serves traffic; the health command is the image's check.
# Run against a PostgreSQL the container can reach, for example:
#   docker run --rm --network host -e POSTGRES_PASSWORD=... databases-model-two-ways:dev rental-shop-report
FROM python:3.13.1-slim-bookworm
```

Lines 1 to 3 are comments saying what the image is for and how to run it against a database. `--rm` deletes the container after it exits; `--network host` lets the container reach `localhost` of the machine, where PostgreSQL's port is published; `-e` hands an environment variable to the container.

`FROM python:3.13.1-slim-bookworm` chooses the starting image. `python` is the image name, `3.13.1` the exact Python version (a pinned version, so a build next year gives the same interpreter), `slim` means a smaller variant without compilers and extra tools, and `bookworm` is the name of the Debian Linux release it is based on. Every Dockerfile begins with `FROM`.

### Environment variables for Python and pip

```dockerfile
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
```

`ENV` sets variables for the build steps that follow and for the running container. A backslash at the end of a line continues the instruction on the next line.

- `PYTHONDONTWRITEBYTECODE=1`: Python normally writes `.pyc` files (compiled versions of source) into `__pycache__` folders. In a container they only make the image larger.
- `PYTHONUNBUFFERED=1`: Python normally collects printed text in a memory buffer and writes it in chunks. With this set, each line is written at once, so `docker logs` shows it immediately.
- `PIP_NO_CACHE_DIR=1`: pip keeps downloaded packages in a cache folder; in an image that cache is dead weight.
- `PIP_DISABLE_PIP_VERSION_CHECK=1`: stops pip from contacting the internet to check for its own new version, which would slow and clutter every build.

### Dependencies first, then the code

```dockerfile
WORKDIR /app
COPY requirements.lock ./
RUN pip install --require-hashes -r requirements.lock

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-deps .
```

- `WORKDIR /app` creates the folder `/app` and makes it the current folder for all later instructions.
- `COPY requirements.lock ./` copies one file from the build context into the image. The `./` means "the current folder", so `/app/`.
- `RUN pip install --require-hashes -r requirements.lock` runs a command during the build. `--require-hashes` makes pip accept a package only if its hash (a fingerprint of the file) matches the one in the lock, so a changed or swapped download is rejected. This layer only depends on `requirements.lock`, so it is rebuilt only when that file changes.
- `COPY pyproject.toml README.md ./` copies the packaging description and the README (the build backend needs the README because `pyproject.toml` names it).
- `COPY src ./src` copies the source code. This layer changes on every code edit, which is why it comes after the slow install.
- `RUN pip install --no-deps .` installs this project's own package. `--no-deps` means "do not look for dependencies again": they are already installed from the lock, and the lock is the single source of truth.

### A user that is not root

```dockerfile
RUN useradd --system --uid 10001 --no-create-home app
USER app
```

By default a container process runs as `root`, the all-powerful user. If a program inside were compromised, root would make the damage larger. `useradd --system --uid 10001 --no-create-home app` creates an account named `app`; `--system` marks it as a service account, `--uid 10001` gives it a fixed numeric id that will not collide with a human user, and `--no-create-home` skips making a personal folder. `USER app` makes every later instruction and the container's main process run as that account.

### Health check and default command

```dockerfile
HEALTHCHECK --interval=30s --timeout=20s --retries=3 CMD ["rental-shop-health"]
CMD ["rental-shop-health"]
```

- `HEALTHCHECK --interval=30s --timeout=20s --retries=3 CMD ["rental-shop-health"]`: every 30 seconds Docker runs the program `rental-shop-health` inside the container. If it takes longer than 20 seconds it counts as a failure, and after three failures in a row the container is marked `unhealthy`. The list form `["program"]` runs the program directly without a shell (the "exec form").
- `CMD ["rental-shop-health"]` is the command a container runs when no other is given. `rental-shop-health` is one of the four programs that `pyproject.toml` declares (see [toml.md](toml.md)).

### `.dockerignore`

```text
.git
.venv
logs
tests
docs
sql
**/__pycache__
.mypy_cache
.ruff_cache
.pytest_cache
.coverage
.env
```

When `docker build .` runs, Docker first packs the build context. `.dockerignore` removes files from that pack, with the same pattern style as `.gitignore`.

- `.git` is the version-control history, large and irrelevant to the image.
- `.venv` is the local virtual environment. It holds a Python built for the Mac or Linux host; copying it into a different image would break.
- `logs`, `tests`, `docs`, `sql` are not needed at run time.
- `**/__pycache__` matches a `__pycache__` folder at any depth; `.mypy_cache`, `.ruff_cache`, `.pytest_cache` and `.coverage` are tool caches and reports.
- `.env` holds the local password and must never be baked into an image where anyone who pulls it could read it.

## Try it yourself

```bash
make docker-build
```
Expect the build to end with a line naming `databases-model-two-ways:dev`. Run it twice: the second time almost every step prints `CACHED`.

```bash
docker image inspect databases-model-two-ways:dev --format '{{.Config.User}} {{.Config.Healthcheck.Test}}'
```
Prints `app` and the health check command.

```bash
docker run --rm --entrypoint id databases-model-two-ways:dev
```
Runs the program `id` instead of the default command; expect `uid=10001(app)` and no `uid=0`.

```bash
docker run --rm --entrypoint python databases-model-two-ways:dev -c "import psycopg; print(psycopg.__version__)"
```
Shows the pinned library is installed in the image.

## Mistakes people make

- **Copying the code before installing dependencies**, which re-installs everything on every edit. Here the lock file is copied and installed first.
- **Running as root.** The image switches to `app`.
- **Baking secrets in.** `.env` is ignored and the password is passed with `-e` at run time.
- **Unpinned base images** (`FROM python`). A version tag keeps builds repeatable.
- **Forgetting `--no-deps`** and silently letting pip pick newer, untested versions.

## Check yourself

1. What is the difference between an image and a container? *An image is the stored result of a build; a container is a running process started from it.*
2. Why are `requirements.lock` and `src` copied by separate `COPY` lines? *So the slow dependency layer is cached and only the code layer is rebuilt on edits.*
3. What does `--require-hashes` protect against? *A downloaded package that differs from the one recorded in the lock.*
4. Why does `.dockerignore` list `.env`? *To keep the local password out of the build context and so out of the image.*
5. What does `HEALTHCHECK` run and how often? *`rental-shop-health`, every 30 seconds, failing after three failures in a row.*

## Further reading

- Dockerfile reference: https://docs.docker.com/reference/dockerfile/
- Docker build cache: https://docs.docker.com/build/cache/
- The `python` image (tag 3.13.1-slim-bookworm): https://hub.docker.com/_/python
