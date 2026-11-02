# YAML

## What it is

YAML is a plain-text format for writing structured data: named values, lists, and values that contain other named values. It is meant to be easy for people to read. Two files in this repository are YAML: the Compose file (`docker-compose.yml`) and the CI workflow (`.github/workflows/ci.yml`).

## Why this repository uses it

Both Docker Compose and GitHub Actions decided that their configuration is YAML. The repository has no choice; it only has to write it correctly.

## Where it appears

| File | What it uses YAML for |
|---|---|
| `docker-compose.yml` | The PostgreSQL service. See [docker-compose.md](docker-compose.md). |
| `.github/workflows/ci.yml` | The automatic checks. See [github-actions.md](github-actions.md). |

## How it works underneath

A YAML file is read into three kinds of value:

- A **mapping** is a set of `key: value` pairs, like a form with named fields.
- A **sequence** (list) is an ordered list of items, each item on a line starting with `- `.
- A **scalar** is a single value: text, a number, `true` or `false`.

**Indentation** shows nesting: a line indented under a key belongs to that key. Only spaces are allowed, never tabs, and all siblings must line up exactly. A `#` starts a comment. Text normally needs no quotes, but quotes are needed when the text could be mistaken for something else, such as `"3.12"` (otherwise it is the number 3.12, which is the same as 3.1 when written `3.10`) or `"5441:5432"` (a bare `22:22` is read by older YAML as a time-like number). A short list can be written in one line with brackets: `[push, pull_request]`. The sign `>-` after a key starts a **folded block**: the following indented lines are joined with single spaces into one string, and the `-` removes the final newline.

## Walkthrough of this repository's use

Every key of both files is explained in context, with the quoted lines, in [docker-compose.md](docker-compose.md) and [github-actions.md](github-actions.md). The YAML features used are:

- **Nested mappings**: `services:` contains `postgres:` which contains `image:`, `command:`, `ports:`, `environment:` and `healthcheck:`.
- **Sequences of scalars**: `ports:` has one item, `- "${POSTGRES_PORT:-5441}:5432"`.
- **Inline lists**: `command: ["postgres", "-c", "deadlock_timeout=100ms"]` and `on: [push, pull_request]`.
- **A folded block**: the `options: >-` of the CI service container.
- **Comments** with `#` on their own lines, used to explain the one non-default setting.

## Try it yourself

```bash
docker compose config
```
Compose parses the YAML and prints it back in normalized form. A syntax error is reported with a line number.

```bash
awk '/\t/ {print FILENAME": tab on line "NR}' docker-compose.yml .github/workflows/ci.yml; echo checked
```
Prints nothing but `checked`: neither file contains a tab character.

```bash
python3 -c "print(open('docker-compose.yml').read().count(chr(9)))"
```
Prints `0`: the Compose file contains no tab character (`chr(9)` is the tab).

## Mistakes people make

- **Tabs for indentation**: a parse error. `.editorconfig` sets two spaces for YAML.
- **Unquoted versions**: `python-version: 3.10` becomes `3.1`. The CI file quotes `"3.12"`.
- **Inconsistent indentation** that silently moves a key under the wrong parent.
- **Unquoted values with a colon and a space**, which start a new mapping.

## Check yourself

1. Which three kinds of value does YAML have? *Mappings, sequences, scalars.*
2. How is nesting written? *By indentation with spaces.*
3. Why is `"3.12"` quoted? *To keep it text; unquoted, a number could lose digits.*
4. What does `>-` do? *It folds the indented lines into one string without a trailing newline.*
5. How do you write a comment? *Start the text with `#`.*

## Further reading

- YAML 1.2.2 specification: https://yaml.org/spec/1.2.2/
