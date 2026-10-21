# Risk Register

| Field | Value |
|---|---|
| Version | 0.2 (updated 21 Oct 2026, end of Phase 2) |
| Owner | Fraidoon Omarzai |
| Review | Every Friday at the weekly demo |

Likelihood / Impact: **L** low · **M** medium · **H** high

| ID | Risk | Likelihood | Impact | Mitigation | Trigger to act | Status |
|---|---|---|---|---|---|---|
| R1 | Rate limit (600/5 min) slows development and eval runs | H | M | Response cache; recorded fixtures for tests; evals run on cached data; parallelism capped | 429 responses in logs | Mitigated (Phase 1): limiter, cache, fixtures |
| R2 | Q8 director network needs too many API calls | M | H | Measure in spike; cap directors and appointments per report; state the cap in the report | Spike shows > 50 calls/report | Server side mitigated (caps, 1 call per director); agent-level director cap decided in Phase 2 |
| R3 | LLM states facts not in the data (hallucination) | H | H | Verifier node; citation required per claim; schema validation; evals M2/M4 | M2 > 2% | Mitigated and measured (Phase 2, 21 Oct 2026): with `claude-haiku-5-5`, 1 of 88 claims failed the checker on the first attempt in one 10-company run and 0 of 88 in a second run; both runs needed one retry and ended with an LLM narrative (20 of 20, no template fallback). Facts and red flags are rule-based and showed no errors in a manual check of about 75 values (`accuracy-check.md`). NOT a hallucination rate: the checker verifies fact IDs, dates, numbers and banned wording only. Real rate to be measured in Phase 3 evals |
| R4 | Eval set too small or unrepresentative → false confidence | M | H | Stratify by company type and question; include adversarial and missing-data cases; report set size with every result | Any category < 15 items | Open |
| R5 | Scope creep (Gazette, FCA, PDFs, UI polish) | H | M | `03-scope.md` out-of-scope list; v2 backlog; changes logged | New feature idea mid-phase | Open |
| R6 | Prompt injection through company names/filings | M | H | Treat API text as data; delimiters; injection eval cases (M6) | Any injection eval failure | Seeded (Phase 1): server instructions mark API text as untrusted; evals in Phase 4 |
| R7 | LLM costs higher than planned | M | M | Track cost per report (M8); cheaper model for simple nodes; cache LLM calls in evals | M8 > £0.05 | Measured (Phase 2, 21 Oct 2026): about £0.0004 per report with `claude-haiku-5-5` ($0.01 for about 22 calls, provider dashboard rounded to the cent; token-level figure to be added). Target £0.05, met. Template mode costs nothing. Cost of a larger model not yet measured |
| R8 | Companies House API changes or downtime | L | M | Retries with backoff; clear error messages; fixtures keep tests independent | Unexpected 5xx / schema errors | Partly mitigated (Phase 1): retries, typed errors, clean messages on odd shapes |
| R9 | Same person under multiple officer IDs → Q8 incomplete | H | M | Document as a known limitation; don't claim completeness | Found in spike | Documented (Phase 1): README limits + tool descriptions |
| R10 | Personal data leaks (fixtures, traces, public eval set) | M | H | Rules in `06-legal-and-ethics.md`; `data/raw` git-ignored; Gitleaks in CI | Any personal data in a PR | Mitigated (Phase 1): data minimised in models; anonymiser + leak check |
| R11 | Solo project stalls (time, motivation, job search) | M | H | Weekly demo; small issues (≤ 1 day); ship each phase usable on its own | 2 weeks with no merged PR | Open |
| R12 | Latency target (30 s) missed | M | M | Parallel API calls; smaller model for early nodes; measure early | p95 > 30 s in Phase 2 | Measured (Phase 2, 21 Oct 2026), 10 companies: template mode median 0.18 s, worst 0.69 s cold; with `claude-haiku-5-5` median about 3.2 s, worst 5.9 s over 20 runs. Target 30 s, met. The LLM call is about 95% of the time. Sample is small, so quote 'worst of 10', not p95. Live-API variation over time and other models not measured |
| R13 | Open-weight model too weak for Phase 5 comparison | M | L | It's a comparison, not a requirement — report honestly | Accuracy far below API model | Open |
| R14 | MCP subprocess dies and the API is not restarted | L | M | `/health` reports `degraded` (503); requests degrade to gaps; container restart fixes it | Health 503 in the field | Open (ADR-008): add reconnect if it ever happens |
| R15 | Citation checker gives false confidence: it cannot catch a wrong name or an unfair characterisation | M | H | State the limit everywhere; names come from sanitised facts; Phase 3 evals measure names and wording; wrongdoing-wording filter | Any eval failure on names or tone | Open (Phase 2): no wrong names found in the manual check, but narratives written by the LLM have not been read systematically for tone and fairness. Rule fairness reviewed: six rule or display fixes made (decision log #28 onwards). Phase 3 evals must measure names and wording |
| R16 | Docker setup fails on first real build (never built in the authoring environment) | M | L | CI builds both images; install path replayed with `uv sync --frozen`; fix on first failure | First `docker compose up` or CI docker job fails | Partly closed (Phase 2): owner reports the local Docker build and run worked. CI docker job not yet confirmed green. Close after the first green CI run |
| R17 | Red-flag severity thresholds are judgement calls and can misrate a company (e.g. solvent liquidation as high, one linked liquidation as medium) | M | H | Rules are deterministic and unit-tested; wording says 'opinion from rules'; every flag shows its evidence; review each rule against real companies; log every change | A real company is rated unfairly | Open (Phase 2): six fixes after reviewing 10 companies; thresholds not yet validated on a larger set. Phase 3 should measure flag precision |

## Closed risks

| ID | Risk | How it closed | Date |
|---|---|---|---|
| — | | | |
