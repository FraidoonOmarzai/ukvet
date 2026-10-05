# The full roadmap

| Phase | Name | Time |
|---|---|---|
| 0 | Problem definition & planning | 3–5 days |
| 1 | MCP server | Week 1 |
| 2 | Agent | Week 2 |
| 3 | Eval harness | Weeks 3–4 |
| 4 | Observability & guardrails | Week 4 |
| 5 | Model comparison | Week 5 |
| 6 | Launch & write-up | Week 5 |

This answer covers **Phase 0 completely**. Most people skip it, and it's the part a senior engineer or hiring manager will ask about: *"Why did you build it this way? How did you know it worked?"*

Treat AAII as your employer. You're the engineer; AAII leadership is the stakeholder you report to.


---
**In one sentence:** an AI agent that researches any UK company from official public data and produces a sourced risk report, built on an open-source MCP server that anyone can plug into their own AI tools.

**The problem it solves:** before hiring a supplier, signing a contract or investing, people check whether a company is legitimate. That means clicking through Companies House manually. Your agent does it in 30 seconds with every claim cited.

#### Step 1: Build the MCP server (week 1)

- Get a free Companies House API key.
- Wrap its endpoints as MCP tools: search_company, get_profile, get_officers, get_filing_history, get_psc (persons with significant control), get_charges, and get_insolvency.
- Handle rate limits (600 requests per 5 minutes), caching and errors properly.
- Publish it to PyPI and the MCP registries. People can now use your server in Claude Desktop or Cursor, which is where your real users come from.

#### Step 2: Build the agent (week 2)

The LangGraph flow has four nodes:

- Planner: decides what to check based on the question.
- Researcher: calls MCP tools.
- Verifier: cross-checks facts, such as whether a director is linked to dissolved companies.
- Reporter: writes the risk summary with a citation for every claim.

Wrap it in FastAPI with a simple Streamlit front end, containerised with Docker.

#### Step 3: Build the eval harness (weeks 3–4)

This is the most important and most skipped part.

- Write 200+ questions, such as "How many active directors does X have?", "Are X's accounts overdue?" or "Who controls X?"
- Verify every answer against the raw API. That's your ground truth.
- Measure factual accuracy, citation correctness, hallucination rate, and whether the agent correctly says "insufficient data" instead of guessing.
- Use rule-based checks where possible and LLM-as-judge only for report quality.
- Add a GitHub Actions job that runs the evals on every pull request and blocks the merge if scores drop.

#### Step 4: Observability and guardrails (week 4)

- Use Langfuse tracing for cost per report, latency, tool calls per query, and where failures happen.
- Add prompt injection defence. Company names and filing text are untrusted input, and someone could register a company called "Ignore previous instructions."
- Validate outputs with Pydantic schemas.

#### Step 5: Model comparison and launch (week 5)

- Run the same evals with a frontier API model versus an open model (you can reuse your vLLM setup from Project 1).
- Publish a table comparing accuracy, cost and latency. This shows engineering judgment, not just building.
- Write a Medium article and share the repo.

What you end up with: an open-source package with install counts, a working agent, a benchmark, CI eval gates, cost data, and a model comparison.

---

# Phase 0: Define, plan, set up

## Step 1: Write the problem statement

Answer five questions in writing before any code:

1. **Who has the problem?** UK small business owners, freelancers, procurement staff, and anyone about to pay or sign with a company they don't know.
2. **What's the pain?** Checking a company means clicking through Companies House pages, reading filings, and tracing directors across other companies. It takes 20–40 minutes, needs know-how, and people skip it.
3. **How do they solve it today?** Manually, or with paid tools like Endole or Creditsafe that cost money and are built for professionals.
4. **What does success look like?** A user enters a company name and gets a sourced risk summary in under 30 seconds.
5. **Why now, and why AI?** The data is public and structured, but interpreting it (red flags, linked companies) needs reasoning across multiple sources. That's what agents are good at.

Condense it into one paragraph, your **problem statement**:

> *UK SMEs and freelancers regularly engage suppliers and clients without checking their legitimacy, because manual Companies House research is slow and requires expertise. We will build an AI agent that produces a cited due-diligence report on any UK company in under 30 seconds, using only official public data, and an open-source MCP server so other AI tools can access the same data.*

## Step 2: Define users and their top questions

Pick **2–3 personas**:
- **Sarah, plumber:** "A new client wants 60-day payment terms. Are they legit?"
- **Procurement officer at a charity:** "Is this supplier financially stable?"
- **Freelance developer:** "Is this startup going to pay my invoice?"

Then list the **10 questions** they'd actually ask. These become your requirements and, later, your eval categories:
1. Is the company active or dissolved?
2. How old is it?
3. Who are the directors?
4. Are the accounts or confirmation statement overdue?
5. Who actually controls it (PSC)?
6. Are there charges (secured debts) against it?
7. Any insolvency history?
8. Have the directors run companies that were dissolved or went insolvent?
9. Has the registered address or leadership changed recently?
10. Overall: what are the red flags?

## Step 3: Set the scope (in and out)

Writing down what you won't do is what makes a project finishable.

**In scope (MVP):**
- UK companies registered at Companies House
- One company per report
- The 10 questions above
- Citations for every fact
- The MCP server, agent, eval harness, and a simple UI

**Out of scope, stated explicitly:**
- Credit scores or financial predictions
- Legal or financial advice (the report says so)
- Non-UK companies
- Paid data sources
- Sole traders, who aren't on Companies House
- User accounts or payments

**Later (v2):** Gazette notices, FCA register, and comparing two companies.

## Step 4: Define success metrics

Set these numbers now, before building, so you can't move the goalposts later.

| Type | Metric | Target |
|---|---|---|
| Quality | Factual accuracy on eval set | ≥ 90% |
| Quality | Hallucinated facts | < 2% |
| Quality | Correct "insufficient data" responses | ≥ 90% |
| Quality | Claims with a valid citation | 100% |
| Performance | p95 report time | < 30s |
| Cost | Cost per report | < £0.05 |
| Engineering | Test coverage | ≥ 80% |
| Adoption | PyPI downloads / GitHub stars | Track, no target |

If you miss a target, report the miss honestly. That still reads well in an interview.

## Step 5: Feasibility spike on the data (1–2 days)

Prove the data supports your 10 questions **before** designing anything.

1. Register at the Companies House developer hub and create a free REST API key.
2. Test these endpoints in a Jupyter notebook:
   - `/search/companies?q=`
   - `/company/{number}`
   - `/company/{number}/officers`
   - `/company/{number}/filing-history`
   - `/company/{number}/persons-with-significant-control`
   - `/company/{number}/charges`
   - `/company/{number}/insolvency`
   - `/officers/{officer_id}/appointments` (needed for question 8)
3. Pull data for about 10 varied companies: a large plc, a tiny new Ltd, a dissolved one, one with insolvency, and one with overdue accounts.
4. Write a **data notes** document covering which fields answer which question, what's missing, response formats, and quirks.
5. Note the constraints: authentication is HTTP Basic with the key as the username; the rate limit is **600 requests per 5 minutes**; and some endpoints return 404 when there's no data (for example, no charges). A 404 there is a valid answer, not an error. That matters for your agent.

**Output:** `notebooks/00_api_exploration.ipynb` plus `docs/data-notes.md`.

## Step 6: Legal and ethical check

Doing this step unprompted is rare, and interviewers notice it.

- Companies House data is published under the **Open Government Licence**, so reuse is allowed with attribution.
- Director names and details are **personal data** under UK GDPR. Don't build a database of people. Cache briefly, store nothing long-term, and don't let it become a people-profiling tool.
- Add a **disclaimer**: "Informational only; not legal or financial advice."
- Treat company names and filing text as **untrusted input**, since anyone can register a company name. Plan the prompt injection defence now; you'll build it in Phase 4.

**Output:** `docs/legal-and-ethics.md`.

## Step 7: Risk register

List what could go wrong and your plan for each:

| Risk | Impact | Mitigation |
|---|---|---|
| API rate limits hit during evals | Evals fail | Cache responses; record fixtures for tests |
| LLM invents facts | Wrong reports | Verifier node, citation checks, evals |
| API changes or downtime | Agent breaks | Error handling, retries, clear messages |
| LLM costs grow | Budget | Track cost per report; use a cheaper model where it's good enough |
| Scope creep | Never finish | Out-of-scope list; v2 backlog |
| Eval set too small or biased | False confidence | Mix company types; include adversarial cases |

**Output:** `docs/risks.md`.

## Step 8: Architecture decisions

Draw a simple diagram:

```
User → Streamlit UI → FastAPI → LangGraph agent
                                   ├─ Planner
                                   ├─ Researcher ──→ MCP client ──→ Your MCP server ──→ Companies House API
                                   ├─ Verifier                           └─ Cache
                                   └─ Reporter
                     Langfuse (tracing) watches the agent
```

Then write short **Architecture Decision Records (ADRs)**: one page each, covering the context, the decision, alternatives, and the reason.
- **ADR-001:** Use MCP instead of direct function tools, because it's reusable by other AI apps and is an industry standard.
- **ADR-002:** Use LangGraph for orchestration, because it gives explicit state and control flow and you already know it.
- **ADR-003:** Choose the initial LLM. Start with one API model; the open model comes in Phase 5.
- **ADR-004:** Choose the caching strategy (in-memory or SQLite with a TTL).
- **ADR-005:** Use the official Python `mcp` SDK (FastMCP) for the server.

**Output:** `docs/architecture.md` and `docs/adr/`.

## Step 9: Set up the repo and tooling

```
uk-company-agent/
├── packages/
│   ├── ch_mcp_server/      # MCP server (published to PyPI)
│   └── agent/              # LangGraph agent + FastAPI (AI Agent)
├── ui/                     # Streamlit
├── evals/
│   ├── datasets/
│   └── runners/
├── tests/
│   └── fixtures/           # recorded API responses
├── notebooks/              # API exploration
├── docs/                   # documentation (official project documentation)
│   ├── adr/
│   ├── problem-statement.md
│   ├── data-notes.md
│   ├── legal-and-ethics.md
│   └── risks.md
├── development/                   # development record
│   ├── README.md
│   ├── phases/
|   | ├── phase-00-define.md
|   | └── ...
│   ├── setup/
|   | ├── uv.md
|   | └── ...
│   └── journals/
├── .github/workflows/
├── docker-compose.yml
├── pyproject.toml         # main configuration
├── Makefile
├── .env.example
└── README.md
```

```
uv.lock      ← exact dependency versions
data/        ← local/raw data (git-ignored)
```

**Tooling:**
- `uv` for dependencies
- `ruff` for linting and formatting
- `mypy` for types
- `pytest` for tests
- `pre-commit` hooks
- A basic GitHub Actions CI (lint, type check, tests) **from day one**
- Secrets in `.env`, never committed, with `.env.example` documenting them
- **Branch strategy:** `main` is protected; work on feature branches and merge through pull requests, even solo. Your PR history becomes evidence of how you work.

## Step 10: Create the plan and backlog

1. Create a **GitHub Project board** with columns Backlog → To do → In progress → Review → Done.
2. Turn each phase into a **milestone** (Phase 1 to Phase 6).
3. Break each milestone into **issues** of half a day to one day each. For example, Phase 1 includes:
   - Implement API client with auth and retries
   - Add rate limiter
   - Add caching layer
   - Implement `search_company` tool
   - Implement `get_officers` tool
   - …
   - Record test fixtures
   - Publish to TestPyPI
4. Write a **Definition of Done** that applies to every issue: code merged via PR, tests pass, CI green, docs updated.

## Step 11: Kick off at AAII

Run this as a real workplace process:
- Send a **one-page project brief** to AAII leadership: the problem, scope, metrics, timeline, and risks.
- Agree on a **weekly demo** where you show working software every Friday, even if it's small.
- Keep a **decision log** of what you changed and why. You'll draw on it for interview stories and the Medium article.
- Write a short **weekly update**: done, next, blockers.

---
## Phase 0: Define, plan, set up
1. **The problem statement:** background, the problem, who's affected, current alternatives and their gaps, why an agent, the final problem statement, 5 assumptions to validate, and a sign-off table for AAII.
2. **Users and questions:** 3 personas plus developers as a secondary user, and the 10 core questions (Q1–Q10) with why each matters, likely data source and answer type. It also sets the answer rules (citations, "insufficient data") and gives a 15-minute user interview script.
3. **Scope:** in scope, out of scope with reasons, a v2 backlog, constraints, and the MVP definition of done.
4. **Success metrics:** 16 metrics, each with a precise definition and target, when it's measured, and the reporting rules.
5. **The API spike:** `notebooks/00_api_exploration.ipynb` is a complete notebook. It tests auth, builds a varied test set automatically, calls every endpoint, records "no data" behaviour, answers Q1–Q9 from the raw data, measures the director network cost for Q8, and calculates calls per report, latency and reports per 5 minutes. `docs/05-data-notes.md` is the template you fill in from the results.
6. **Step 6:** `06-legal-and-ethics.md` covers OGL attribution, the UK GDPR rules, the report disclaimer, and misuse controls.
7. **Step 7:** `07-risks.md` has 13 risks, each with likelihood, impact, mitigation and a trigger to act.
8. **Step 8:** `08-architecture.md` has a Mermaid diagram (GitHub renders it), component responsibilities, draft `Fact`/`Report` schemas and the request flow, plus 5 ADRs and a template in `adr/`.
9. **Step 9:** a uv workspace with two packages (`ukvet-mcp`, `ukvet-agent`), ruff, strict mypy, pytest with an 80% coverage gate, pre-commit hooks, a Makefile, and CI running on Python 3.11 and 3.12 with a Gitleaks secrets scan. It also has an MIT licence, `.gitignore` and `.env.example`.
10. **Step 10:** `09-plan.md` covers milestones, the Definition of Done, git workflow and weekly rhythm. `scripts/create_backlog.sh` creates **51 GitHub issues** with milestones and labels in one command.
11. **Step 11:** `kickoff/` holds the one-page project brief for AAII, a weekly update template, and a decision log already filled with your 5 decisions so far.
---

# Phase 0 checklist

- [ ] Problem statement written
- [ ] 2–3 personas and 10 user questions
- [ ] In/out/later scope list
- [ ] Success metrics with targets
- [ ] API key obtained; exploration notebook done
- [ ] `data-notes.md`
- [ ] `legal-and-ethics.md`
- [ ] `risks.md`
- [ ] Architecture diagram and 5 ADRs
- [ ] Repo created with structure, tooling, and CI
- [ ] GitHub board with milestones and issues
- [ ] Project brief sent to AAII; weekly demo agreed

**Honest note:** Phase 0 will feel slow because you'll want to start coding. Don't. Keep it to 5 days maximum. The goal is a clear plan, not perfect documents. The API spike in Step 5 is the one step you must not skip, because it's the step most likely to change your plan.