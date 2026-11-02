# Docker Compose

## What it is

Docker Compose is a command (`docker compose`) that starts one or more containers described in a single YAML file, `docker-compose.yml`. Each container in the file is a **service**. Compose creates the network between them, starts them in a sensible order and removes them again with one command. YAML is explained in [yaml.md](yaml.md).

## Why this repository uses it

The lesson needs a real PostgreSQL 18 server. Compose gives every reader the same server with one command (`make up`), with the right settings and without installing PostgreSQL on the machine.

## Where it appears

| File | What it does with Compose |
|---|---|
| `docker-compose.yml` | Defines the one `postgres` service. |
| `Makefile` | `up`, `psql`, `down` and the `PSQL` command lines use `docker compose`. See [make.md](make.md). |

## How it works underneath

`docker compose up` reads the YAML, pulls the image if it is missing, creates a **project** (a group of containers with a shared name) and a private virtual network, and starts each service as a container. A **port mapping** `HOST:CONTAINER` makes a port on your machine forward to a port inside the container. A **health check** is a command Compose runs inside the container on a timer; the service is `healthy` once it exits 0. `up --wait` waits for that.

Before reading the file, Compose replaces `${NAME}` with the value of the environment variable `NAME` (or from a `.env` file in the same folder). `${NAME:-default}` uses `default` when `NAME` is empty. `${NAME:?message}` stops with `message` when it is empty. A literal dollar sign for the container's shell is written `$$`.

## Walkthrough of this repository's use

```yaml
# One PostgreSQL 18 for local use only.
name: databases-model-two-ways

services:
  postgres:
    image: postgres:18
```

- Line 1 is a comment. `name:` sets the project name, which prefixes the container, network and volume names; without it Compose would use the folder name.
- `services:` starts the map of containers. `postgres:` is this service's name (used by `docker compose exec postgres ...`). `image: postgres:18` is the image to start (pulled from Docker Hub if absent). The tag 18 means the major version 18 of PostgreSQL.

```yaml
    # deadlock_timeout is how long a session waits on a lock before PostgreSQL looks for a deadlock (default 1s).
    # Contenders racing for one item can deadlock on each other's uncommitted rows (see ARCHITECTURE.md); the
    # lab checks sooner so the 20 races finish in seconds. It changes how fast a deadlock is found, not whether
    # the exclusion constraint holds.
    command: ["postgres", "-c", "deadlock_timeout=100ms"]
```

The comment explains the one non-default setting. A **deadlock** is a situation where two transactions each wait for a lock the other holds, so neither can go on. PostgreSQL looks for deadlocks only after a session has waited `deadlock_timeout` (default one second). The lab starts 20 contenders on purpose, so a shorter wait makes the races finish in seconds. `command:` replaces the image's default command: it runs the `postgres` server with `-c deadlock_timeout=100ms`, where `-c` sets one configuration parameter. It speeds up the finding of deadlocks and does not change what the exclusion constraint allows.

```yaml
    ports:
      - "${POSTGRES_PORT:-5441}:5432"
```

`ports:` is a list. `"${POSTGRES_PORT:-5441}:5432"` publishes the container's port 5432 (PostgreSQL's usual port) on the host's port 5441, or on the port in `POSTGRES_PORT`. 5441 avoids a clash with a PostgreSQL that may already use 5432. The quotes keep it a text value: Compose's documentation asks for quotes on port mappings because older YAML readers turn a bare `22:22` into a base-60 number.

```yaml
    environment:
      # Credentials come from .env (make up copies .env.example the first time); none is written here.
      POSTGRES_USER: ${POSTGRES_USER:-shop}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?copy .env.example to .env first}
      POSTGRES_DB: ${POSTGRES_DB:-rentals}
```

`environment:` sets environment variables inside the container; the PostgreSQL image reads them on first start to create the database. `POSTGRES_USER` and `POSTGRES_DB` fall back to `shop` and `rentals`. `POSTGRES_PASSWORD` uses `:?`, so without a value Compose stops and prints "copy .env.example to .env first". No password is written in the file.

```yaml
    healthcheck:
      # -h 127.0.0.1: during first-start initialization the temporary server listens on the socket only, so a TCP
      # check turns healthy only once the real server is up, and `make db` never races the restart.
      test: ["CMD-SHELL", "pg_isready -h 127.0.0.1 -U $${POSTGRES_USER} -d $${POSTGRES_DB}"]
      interval: 3s
      timeout: 5s
      retries: 20
```

- `healthcheck:` defines the readiness probe. `test:` with `CMD-SHELL` passes the string to the container's shell. `pg_isready` is PostgreSQL's own program that asks "is the server accepting connections?"; `-h 127.0.0.1` forces a network (TCP) connection, `-U` and `-d` name the user and database. `$${POSTGRES_USER}` is written with two dollars so Compose leaves it alone and the shell inside the container expands it.
- The comment gives the reason for `-h 127.0.0.1`: during the very first start the image runs a temporary server that listens on a local socket file only. A check over TCP is false until the real server is up, so the lab never races the restart.
- `interval: 3s` is the time between checks, `timeout: 5s` the longest a check may take, `retries: 20` how many failed checks are tolerated before the service is `unhealthy`.

## Try it yourself

```bash
make env && docker compose config | head -30
```
Prints the file after substitution: the port is `5441` and the password comes from `.env`.

```bash
make up && docker compose ps
```
The `postgres` row ends with `(healthy)` and shows `0.0.0.0:5441->5432/tcp`.

```bash
docker compose exec -T postgres psql -U shop -d rentals -c 'SHOW deadlock_timeout'
```
Expect `100ms`.

```bash
POSTGRES_PASSWORD= docker compose config
```
Expect the error `copy .env.example to .env first`.

```bash
make down
```
Stops the container and deletes the data volume.

## Mistakes people make

- **Using `$` where `$$` is needed**, so Compose substitutes a value instead of the shell. The health check uses `$$`.
- **Writing a password in the file.** This file reads it from `.env`.
- **Leaving ports unquoted**, which YAML may parse as a number.
- **Starting dependants before the database is ready.** `make up` uses `--wait`.
- **Expecting data to survive `down -v`.** The `-v` deletes volumes.

## Check yourself

1. What does `5441:5432` mean? *Host port 5441 forwards to container port 5432.*
2. Why is the password written with `:?`? *Compose stops with a clear message if it is missing.*
3. What is a health check for? *It tells Compose when the service is truly ready, so `--wait` can return.*
4. What does `command:` do here? *It replaces the image's default command with `postgres -c deadlock_timeout=100ms`.*
5. Why `$${POSTGRES_USER}` in the health check? *So the shell in the container reads the variable, not Compose.*

## Further reading

- Compose file reference: https://docs.docker.com/reference/compose-file/
- Interpolation: https://docs.docker.com/reference/compose-file/interpolation/
- The `postgres` image (tag 18): https://hub.docker.com/_/postgres
