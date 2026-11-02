# GitHub Actions

## What it is

GitHub Actions is a service that runs commands on a fresh, temporary computer each time something happens in a GitHub repository, such as a push. A **workflow** is a YAML file under `.github/workflows/` that says when to run and what to do. A workflow contains **jobs**; a job runs on one machine (a **runner**) and holds a list of **steps**. This is **continuous integration** (CI): the automatic check that a change still builds and passes its tests.

## Why this repository uses it

So that anyone who copies the repository sees the same results as the author, on a clean machine. The workflow runs everything that needs no services in one job and everything that needs PostgreSQL in another.

## Where it appears

| File | What it does |
|---|---|
| `.github/workflows/ci.yml` | The two jobs, `check` and `integration`. |

## How it works underneath

GitHub watches for the events named under `on:`. When one happens, it starts a virtual machine of the kind named in `runs-on:`, runs each step in order and stops at the first failure. Each step is either `run:` (a shell command) or `uses:` (a ready-made action, a small reusable program published as `owner/name@version`). Jobs run in parallel on separate machines unless told otherwise. A **service container** is a Docker container that GitHub starts beside the job, and waits for until its health check passes. **Environment variables** set with `env:` are visible to all commands in their scope.

## Walkthrough of this repository's use

```yaml
name: ci

on: [push, pull_request]

```

- `name: ci` is the workflow's label in the GitHub web page.
- `on: [push, pull_request]` is an inline list of events: a push to any branch, and any change to a pull request (a proposal to merge a branch).

```yaml
jobs:
  check:
    name: Format, lint, types, import rules, unit tests with coverage, dependency audit
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: make check
      - run: make audit

```

- `jobs:` holds the jobs by id; the first is `check`. Its `name:` is the human-readable title.
- `runs-on: ubuntu-latest` picks a Linux virtual machine.
- `steps:` is the list. `uses: actions/checkout@v4` copies the repository's files onto the machine. `actions/setup-python@v5` installs Python; its `with:` block passes the input `python-version: "3.12"` (quoted, see [yaml.md](yaml.md)).
- `run: make check` runs lint and unit tests with coverage; `run: make audit` checks the locked packages for known vulnerabilities. Make creates the virtual environment on first use, see [make.md](make.md).

```yaml
  integration:
    name: Integration and end-to-end tests (PostgreSQL 18 service container)
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:18
        ports:
          - 5441:5432
        env:
          POSTGRES_USER: shop
          POSTGRES_PASSWORD: ci-only-throwaway
          POSTGRES_DB: rentals
        options: >-
          --health-cmd "pg_isready -U shop -d rentals"
          --health-interval 3s
          --health-timeout 5s
          --health-retries 20
```

The second job is `integration`, with its own machine. `services:` starts a container named `postgres` from `postgres:18`. `ports: - 5441:5432` publishes the database on the machine's port 5441, the port the tests expect. `env:` under the service gives the user, a throwaway password and the database name. `options: >-` is a folded block (see [yaml.md](yaml.md)) of extra `docker create` flags: `--health-cmd` is the check command (`pg_isready` asks whether the server is accepting connections), and the other three set the interval, timeout and retry count. GitHub does not start the steps until the check passes.

```yaml
    env:
      POSTGRES_PASSWORD: ci-only-throwaway
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: make test-integration test-e2e
```

The job-level `env:` sets `POSTGRES_PASSWORD` for every step, so the Python programs find the password the service was created with. After checkout and Python setup, `make test-integration test-e2e` runs both suites: Make runs the two targets one after the other.

The password `ci-only-throwaway` protects a database that exists only for the minutes the job runs and is never reachable from outside; it is not a secret.

## Try it yourself

```bash
make -n check audit test-integration test-e2e | head -20
```
Shows the commands the workflow will run, without running them.

```bash
python3 -c "print(open('.github/workflows/ci.yml').read().count('uses:'))"
```
Prints `4`: two checkouts and two Python setups.

```bash
git ls-files .github
```
Shows the workflow is committed; without the file in the repository nothing runs.

## Mistakes people make

- **Unquoted Python versions** such as `3.10` that become `3.1`; here `"3.12"` is quoted.
- **Floating action versions** such as `@main`. Here the actions are pinned to a major version.
- **Real secrets in the workflow file.** Only a throwaway is written here.
- **Not waiting for the service.** The health options make GitHub wait until PostgreSQL answers.

## Check yourself

1. What is a job and what is a step? *A job runs on one machine; steps are its commands in order.*
2. Which events trigger this workflow? *A push and a pull request.*
3. Why does the `integration` job have `services:`? *The integration and end-to-end tests need a real PostgreSQL.*
4. What does `>-` mean in `options:`? *A folded block that joins lines into one string.*
5. Why is the Python version quoted? *So YAML keeps it as text.*

## Further reading

- Workflow syntax: https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax
- Service containers: https://docs.github.com/en/actions/use-cases-and-examples/using-containerized-services/about-service-containers
