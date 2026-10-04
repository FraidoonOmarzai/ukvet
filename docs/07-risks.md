# Risk Register

| Field | Value |
|---|---|
| Version | 0.1 |
| Owner | Fraidoon Omarzai |
| Review | Every Friday at the weekly demo |

Likelihood / Impact: **L** low · **M** medium · **H** high

| ID | Risk | Likelihood | Impact | Mitigation | Trigger to act | Status |
|---|---|---|---|---|---|---|
| R1 | Rate limit (600/5 min) slows development and eval runs | H | M | Response cache; recorded fixtures for tests; evals run on cached data; parallelism capped | 429 responses in logs | Open |
| R2 | Q8 director network needs too many API calls | M | H | Measure in spike; cap directors and appointments per report; state the cap in the report | Spike shows > 50 calls/report | Open |
| R3 | LLM states facts not in the data (hallucination) | H | H | Verifier node; citation required per claim; schema validation; evals M2/M4 | M2 > 2% | Open |
| R4 | Eval set too small or unrepresentative → false confidence | M | H | Stratify by company type and question; include adversarial and missing-data cases; report set size with every result | Any category < 15 items | Open |
| R5 | Scope creep (Gazette, FCA, PDFs, UI polish) | H | M | `03-scope.md` out-of-scope list; v2 backlog; changes logged | New feature idea mid-phase | Open |
| R6 | Prompt injection through company names/filings | M | H | Treat API text as data; delimiters; injection eval cases (M6) | Any injection eval failure | Open |
| R7 | LLM costs higher than planned | M | M | Track cost per report (M8); cheaper model for simple nodes; cache LLM calls in evals | M8 > £0.05 | Open |
| R8 | Companies House API changes or downtime | L | M | Retries with backoff; clear error messages; fixtures keep tests independent | Unexpected 5xx / schema errors | Open |
| R9 | Same person under multiple officer IDs → Q8 incomplete | H | M | Document as a known limitation; don't claim completeness | Found in spike | Open |
| R10 | Personal data leaks (fixtures, traces, public eval set) | M | H | Rules in `06-legal-and-ethics.md`; `data/raw` git-ignored; Gitleaks in CI | Any personal data in a PR | Open |
| R11 | Solo project stalls (time, motivation, job search) | M | H | Weekly demo; small issues (≤ 1 day); ship each phase usable on its own | 2 weeks with no merged PR | Open |
| R12 | Latency target (30 s) missed | M | M | Parallel API calls; smaller model for early nodes; measure early | p95 > 30 s in Phase 2 | Open |
| R13 | Open-weight model too weak for Phase 5 comparison | M | L | It's a comparison, not a requirement — report honestly | Accuracy far below API model | Open |

## Closed risks

| ID | Risk | How it closed | Date |
|---|---|---|---|
| R9 | Same person under multiple officer IDs → Q8 incomplete | Identified and documented as a known limitation during the API spike; Q8 will not claim complete identity matching | 2026-10-04 |

