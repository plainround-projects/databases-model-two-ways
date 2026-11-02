# EditorConfig and Git ignore files

## What it is

`.editorconfig` is a text file that tells code editors how to format files: what character set, which line endings, whether to use tabs or spaces. Most editors read it with no setup or with a small plug-in. `.gitignore` is a text file that tells Git which files never to track. Both are lists of patterns, not programs.

## Why this repository uses it

A consistent file style (the same indent, no stray spaces) keeps changes small and avoids bugs in files where whitespace matters (YAML and Makefiles). `.gitignore` keeps the virtual environment, caches, logs and the local `.env` out of the history.

## Where it appears

| File | Role |
|---|---|
| `.editorconfig` | Formatting rules for every file type. |
| `.gitignore` | Local files that must not be committed. |

## How it works underneath

An editor looks for `.editorconfig` in the file's folder and upward, until a file says `root = true`. The file has **sections** in `[brackets]` that hold a pattern, and settings in the lines below apply to files matching the pattern. Later sections override earlier ones. Git compares each untracked file with the patterns in `.gitignore`: a match hides it from `git status` and `git add`. A trailing `/` matches a folder, `*` matches any run of characters.

## Walkthrough of this repository's use

```text
root = true

[*]
charset = utf-8
end_of_line = lf
insert_final_newline = true
trim_trailing_whitespace = true
indent_style = space
indent_size = 4

[*.{yml,yaml,json,toml}]
indent_size = 2

[Makefile]
indent_style = tab

[*.md]
trim_trailing_whitespace = false
```

- `root = true`: stop searching in the parent folders.
- `[*]` applies to every file: `charset = utf-8` (the text encoding), `end_of_line = lf` (Unix line endings, not Windows `\r\n`), `insert_final_newline = true` (every file ends with a newline), `trim_trailing_whitespace = true` (remove spaces at line ends), `indent_style = space` and `indent_size = 4` (indent by four spaces).
- `[*.{yml,yaml,json,toml}]` overrides the indent to 2 for those formats.
- `[Makefile]` sets `indent_style = tab`, because Make requires a tab character at the start of a recipe line (see [make.md](make.md)).
- `[*.md]` turns trimming off: in Markdown two trailing spaces mean a line break.

```text
.venv/
__pycache__/
*.pyc
*.egg-info/
build/
dist/
.pytest_cache/
.mypy_cache/
.ruff_cache/
.import_linter_cache/
.coverage
.env
.DS_Store
logs/
.omc/
```

- `.venv/` is the virtual environment; `__pycache__/`, `*.pyc` and `*.egg-info/` are files Python and packaging create; `build/` and `dist/` are packaging output.
- `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`, `.import_linter_cache/` and `.coverage` are tool caches and the coverage data.
- `.env` is the local settings file with the password (see [dotenv.md](dotenv.md)).
- `.DS_Store` is a folder-view file macOS creates. `logs/` and `.omc/` are local run folders.

## Try it yourself

```bash
git status --short --ignored | head
```
Lines starting with `!!` are ignored files such as `.venv/`.

```bash
git check-ignore -v .venv/bin/python
```
Prints the `.gitignore` line (and its number) that matches.

```bash
grep -n 'indent_style' .editorconfig
```
Shows the three indent rules: space, then tab for Makefile.

## Mistakes people make

- **Tabs in YAML or spaces in Makefiles**: both break. The rules above prevent it.
- **Committing a secret before ignoring it.** Adding a name to `.gitignore` later does not remove it from history.
- **Windows line endings** in shell scripts, which breaks the shebang. `end_of_line = lf` prevents it.

## Check yourself

1. What does `root = true` do? *Stops the search for more `.editorconfig` files.*
2. Why does `[Makefile]` use tabs? *Make recipes require a tab.*
3. Why do Markdown files keep trailing spaces? *Two spaces are a line break.*
4. What does a trailing `/` in `.gitignore` mean? *The pattern matches folders.*
5. Does `.gitignore` remove already tracked files? *No; it affects untracked files only.*

## Further reading

- EditorConfig specification: https://spec.editorconfig.org/
- gitignore patterns: https://git-scm.com/docs/gitignore
