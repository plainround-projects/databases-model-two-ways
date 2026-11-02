# The .env file

## What it is

A `.env` file is a plain text file of `NAME=value` lines, one per line, that holds settings for a program. The name `.env` starts with a dot, which makes it hidden in most file lists. It is not a technology with a specification; it is a convention that Make, Docker Compose and many tools understand. `#` starts a comment line.

## Why this repository uses it

The database name, user, port and password are settings, not code. Keeping them in `.env` (which is never committed) means no password lives in the source, and one place changes every program.

## Where it appears

| File | Role |
|---|---|
| `.env.example` | The template that is committed. |
| `.env` | The real copy, created by `make env` and ignored by Git and Docker (`.gitignore`, `.dockerignore`). |
| `Makefile` | Reads `.env` with `-include .env` and exports it. |
| `docker-compose.yml` | Takes `${POSTGRES_PORT}`, `${POSTGRES_USER}` and the others from the environment. |
| `src/rental_shop/infrastructure/settings.py` | Reads the same variables in Python. See [python-stdlib.md](python-stdlib.md). |

## How it works underneath

An **environment variable** is a named piece of text that a process inherits from the process that started it. Nothing reads `.env` by itself: Make reads it and passes the values on as environment variables to every command (`export`), and those commands, `docker compose` and `python`, read the variables. The values are text only; a port is the text `5441` until the code turns it into a number.

## Walkthrough of this repository's use

```bash
# Copy to .env (make up does it the first time). Every variable has a default except the password.
# The password below is a throwaway for a database that lives only on this machine while the container runs.
POSTGRES_HOST=localhost
POSTGRES_PORT=5441
POSTGRES_DB=rentals
POSTGRES_USER=shop
POSTGRES_PASSWORD=local-only-change-me
# Schema the programs use (default public). The integration tests set their own.
POSTGRES_SCHEMA=public
POSTGRES_CONNECT_TIMEOUT_SECONDS=5
POSTGRES_STATEMENT_TIMEOUT_MS=30000
LOG_LEVEL=INFO
```

- Line 1 says the file is copied by `make up` the first time, and that every variable has a default in the code except the password.
- Line 2 explains the password: it is a throwaway for a database that lives only on this machine while the container runs. It is acceptable for it to be in the example file because it protects nothing real.
- `POSTGRES_HOST=localhost` is the machine the programs connect to; `POSTGRES_PORT=5441` the port that Compose publishes (see [docker-compose.md](docker-compose.md)); `POSTGRES_DB=rentals` and `POSTGRES_USER=shop` name the database and the login; `POSTGRES_PASSWORD` is the password.
- Line 8 and `POSTGRES_SCHEMA=public` choose the schema, the namespace inside a database that holds the tables (see [postgresql.md](postgresql.md)); the integration tests set their own, so tests never touch the lesson's tables.
- `POSTGRES_CONNECT_TIMEOUT_SECONDS=5` is how long to wait to open a connection, and `POSTGRES_STATEMENT_TIMEOUT_MS=30000` is the longest a single statement may run (30 seconds, in milliseconds) before PostgreSQL cancels it.
- `LOG_LEVEL=INFO` is how detailed the logs are.

## Try it yourself

```bash
make env && grep -c '=' .env
```
Creates `.env` if missing (never overwrites) and counts the assignment lines.

```bash
POSTGRES_PORT=5999 docker compose config | grep 5999
```
A variable in your shell wins over the file: the published port becomes 5999.

```bash
git check-ignore -v .env
```
Names the `.gitignore` line that keeps the file out of Git.

## Mistakes people make

- **Committing `.env`.** The file is in `.gitignore` and `.dockerignore`.
- **Spaces around `=`.** Make and Compose treat them differently; this file has none.
- **Quoting differences:** Make would keep quotes as part of the value; this file uses no quotes.

## Check yourself

1. Why is there `.env.example` and `.env`? *The example is committed as a template; the real one is local and ignored.*
2. Who reads `.env`? *Make (which exports to children); the programs read the environment variables.*
3. Are the values numbers? *No, text; the code converts them.*
4. Why is the password in the example acceptable? *It is a throwaway for a local database.*
5. How do you override one value once? *Put it before the command, as `POSTGRES_PORT=5999 command`.*

## Further reading

- Compose environment variables: https://docs.docker.com/compose/how-tos/environment-variables/
- GNU Make `include` and `export`: https://www.gnu.org/software/make/manual/make.html#Include
