# uv

## What it is

uv is a fast Python package manager written in Rust. Among other things it can **resolve** a set of requirements (decide one compatible version of every package that satisfies all rules) and write the result as a lock file. This repository uses uv 0.11.2 only for that: `uv pip compile`.

## Why this repository uses it

The two lock files were produced by uv because it can write hashes for all platforms in one run. uv is **not** needed to run, test or build the project: `make install` uses plain pip and venv. It is a maintainer's tool.

## Where it appears

| File | Role |
|---|---|
| `requirements.lock` | Generated from `pyproject.toml`'s `dependencies`. |
| `requirements-dev.lock` | Generated from `dependencies` plus the `dev` extra. |

The first two comment lines of each file record the exact command used.

## How it works underneath

`uv pip compile` reads the requirements, asks the package index for every candidate version, picks a consistent set and prints it as `package==version`. With `--generate-hashes` it also downloads the file list of each release and writes one `--hash=sha256:...` line for each file. With `--universal` the result is valid for all operating systems and Python implementations, using environment markers (`; sys_platform == ...`) where packages differ.

## Walkthrough of this repository's use

The command recorded at the top of `requirements.lock` is:

```
uv pip compile pyproject.toml --universal --generate-hashes --python-version 3.12 -o requirements.lock
```

- `pyproject.toml` is the input, whose `dependencies` are the requirements (see [toml.md](toml.md)).
- `--universal` resolves for all platforms, `--generate-hashes` writes the fingerprints, `--python-version 3.12` resolves for the oldest supported Python (3.12), so the pins work on 3.12 and above.
- `-o requirements.lock` is the output file. For the development lock the same command adds `--extra dev`.

To refresh the pins, rerun the same command and review the diff before committing.

## Try it yourself

```bash
uv --version
```
Prints the installed version if uv is available. It is not required by the project.

```bash
sed -n 1,2p requirements.lock
```
Shows the recorded command.

```bash
uv pip compile pyproject.toml --universal --python-version 3.12 | head -5
```
Prints a fresh, hash-less resolution to the terminal without changing any file (needs uv and network access).

## Mistakes people make

- **Treating uv as a project requirement.** The Makefile and CI use pip.
- **Resolving for the wrong Python version**, producing pins that fail on the oldest supported one. The recorded command pins 3.12.
- **Updating pins without testing.** Run `make check` and `make audit` after.

## Check yourself

1. What does `--generate-hashes` add? *A sha256 fingerprint for every release file.*
2. What does `--universal` mean? *The result works for all platforms.*
3. Is uv needed to install the project? *No; pip does that.*
4. Where is the command recorded? *In the first lines of the lock file.*
5. Why resolve for Python 3.12? *It is the oldest supported version.*

## Further reading

- uv documentation (0.11): https://docs.astral.sh/uv/
- `uv pip compile`: https://docs.astral.sh/uv/pip/compile/
