# Success Metrics

| Field | Value |
|---|---|
| Version | 0.1 (Draft) |
| Date | 24 Sep 2026 |
| Owner | Fraidoon Omarzai |

Targets are **fixed now, before building**, so results can't be judged against goalposts moved afterwards. Any change to a target must be recorded in the decision log with a reason.

---

## 1. Quality metrics (measured on the eval set)

| ID | Metric | Definition | Target |
|---|---|---|---|
| M1 | Factual accuracy | % of factual claims in answers that match the ground truth from the Companies House API | ≥ 90% overall, and ≥ 80% on every individual question category Q1–Q9 |
| M2 | Hallucination rate | % of factual claims that are **not supported** by any retrieved record | < 2% |
| M3 | Correct abstention | % of cases with missing/unavailable data where the agent correctly says "insufficient data" instead of answering | ≥ 90% |
| M4 | Citation validity | % of factual claims with a citation that points to a real record which actually supports the claim | 100% |
| M5 | Red-flag recall | % of known red flags (seeded in the eval set) that appear in the Q10 summary | ≥ 85% |
| M6 | Prompt-injection resistance | % of adversarial cases (malicious text in company names/filings) where the agent does not follow the injected instruction | ≥ 95% |

**Notes**
- A "factual claim" = a single checkable statement (e.g. "The company was incorporated on 3 March 2021").
- M1, M3, M4 and M5 are checked with rule-based comparisons against ground truth wherever possible. LLM-as-judge is used only for report quality and must be spot-checked by hand.
- M1 is reported **per question category**, not just overall — an average can hide a category that fails badly.

## 2. Performance and cost

| ID | Metric | Definition | Target |
|---|---|---|---|
| M7 | Latency (p95) | Time from request to complete report, 95th percentile across the eval run | < 30 seconds |
| M8 | Cost per report | Average LLM cost per full report (from token usage tracked in Langfuse) | < £0.05 |
| M9 | Tool calls per report | Average number of MCP tool calls per full report | Tracked; no target in v0.1 (baseline first) |

## 3. Engineering

| ID | Metric | Definition | Target |
|---|---|---|---|
| M10 | Test coverage | Line coverage across MCP server and agent packages | ≥ 80% |
| M11 | CI health | Lint, type check, tests and evals pass on `main` | Always green on `main` |
| M12 | Eval regression gate | A PR that lowers M1, M2 or M4 beyond tolerance is blocked | Enforced in CI |

## 4. Adoption (tracked, no targets)

| ID | Metric | Source |
|---|---|---|
| M13 | PyPI downloads of the MCP server | PyPI stats |
| M14 | GitHub stars and forks | GitHub |
| M15 | Issues/PRs opened by external users | GitHub |
| M16 | Medium article reads | Medium stats |

No targets, because adoption is outside direct control. Report real numbers, whatever they are.

## 5. Model comparison (Phase 5)

Report M1, M2, M4, M7 and M8 for both models in one table:

| Model | Accuracy (M1) | Hallucination (M2) | Citation validity (M4) | p95 latency (M7) | Cost/report (M8) |
|---|---|---|---|---|---|
| Frontier API model | | | | | |
| Open-weight model | | | | | |

## 6. When metrics are measured

| Metric | When |
|---|---|
| M1–M6 | Every PR (CI, subset) + full eval run at the end of each phase |
| M7–M9 | Every full eval run |
| M10–M12 | Every PR |
| M13–M16 | Weekly, and at launch + 30 days |

## 7. Reporting rules

1. Report every metric against its target — **including misses**.
2. For every miss, give the likely cause and what would fix it.
3. State the eval set size and composition next to every result.
4. Never report only the best run; report the final committed version.
