<h1 align=center> ukvet — AI Due-Diligence Agent for UK Companies</h1>


### Project: UK Company Due-Diligence Agent (MCP)

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
