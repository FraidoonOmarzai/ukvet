# Development

This directory records the development process behind **ukvet** — an AI due-diligence agent for UK companies.

It documents the decisions, experiments, setup, problems, lessons learned, and progress through each development phase.

The purpose is to provide a clear engineering record of **how the project was built and why key decisions were made**.

---

## Structure

```text
development/
│
├── README.md
│
├── setup/
│   ├── uv.md
│   ├── pyproject.md
│   ├── makefile.md
│   ├── pre-commit.md
│   └── git-workflow.md
│
├── phases/
│   ├── phase-01-foundation.md
│   ├── phase-02-api-spike.md
│   ├── phase-03-mcp.md
│   ├── phase-04-agent.md
│   └── phase-05-evaluation.md
│
└── journal/
    └── YYYY-MM-DD.md
```

---

## 1. Setup

The `setup/` directory explains how the development environment was created and configured.

| File | Purpose |
|---|---|
| `uv.md` | Python and dependency management with uv |
| `pyproject.md` | Project configuration and dependencies |
| `makefile.md` | Development commands and automation |
| `pre-commit.md` | Git hooks and automated checks |
| `git-workflow.md` | Branches, commits and pull requests |

These files explain **how the project is developed and maintained**.

---

## 2. Development phases

The `phases/` directory records the major stages of the project.

Each phase should describe:

- Goal
- Planned work
- Work completed
- Experiments performed
- Problems encountered
- Decisions made
- Results
- Lessons learned
- Remaining work

### Phase 1 — Foundation

Set up the repository, Python environment, workspace structure, development tools and quality checks.

### Phase 2 — Companies House API Spike

Test the Companies House API before building the MCP server.

This includes:

- Authentication
- Endpoint behaviour
- Q1–Q10 data mapping
- Test-company selection
- Rate limits
- API latency
- Q8 director-network cost
- Caching and fixtures
- API edge cases

### Phase 3 — MCP Server

Build the Companies House MCP server using the official Python MCP SDK and FastMCP.

### Phase 4 — Agent

Build the LangGraph agent that uses the MCP server to answer due-diligence questions and produce reports.

### Phase 5 — Evaluation and Model Comparison

Evaluate accuracy, hallucination, latency and cost, and compare the initial API model with an open-weight model.

---

## 3. Development journal

The `journal/` directory is for significant development events that do not belong in a formal phase document.

Examples:

- A technical problem and how it was solved
- A change to the project structure
- A failed approach
- An important discovery
- A change in an architectural decision
- A useful lesson learned

The journal should record **meaningful development events**, not every command that was executed.

---

## 4. Documentation principles

Development notes should answer four questions:

1. **What did I do?**
2. **Why did I do it?**
3. **What happened?**
4. **What did I learn or decide as a result?**

Where possible, link development notes to the relevant:

- Architecture Decision Record (ADR)
- Notebook
- Test
- API finding
- Git commit or pull request

---

## 5. Relationship to other project directories

Development documentation is separate from the project's formal documentation.

```text
development/
    How the project was built
    ↓
docs/
    Final project documentation
    ↓
notebooks/
    Experiments and evidence
    ↓
packages/
    Production code
    ↓
tests/
    Automated verification
```

The development directory records the **journey**.

The `docs/` directory records the **resulting system and decisions**.

The notebooks contain the **experimental evidence**.

---

## 6. Updating this directory

Update the relevant development file when a significant milestone is completed.

At the end of each phase, record:

- What was completed
- What was not completed
- Important findings
- Decisions made
- Risks reduced or discovered
- Open questions
- Next steps

This keeps the development history useful without turning it into a complete activity log.