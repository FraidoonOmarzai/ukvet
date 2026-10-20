# Phase 2 roadmap: `ukvet-agent`

**Goal:** a company name or number goes in, and a validated, cited report comes out, through an API and a UI, running with one `docker compose up`.

**Exit criteria:**
- Q1-Q9 answered for any active UK company.
- Every claim cites a fact that exists.
- Runs in Docker.
- Tests pass with no network and no real LLM.

**Time:** about 8-10 working days, which is more than the "week 3" in the plan.

---

## Before you start

- [ ] Phase 1 is really finished: `--check` passes, real fixtures are recorded, and the Claude Desktop test is done. Phase 2 builds on those fixtures and on the tool descriptions you tuned.
- [ ] **Prototype the Reporter in a notebook first (day 1-2).** It's the only unmeasured, highest-risk part. Feed it real tool output for 2-3 companies and look at the latency, the output quality, and whether it follows a citation format. If this fails, the whole design needs to change, so find out before building the rest.
- [ ] Decide **ADR-007** (deterministic Researcher) and **ADR-008** (stdio between agent and server) after that prototype. Pick the LLM (**ADR-003**) and record the exact model ID.

---

## Steps

| Step | What | Time |
|---|---|---|
| 2.1 | Dependencies and layout | ½ day |
| 2.2 | Schemas and fact IDs | ½ day |
| 2.3 | LLM abstraction and a fake model | ½ day |
| 2.4 | MCP client integration | 1 day |
| 2.5 | Fact builders (tool results to `Fact`s) | 1 day |
| 2.6 | Researcher node | 1 day |
| 2.7 | Planner node | ½ day |
| 2.8 | Verifier node | 1 day |
| 2.9 | Red-flag rules, Reporter and citation checker | 2 days |
| 2.10 | LangGraph assembly | ½ day |
| 2.11 | FastAPI service | 1 day |
| 2.12 | Streamlit UI | ½ day |
| 2.13 | Docker | ½ day |
| 2.14 | Measure and tune | ½ day |
| 2.15 | Close the phase | ½ day |

### 2.1 Dependencies and layout
- Add `langgraph`, the chat-model package for your chosen provider, `fastapi` and `uvicorn` to `ukvet-agent`, and `streamlit` to the UI.
- Modules: `schemas.py`, `state.py`, `llm.py`, `mcp_client.py`, `facts.py`, `nodes/` (planner, researcher, verifier, reporter), `redflags.py`, `citations.py`, `graph.py`, `api.py`, and a `prompts/` folder.

### 2.2 Schemas and fact IDs
- `Fact`, `Claim{text, fact_ids}`, `RedFlag`, `Report` and `AgentState`, as in `08-architecture.md` and `10-system-design.md`.
- Use **stable, readable fact IDs** (for example `Q4.accounts_overdue`), so the citation check can be deterministic and eval failures are traceable.

### 2.3 LLM abstraction and a fake model
- One chat-model interface selected by environment variables, with structured output.
- A **fake model** for tests that returns canned responses. CI must never call a real LLM, because that would cost money and give flaky results.
- A separate, opt-in `live` pytest marker for real-LLM smoke tests that you run by hand.

### 2.4 MCP client integration
- Start `ukvet-mcp` as a stdio subprocess and keep one session for the API's lifetime.
- Call tools and parse `structured_content` into typed results.
- Add timeouts and a health check for a dead subprocess.
- Test against the in-memory server with your fixtures.

### 2.5 Fact builders
- Pure functions that turn each tool result into tagged `Fact`s for Q1-Q9, with value, source URL and `retrieved_at`.
- A `found=false` result becomes a fact like "no charges registered", not a gap.
- Missing or failed data becomes an explicit **gap**.
- This is the foundation of every citation, so test it heavily with parametrised cases.

### 2.6 Researcher
- Plain code, no LLM. Fan out profile, officers, PSC, charges, insolvency and filings in parallel with `asyncio.gather`.
- Then fetch Q8 appointments for current directors, capped at 5 to start.
- One failed call becomes a gap and never a crash.

### 2.7 Planner
- A number goes straight through. A name triggers search, and an ambiguous name returns candidates for the user to choose.
- Decide whether free-text questions ("who controls X?") are in the MVP. I'd defer them and ship the full report first.

### 2.8 Verifier
- Deterministic checks only:
  - every planned question has a fact or a gap;
  - profile flags agree with the detail endpoints (`has_charges` against the charges list);
  - dissolved or insolvent status agrees with the insolvency record.
- Gaps trigger one targeted re-fetch, with at most 2 loops.

### 2.9 Red-flag rules, Reporter, citation checker
- **Red flags come from rules, not the LLM.** Examples: overdue accounts, a very young company, an outstanding charge, directors linked to dissolved companies. Each rule produces a flag that cites its facts.
  - **Trade-off:** it's less flexible, but red-flag recall (M5) becomes measurable and the LLM can't invent a flag.
- **Reporter:** a single structured-output call that phrases the findings and assessment from verified facts only. Registry text goes in delimited data blocks and is treated as untrusted.
- **Citation checker:** rejects unknown `fact_ids`, checks that dates, counts and statuses in a claim match the cited fact, and strips uncited claims.
- Retry once on a schema or citation failure, then return the report with the failing claims removed and `missing_data` noted.
- Enforce "no statements implying wrongdoing by an individual".

### 2.10 LangGraph assembly
- Wire Planner → Researcher → Verifier → Reporter, with the capped loop and the ambiguous-name exit.
- End-to-end tests with the fake LLM and fixtures covering: a normal company, dissolved, insolvent, a missing endpoint, an ambiguous name, an unknown company, and invalid LLM output.

### 2.11 FastAPI service
- `POST /v1/reports` and `GET /health`, with the status codes from the design doc.
- Manage the MCP session in the app lifespan, and enforce a hard 45 s deadline.
- Test with the fake LLM.

### 2.12 Streamlit UI
- Input box, candidate picker, report with clickable citations, freshness timestamp, disclaimer and OGL attribution.

### 2.13 Docker
- Multi-stage image, `docker-compose.yml` with `api` and `ui`, and a volume for the cache. Secrets come from `.env`. Check that one command starts everything.

### 2.14 Measure and tune
- Run 10 varied companies by hand (active, dissolved, insolvent, large, tiny, ambiguous). Read every report and check each claim against Companies House.
- Time each node. **Record the real Reporter latency and rough cost.** That's the number the design left as a guess.
- Update `11-system-design.md`, the decision log and the risk register (R3, R7, R12).

### 2.15 Close the phase
- Coverage at 80% or above, CI green, milestone closed, Friday demo to AAII, and a weekly update.

---

## Order

```
Prototype Reporter → 2.1 → 2.2 → 2.3 ─┐
                              2.4 → 2.5 → 2.6 → 2.7 → 2.8 ─┤→ 2.9 → 2.10 → 2.11 → 2.12 → 2.13 → 2.14 → 2.15
```

2.3 and 2.4 can be built in either order. 2.9 depends on all of 2.5-2.8.

---

## Honest notes

- **Don't claim accuracy numbers after this phase.** You'll have a working agent but no benchmark until Phase 3. A few manual checks are a sanity test, not a metric.
- **Resist the free-form agent.** Keeping the Researcher, Verifier and red flags deterministic is what makes the Phase 3 evals meaningful, because you can tell a retrieval bug from a writing error.
- **Keep prompts in files,** not scattered in code. You'll rewrite them many times, and the history shows how you iterated.
- **Commit the prototype notebook** (outputs stripped) with a short note on what it taught you. It's good interview material.

**One question before I write code:** which LLM provider do you have an API key for? That settles ADR-003 and the dependency choices for steps 2.1 and 2.3.