# psql

## What it is

`psql` is PostgreSQL's interactive command-line client. You type SQL into it (or feed it a file) and it sends each statement to the server and prints the result as a text table. Lines that start with a backslash, such as `\echo` and `\set`, are **meta-commands**: they are understood by `psql` itself, not sent to the server.

## Why this repository uses it

Every lesson step that is plain SQL runs through it, so the SQL files are the same ones a reader can paste into any PostgreSQL. It runs inside the container, so nothing has to be installed on the host machine.

## Where it appears

| Place | Use |
|---|---|
| `Makefile` (`PSQL`, `PSQL_LOUD`, `psql`, `bulk`, `db`, `queries`, `demo`) | Runs SQL files and single statements. See [make.md](make.md). |
| `scripts/capture_explain.sh` | Feeds queries on standard input and reads one value with `-At`. See [bash.md](bash.md). |
| `sql/004_constraint_demo.sql` | Uses `\set` and `\echo`. |
| `docker-compose.yml` | The health check uses `pg_isready`, a sibling tool. |

## How it works underneath

`psql` opens a connection to the server and runs a loop: read text, split it into statements at semicolons, send each, print the answer. With `docker compose exec -T postgres psql ...`, the process is started inside the container, so it connects through the container's local socket as the user you name. Standard input can be a file (`< file.sql`), which is how the Makefile runs scripts.

**Options used here:**

- `-U user` and `-d database` choose the login and database.
- `-v ON_ERROR_STOP=1` sets a psql variable. With it, the first failing statement ends the run with a non-zero exit code. Without it, psql prints the error and continues, and the exit code is 0. That is why the Makefile uses it, and why `004_constraint_demo.sql` sets `\set ON_ERROR_STOP off` for its demonstration of refusals.
- `-q` is quiet: no banner and no command tags such as `CREATE TABLE`.
- `-c "SQL"` runs one command and exits.
- `-A` is unaligned output and `-t` is tuples only (no headers or footers), used when a script reads one value.

## Walkthrough of this repository's use

```make
PSQL := docker compose exec -T postgres psql -U $(POSTGRES_USER) -d $(POSTGRES_DB) -v ON_ERROR_STOP=1 -q
PSQL_LOUD := docker compose exec -T postgres psql -U $(POSTGRES_USER) -d $(POSTGRES_DB) -v ON_ERROR_STOP=1
```

`PSQL` and `PSQL_LOUD` are the two command lines. They differ in `-q`. `docker compose exec -T postgres` runs the command in the already running `postgres` service without a terminal.

```sql
-- What the constraint does (lesson step 4), as psql shows it. Each case runs in its own transaction and is
-- rolled back, so the hand-checked data stays as it was. ON_ERROR_STOP is off so the refusal is printed
-- and the script goes on (make demo).
\set ON_ERROR_STOP off
```

```sql
\echo '-- overlap: Drill from 11-03 to 11-05 collides with rental 1 (11-01 to 11-04); expect SQLSTATE 23P01'
```

`\set ON_ERROR_STOP off` lets the script go on after a refusal; `\echo '...'` prints a heading. The remaining lines of the file are SQL (see [sql.md](sql.md)).

In `scripts/capture_explain.sh` the command is stored in the variable `PSQL_CMD` and used as `$PSQL_CMD -At -c 'SHOW server_version'` and `$PSQL_CMD < file.sql`.

## Try it yourself

```bash
docker compose exec -T postgres psql -U shop -d rentals -At -c "SELECT version()"
```
One line, unaligned: the server version string.

```bash
docker compose exec -T postgres psql -U shop -d rentals -c '\dt'
```
Lists the tables.

```bash
make psql
```
An interactive session. Type `\d items`, then `\q` to quit.

```bash
echo "SELECT 1/0; SELECT 2;" | docker compose exec -T postgres psql -U shop -d rentals -v ON_ERROR_STOP=1; echo "exit=$?"
```
Prints the division error and a non-zero exit; the second statement is not run.

## Mistakes people make

- **Forgetting `ON_ERROR_STOP`**, so a failed script looks successful.
- **Using `-t` in an interactive session** and being confused by missing headers.
- **Omitting `-T`** when piping into `docker compose exec`, which complains the input is not a terminal.
- **Mixing meta-commands with SQL on one line.** Meta-commands end at the end of the line.

## Check yourself

1. What does a backslash line mean? *A psql meta-command, handled by the client.*
2. What does `ON_ERROR_STOP=1` do? *Ends the run at the first error with a non-zero exit code.*
3. What is the difference between `-c` and `<`? *`-c` runs one given command; `<` feeds a whole file.*
4. What do `-A` and `-t` do together? *Print just the values, unaligned.*
5. Why `-T`? *No terminal is available when input is piped.*

## Further reading

- psql (PostgreSQL 18): https://www.postgresql.org/docs/18/app-psql.html
- `pg_isready`: https://www.postgresql.org/docs/18/app-pg-isready.html
