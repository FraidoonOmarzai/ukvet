# Scope

| Field | Value |
|---|---|
| Version | 0.1 (Draft) |
| Date | 24 Sep 2026 |
| Owner | Fraidoon Omarzai |

Anything not listed as **in scope** is out of scope by default. Changes to scope must be recorded in the decision log with a reason.

---

## 1. In scope (MVP)

### MCP server
- Python MCP server using the official `mcp` SDK.
- Tools covering: company search, company profile, officers, filing history, persons with significant control, charges, insolvency, and officer appointments.
- Authentication via Companies House API key (environment variable).
- Rate limiting, retries with backoff, and response caching.
- Correct handling of "no data" responses (e.g. a company with no charges is a valid answer, not an error).
- Published to PyPI with install and usage docs.

### Agent
- Answers questions **Q1–Q10** (see `02-users-and-questions.md`) for **one UK company per request**.
- Accepts a company name or company number.
- Handles ambiguous names by showing candidate matches and asking the user to choose.
- Produces a structured report: facts, red flags, overall assessment, citations.
- Every factual claim cited to a Companies House record.
- Returns "insufficient data" instead of guessing.
- Disclaimer on every report: informational only, not legal or financial advice.

### Interfaces
- FastAPI backend endpoint.
- Simple Streamlit UI.
- Docker / docker-compose for local run.

### Quality and operations
- Evaluation dataset and harness covering Q1–Q10 plus adversarial cases.
- Evals run in GitHub Actions; merges blocked on score regressions.
- Tracing with Langfuse: latency, cost, tool calls, errors.
- Prompt-injection defence for untrusted text (company names, filing descriptions).
- Output validation with Pydantic schemas.
- Unit and integration tests using recorded API fixtures.

### Model comparison
- Same eval run on one frontier API model and one open-weight model; results published as a table.

### Documentation
- README, architecture diagram, ADRs, data notes, legal & ethics note, write-up.

---

## 2. Out of scope

| Item | Reason |
|---|---|
| Credit scores or predictions of future failure | Requires financial modelling and data we don't have; high risk of misleading users |
| Legal, financial or investment advice | Liability; the tool informs, it does not advise |
| Non-UK companies | Different registries and data formats |
| Sole traders and ordinary partnerships | Not registered at Companies House |
| Paid or scraped data sources | Licensing, cost and reliability |
| Reading the contents of filed PDF documents (e.g. full accounts) | Significant extra complexity; MVP uses structured API data only |
| Storing a database of people or companies | Privacy (UK GDPR); only short-lived caching |
| User accounts, login, payments | Not needed to prove the concept |
| Monitoring / alerts when a company changes | Requires scheduling and storage; v2 candidate |
| Mobile app | Streamlit web UI is sufficient |

---

## 3. Later (v2 backlog)

Recorded so they don't creep into the MVP:

- The Gazette notices (insolvency and strike-off notices).
- FCA Financial Services Register checks.
- Comparing two or more companies side by side.
- Reading key figures from filed accounts.
- Company change monitoring and alerts.
- Hosted public demo with usage limits.

---

## 4. Constraints

| Constraint | Detail |
|---|---|
| Time | ~5 weeks, solo |
| Budget | Low — free Companies House API; LLM and GPU spend kept minimal and tracked |
| Data | Companies House public API only; rate limits apply (to confirm in API spike) |
| Licensing | Companies House data reused under the Open Government Licence, with attribution |
| Privacy | Director details are personal data under UK GDPR — no long-term storage, no profiling features |
| Team | One engineer |

---

## 5. MVP definition of done

The MVP is complete when **all** of the following are true:

- [ ] MCP server published to PyPI and installable in Claude Desktop.
- [ ] Agent answers Q1–Q10 for any active UK company number.
- [ ] Eval harness runs in CI and blocks regressions.
- [ ] Results reported against every target in `04-success-metrics.md` (met or not).
- [ ] Langfuse tracing live, with cost per report recorded.
- [ ] Model comparison table published.
- [ ] Docker setup runs the full system with one command.
- [ ] README, architecture docs and write-up complete.
