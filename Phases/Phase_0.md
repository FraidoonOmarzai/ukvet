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
│   └── agent/              # LangGraph agent + FastAPI
├── ui/                     # Streamlit
├── evals/
│   ├── datasets/
│   └── runners/
├── tests/
│   └── fixtures/           # recorded API responses
├── notebooks/
├── docs/
│   ├── adr/
│   ├── problem-statement.md
│   ├── data-notes.md
│   ├── legal-and-ethics.md
│   └── risks.md
├── .github/workflows/
├── docker-compose.yml
├── pyproject.toml
├── Makefile
├── .env.example
└── README.md
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