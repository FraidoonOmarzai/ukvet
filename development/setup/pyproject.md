This is the **root `pyproject.toml`** for your whole `ukvet` project. It is basically the project's **main configuration file**: it tells `uv`, Python tooling, tests, linting, and type checking how the project is organised.

The easiest way to understand it is:

```text
ukvet-workspace/
│
├── pyproject.toml        ← main configuration
├── uv.lock               ← exact dependency versions
│
├── packages/
│   ├── ukvet-mcp/        ← MCP server
│   └── ukvet-agent/      ← AI agent
│
├── tests/                ← tests
├── notebooks/            ← API exploration
├── docs/                 ← documentation
└── data/                 ← local/raw data (git-ignored)
```

## 1. `[project]`

```toml
[project]
name = "ukvet-workspace"
version = "0.0.0"
description = "ukvet — AI Due-Diligence Agent for UK Companies (workspace root)"
requires-python = ">=3.11"
dependencies = [
    "ukvet-mcp",
    "ukvet-agent",
]
```

This describes the **main project**.

### `name`

```toml
name = "ukvet-workspace"
```

The name of the overall workspace.

You have two actual packages inside it:

```text
ukvet-mcp
ukvet-agent
```

The workspace itself is called `ukvet-workspace`.

### `version`

```toml
version = "0.0.0"
```

The current version of the workspace.

Since you're still developing, `0.0.0` is fine.

### `description`

Just explains what the project is.

### `requires-python`

```toml
requires-python = ">=3.11"
```

Means:

> This project requires Python 3.11 or newer.

This prevents someone from trying to run it with an unsupported Python version.

### `dependencies`

```toml
dependencies = [
    "ukvet-mcp",
    "ukvet-agent",
]
```

These are the two packages that make up your application.

Conceptually:

```text
ukvet-workspace
       │
       ├── ukvet-mcp
       │
       └── ukvet-agent
```

---

# 2. Development dependencies

```toml
[dependency-groups]
dev = [
    "pytest>=8",
    "pytest-cov>=5",
    "ruff>=0.6",
    "mypy>=1.11",
    "pre-commit>=3.8",
]
```

These aren't needed to **run the application**.

They're tools you use while **developing** it.

### pytest

Runs your tests.

```text
code → pytest → pass/fail
```

### pytest-cov

Measures how much of your code is covered by tests.

### ruff

Checks your Python code for problems and style issues.

### mypy

Checks your Python **types**.

### pre-commit

Automatically runs checks before you commit code.

For example:

```text
git commit
    ↓
pre-commit
    ↓
ruff
mypy
tests/checks
    ↓
commit allowed
```

This helps prevent bad code entering your repository.

---

# 3. Notebook dependencies

```toml
notebook = [
    "jupyterlab>=4",
    "httpx>=0.27",
    "pandas>=2.2",
    "python-dotenv>=1.0",
]
```

These are specifically for your **notebooks**.

You used these during your Companies House API spike.

- `jupyterlab` → notebook environment
- `httpx` → API requests
- `pandas` → tables/data analysis
- `python-dotenv` → load your `.env` API key

The important idea is that these don't have to become dependencies of your production agent.

---

# 4. `[tool.uv]`

```toml
[tool.uv]
package = false
```

This tells `uv`:

> The root workspace is not itself a Python package.

That's because the real packages are:

```text
packages/ukvet-mcp
packages/ukvet-agent
```

The root is mainly a **workspace/container**.

---

# 5. The workspace

```toml
[tool.uv.workspace]
members = ["packages/*"]
```

This is one of the most important parts.

It tells `uv`:

> Every package inside `packages/` belongs to this workspace.

So:

```text
packages/
├── ukvet-mcp/
└── ukvet-agent/
```

are automatically recognised as workspace members.

This lets you develop both packages together.

---

# 6. Workspace dependencies

```toml
[tool.uv.sources]
ukvet-mcp = { workspace = true }
ukvet-agent = { workspace = true }
```

This tells `uv`:

> When I say `ukvet-mcp` or `ukvet-agent`, use the local packages in this workspace.

Instead of downloading them from PyPI.

So:

```text
ukvet-agent
     │
     └── uses local ukvet-mcp
```

This is very useful while you're developing because changes to the MCP package are immediately available to the agent.

---

# 7. Ruff configuration

```toml
[tool.ruff]
line-length = 100
target-version = "py311"
extend-exclude = ["notebooks"]
```

This configures **Ruff**, your code-quality checker.

### Line length

```toml
line-length = 100
```

You allow lines up to 100 characters.

### Python version

```toml
target-version = "py311"
```

Ruff knows you're writing Python 3.11 code.

### Exclude notebooks

```toml
extend-exclude = ["notebooks"]
```

Your exploratory notebooks aren't checked by Ruff.

That's sensible because notebooks are usually more experimental than production code.

---

# 8. Ruff rules

```toml
[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "SIM", "S"]
ignore = ["S101"]
```

This says which kinds of problems Ruff should look for.

You don't need to memorise all the codes.

Broadly:

```text
E   → style/errors
F   → bugs / undefined things
I   → import organisation
B   → common bugs
UP  → modern Python
SIM → simplify code
S   → security checks
```

You specifically ignore:

```toml
S101
```

because that flags `assert`.

You want to allow assertions in tests.

---

# 9. Mypy

```toml
[tool.mypy]
python_version = "3.11"
strict = true
packages = ["ukvet_mcp", "ukvet_agent"]
```

This configures **mypy**, which checks your type hints.

For example:

```python
def search(company: str) -> list[dict]:
```

Mypy checks whether you're using that function consistently.

### `strict = true`

Means:

> Be quite strict about type correctness.

This is good for a project where you want reliable, maintainable code.

### Packages

```toml
packages = ["ukvet_mcp", "ukvet_agent"]
```

Mypy checks your two actual packages.

---

# 10. Pytest

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "--cov=ukvet_mcp --cov=ukvet_agent --cov-report=term-missing"
```

This configures your tests.

### Where are tests?

```toml
testpaths = ["tests"]
```

Pytest looks in:

```text
tests/
```

### Coverage

Every time you run:

```bash
uv run pytest
```

pytest also measures coverage for:

```text
ukvet_mcp
ukvet_agent
```

and shows which lines aren't covered.

---

# 11. 80% coverage requirement

```toml
[tool.coverage.report]
fail_under = 80
```

This means:

> Your test suite must achieve at least 80% coverage.

If coverage is below 80%, the test command fails.

So you are setting a quality gate:

```text
pytest
  ↓
tests pass?
  ↓
coverage ≥ 80%?
  ↓
YES → good
NO  → fail
```

---

# How you actually create this

You don't need to type all of this manually from scratch.

With `uv`, you start the workspace:

```bash
uv init --bare
```

Then create your packages:

```bash
mkdir -p packages/ukvet-mcp
mkdir -p packages/ukvet-agent
```

Each package gets its own `pyproject.toml`.

For example:

```text
ukvet-workspace/
├── pyproject.toml
│
└── packages/
    ├── ukvet-mcp/
    │   └── pyproject.toml
    │
    └── ukvet-agent/
        └── pyproject.toml
```

Then your **root `pyproject.toml`** contains the workspace configuration you showed.

Finally:

```bash
uv sync
```

`uv` reads the configuration, finds the two workspace packages, installs their dependencies, and creates/updates:

```text
.venv/
uv.lock
```

---

## The big picture

Think of the whole file as answering different questions:

```text
[project]
     ↓
"What is this project and what does it depend on?"

[dependency-groups]
     ↓
"What tools do I need for development/notebooks?"

[tool.uv.workspace]
     ↓
"Which packages belong to my project?"

[tool.uv.sources]
     ↓
"Where do those packages come from?"

[tool.ruff]
     ↓
"How should my code be checked?"

[tool.mypy]
     ↓
"How should types be checked?"

[tool.pytest]
     ↓
"How should tests run?"

[tool.coverage]
     ↓
"How much code must tests cover?"
```

So **`pyproject.toml` is basically the control centre for your Python project**. It brings your MCP server, agent, dependencies, tests and code-quality rules together in one place.


```
uv add python-dotenv

uv remove pytest
uv add --dev pytest

uv add --group notebook jupyter numpy pandas
```