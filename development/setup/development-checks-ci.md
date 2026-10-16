# Development Checks and Why We Use Them

This project uses automated checks locally and in GitHub Actions to
catch problems before code is merged.

## 1. Install dependencies --- `uv sync --group dev`

Installs the project dependencies, including the development tools used
by the checks.

**Why:** Helps developers and CI use the dependencies declared by the
project.

## 2. Ruff linting --- `uv run ruff check .`

Finds common Python code issues, such as unused imports and other
problems covered by the configured lint rules. It can also identify some
bugs.

**Why:** Keeps the code clean and catches issues early. Use
`uv run ruff check --fix .` to automatically fix issues Ruff knows how
to fix.

## 3. Ruff formatting --- `uv run ruff format --check .`

Checks whether Python files match Ruff's formatting rules without
changing them.

**Why:** Keeps formatting consistent and makes code easier to read. If
it fails, run `uv run ruff format .`, review the changes, and commit
them.

## 4. Mypy type checking --- `uv run mypy`

Checks type annotations and detects possible type mismatches, such as
passing `None` where a plain `str` is expected.

**Why:** Finds potential bugs before runtime and makes function inputs
and outputs clearer. A Mypy error does not always mean the program will
fail at runtime, but it should be investigated.

## 5. Pytest --- `uv run pytest`

Runs the automated tests in the project.

**Why:** Checks that the code behaves as expected and helps prevent new
changes from breaking existing functionality.

## 6. Gitleaks secret scanning

GitHub Actions runs `gitleaks/gitleaks-action@v2` to scan the
repository's Git history for likely secrets, such as API keys or tokens.

**Why:** Helps prevent credentials from being committed to the
repository. If a real secret is exposed, revoke or rotate it; removing
it from the latest commit may not remove it from Git history.

## When do these checks run?

The workflow in `.github/workflows/ci.yml` runs on pushes to `main` and
on pull requests. It uses Ubuntu and Python 3.12. The checks are:

1.  Install development dependencies.
2.  Run Ruff linting and formatting checks.
3.  Run Mypy.
4.  Run Pytest.
5.  Run the Gitleaks secret scan in a separate job.

## Run the main checks locally

From the project root:

``` bash
uv sync --group dev
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
```

To apply Ruff's automatic formatting before checking:

``` bash
uv run ruff format .
uv run ruff check --fix .
```

Review the changes with `git diff` before committing. Passing these
local checks helps, but GitHub Actions is the final confirmation that
the committed code passes the configured CI workflow.
