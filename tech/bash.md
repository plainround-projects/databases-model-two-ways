# Bash

## What it is

Bash is a **shell**: a program that reads text commands and runs other programs for you. A **shell script** is a plain text file of such commands, so that a sequence you would type by hand can be repeated exactly. Bash is the shell most Linux machines and many Macs use. Every command in a script is either a **built-in** (a command Bash itself carries out, such as `cd` or `echo`) or an **external program** (a separate program on disk, such as `date` or `head`).

## Why this repository uses it

The lesson asks for plans captured on 100,000 rentals. That needs the same steps every time: load the data, drop the constraint, capture a plan, add the constraint, capture a plan again. A script makes the capture repeatable, so the plan files in `sql/explain/` can be regenerated and compared. There is one script, `scripts/capture_explain.sh`.

## Where it appears

| File | What it does with Bash |
|---|---|
| `scripts/capture_explain.sh` | Runs every query in `sql/explain/` through `psql` and writes the plan text next to it. |
| `Makefile` | Every recipe line is handed to a shell (`/bin/sh` by default). The recipes use shell features such as `[ -f .env ]`, `||`, `{ ...; }`, `<` redirection and `$(...)`. See [make.md](make.md). |
| `docker-compose.yml` | The health check uses `CMD-SHELL`, which hands a string to the container's shell. See [docker-compose.md](docker-compose.md). |

## How it works underneath

When you type `./scripts/capture_explain.sh`, the operating system starts a new **process** (a running program with its own memory and its own list of open files). The first line of the file tells it which program should read the rest. Bash reads the file one command at a time. For each command it finds the program, starts it as a child process, waits for it to finish and looks at its **exit code**.

An exit code is a number a finished program leaves behind. `0` means success. Any other number means some kind of failure. Bash stores the latest one in `$?`. A script that ignores exit codes will carry on after a failure and may write wrong output, so the first thing a careful script does is ask Bash to stop at the first failure.

Every process starts with three **standard streams**, which are open channels numbered 0, 1 and 2. Stream 0 is **standard input** (where the program reads), 1 is **standard output** (where it prints results) and 2 is **standard error** (where it prints complaints). The terminal is usually attached to all three. The operators `<`, `>` and `|` re-attach these streams: `< file` feeds a file into stream 0, `> file` sends stream 1 into a file (creating it or emptying it), and `a | b` connects the output of `a` to the input of `b`.

**Variables** hold text. `name=value` sets one, `$name` or `${name}` reads it. An **environment variable** is a variable that is copied into every child process, which is how `make` passes `PSQL_CMD` to this script. **Quoting** controls word splitting: inside double quotes, `"$1"` stays one word even if it contains spaces; outside quotes, Bash cuts the text at spaces and expands wildcards. Always quote variables that hold file names.

## Walkthrough of this repository's use

### The first line and the header comment

```bash
#!/usr/bin/env bash
# Writes sql/explain/*.txt: EXPLAIN (ANALYZE, BUFFERS) of the shop's queries on 100,000 rentals.
# Expects the seed plus sql/bulk/100k_rentals.sql to be loaded (make explain does that) and PSQL_CMD to hold the
# command that runs a SQL file on stdin, for example: docker compose exec -T postgres psql -U shop -d rentals -q
# The availability query is captured twice, without and with the step-4 exclusion constraint.
```

Line 1 is a **shebang**: the two characters `#!` followed by the path of the program that should run the file. `/usr/bin/env bash` means "find `bash` on the search path (`PATH`, the list of folders where programs live) and use that". It is more portable than writing `/bin/bash`, because Bash is not in the same place on every machine. Because the file is marked executable (`chmod +x`), `./scripts/capture_explain.sh` starts it directly.

Lines 2 to 5 start with `#`. A `#` makes Bash ignore the rest of the line, so these lines are comments for readers. They state the contract: the data must be loaded already, and the environment variable `PSQL_CMD` must hold the command that runs a SQL file when the file is fed on standard input. The query is captured twice, once without and once with the exclusion constraint.

### Fail fast and move to the repository root

```bash
set -euo pipefail
cd "$(dirname "$0")/.."
```

`set` changes how Bash behaves. The three letters after `-` are options, and `-o pipefail` is an option with a separate name:

- `-e` (errexit): stop the script as soon as any simple command exits with a non-zero code. Without it, a failed `psql` would be ignored and the script would write a half-empty plan file.
- `-u` (nounset): treat a read of a variable that was never set as an error, instead of silently reading it as an empty string. A typo such as `$PSQL_CDM` would otherwise run an empty command.
- `-o pipefail`: a pipeline `a | b | c` normally takes the exit code of the last command only. With `pipefail`, the pipeline fails if any command in it fails, so `-e` can notice.

Line 7 is `cd "$(dirname "$0")/.."`:

- `$0` is the path this script was started with, for example `./scripts/capture_explain.sh`.
- `dirname` is a program that prints the folder part of a path, here `./scripts`.
- `$( ... )` is **command substitution**: Bash runs what is inside, then puts its output in place of the whole expression.
- `/..` goes one folder up, so the result is the repository root.
- `cd` changes the script's working folder to that root. All the relative paths later in the script (`sql/explain`, `sql/migrations/...`) now work no matter where the user was standing when starting it.
- The double quotes keep the path in one piece if it ever contains a space.

### A required variable

```bash
: "${PSQL_CMD:?set PSQL_CMD to a command that runs SQL from stdin}"
out=sql/explain
```

Line 9 uses `: "${PSQL_CMD:?message}"`. The colon `:` is a built-in command that does nothing and always succeeds; it exists so that Bash has a command to run while expanding its argument. The expansion `${NAME:?message}` means: if `NAME` is unset or empty, print `message` to standard error and stop with an error. So if someone runs the script without `PSQL_CMD`, they are told exactly what to set. Line 10 stores the folder name `sql/explain` in `out` so the later lines are shorter and a rename touches one place.

### A function that captures one query

```bash
capture() { # capture <query-file> <output-file> <label>
  {
    echo "-- $3"
    echo "-- captured $(date -u +%Y-%m-%d) on $($PSQL_CMD -At -c 'SHOW server_version' | head -1), 100,000 rentals, after ANALYZE"
    echo "-- source: $1"
    echo
    $PSQL_CMD < "$1"
  } > "$2"
  echo "wrote $2"
}
```

- `capture() { ... }` defines a **function**, a named group of commands that is run by writing its name. The trailing comment documents the three arguments. Inside a function, `$1`, `$2` and `$3` are the first three arguments (the query file, the output file and the label).
- The braces on line 13 and 19 form a **command group**: everything printed inside them is collected as one stream. The `> "$2"` on line 19 sends that whole stream into the output file, truncating it first.
- `echo "-- $3"` prints the label as a SQL comment (`--` starts a comment in SQL), so the plan file stays valid SQL-looking text with a self-explaining header.
- Line 15 builds the second header line from three pieces. `$(date -u +%Y-%m-%d)` prints today's date in UTC (`-u`) as year-month-day. `$($PSQL_CMD -At -c 'SHOW server_version' | head -1)` runs `psql` with `-A` (unaligned output), `-t` (tuples only: no headers or row counts) and `-c` (run this one command), asks the server for its version, and keeps only the first line with `head -1`. Writing the version into the file records what PostgreSQL produced the plan.
- `echo` with nothing after it (line 17) prints an empty line to separate the header from the plan.
- Line 18, `$PSQL_CMD < "$1"`, runs the stored command with the query file connected to its standard input. The variable is deliberately **not** quoted, so Bash splits it into words (`docker`, `compose`, `exec` and so on), which is how a command stored in a variable is run.
- Line 20 prints `wrote <file>` so the person watching the terminal sees progress.

### Warm-up and the "before" capture

```bash
# Settle statistics and warm the cache once, so the plans are not dominated by the bulk load.
echo "ANALYZE rentals; ANALYZE items; ANALYZE customers;" | $PSQL_CMD
echo "SELECT count(*) FROM rentals;" | $PSQL_CMD > /dev/null

# Before: no exclusion constraint, so no index covers (item_id, during).
echo "ALTER TABLE rentals DROP CONSTRAINT rentals_item_id_during_excl;" | $PSQL_CMD
capture "$out/q1_is_item_free.sql" "$out/q1_is_item_free_before.txt" "before the constraint: no index on (item_id, during)"
```

- Line 24 pipes a string into `psql`. `ANALYZE` makes PostgreSQL re-measure each table, so the planner's row estimates reflect the 100,000 rentals instead of the tiny seed. Three tables are listed, each ending with a semicolon.
- Line 25 reads every rental once (`count(*)`) so that the first captured plan is not slower than the others because the table pages were still on disk. Its output is thrown away with `> /dev/null`, a special file that discards everything written to it.
- Line 28 removes the exclusion constraint (`ALTER TABLE ... DROP CONSTRAINT`), and with it the index that backs it, to get the "before" state. Line 29 calls `capture` with three quoted arguments.

### The "after" capture and the loop

```bash
# After: the migration of lesson step 4 adds the constraint and its GiST index.
$PSQL_CMD < sql/migrations/001_exclusion_constraint.sql
echo "ANALYZE rentals;" | $PSQL_CMD
capture "$out/q1_is_item_free.sql" "$out/q1_is_item_free_after.txt" "after the constraint: its GiST index answers the check"
for query in q2_free_next_weekend q3_customer_history q4_returns_today q5_revenue_per_item_and_month q6_never_rented; do
  capture "$out/$query.sql" "$out/$query.txt" "with the constraint and the lesson's indexes"
done
```

- Line 32 re-applies the lesson's migration by feeding the file into `psql`; it adds the extension, the constraint and so the index back.
- Line 33 analyzes the rentals again so the new index has statistics.
- Line 34 captures the same query a second time under a different file name.
- Lines 35 to 37 are a `for` loop. `for query in a b c; do ...; done` runs the body once per word, with `query` set to each word. The body calls `capture` for the five other query files, building the file names with `"$out/$query.sql"`. The loop covers q2 to q6 and writes `sql/explain/q2_free_next_weekend.txt` and its siblings.

## Try it yourself

Run these from the repository root.

```bash
bash -n scripts/capture_explain.sh && echo "syntax ok"
```
`-n` reads the script without running it. Expect `syntax ok`.

```bash
PSQL_CMD= ./scripts/capture_explain.sh
```
Expect the message `set PSQL_CMD to a command that runs SQL from stdin` and a non-zero exit (`echo $?` prints a number other than 0). This is the `${NAME:?}` check.

```bash
bash -x -c 'set -euo pipefail; false | true; echo reached' ; echo "exit=$?"
bash -c 'set -euo pipefail; false | true; echo reached' ; echo "exit=$?"
```
The first line, with `-x`, prints each command as it runs. Neither prints `reached`, and both end with a non-zero exit: because of `pipefail`, the failing `false` makes the whole pipeline fail, and `-e` stops the script.

```bash
make explain
```
Needs Docker (`make up` first). It rebuilds the database, loads 100,000 rentals and runs this script. Expect seven `wrote sql/explain/...` lines (q1 twice, then q2 to q6).

## Mistakes people make

- **Forgetting `set -euo pipefail`**, so the script keeps going after an error. Here the first thing the script does is turn them on.
- **Unquoted variables.** `cd $dir` breaks when the path contains a space. This script quotes every file name; the one deliberate exception is `$PSQL_CMD`, which must be split into words.
- **Depending on the caller's folder.** Line 7 moves to the repository root first.
- **Hiding a missing input.** The script refuses to start without `PSQL_CMD` rather than running an empty command.
- **Using `echo` for data that may start with a dash.** Here every string is a fixed literal, so there is no such risk.

## Check yourself

1. What does the first line of the script do, and why is `env` used? *It names the program that reads the file; `env` finds `bash` on `PATH`, so it works wherever Bash is installed.*
2. What does `set -euo pipefail` change? *It stops on a failing command (`-e`), on an unset variable (`-u`), and on a failing stage inside a pipeline (`pipefail`).*
3. Why is `$PSQL_CMD` not in double quotes on line 18? *Because the variable holds a whole command with spaces; unquoted, Bash splits it into the program and its arguments.*
4. What does `$(dirname "$0")/..` evaluate to? *The repository root, one folder above the folder that contains the script.*
5. What does `> /dev/null` do on line 25? *It discards the command's standard output, so only the side effect of reading the table remains.*

## Further reading

- GNU Bash Reference Manual (the script uses only features present in the Bash 3.2 that macOS ships and in Bash 5): https://www.gnu.org/software/bash/manual/bash.html
- `set` built-in: https://www.gnu.org/software/bash/manual/bash.html#The-Set-Builtin
