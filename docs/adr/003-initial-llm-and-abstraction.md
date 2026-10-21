# ADR-003: LLM and model abstraction

- **Status:** Accepted (amended 19 Oct 2026; model chosen 21 Oct 2026, end of Phase 2)
- **Date:** 26 Sep 2026

## Context
We need one LLM for development now and a second (open-weight) model for the Phase 5 comparison. Requirements: reliable structured output, low cost per report (M8 < £0.05). The owner has access to OpenAI, Anthropic and a free-tier API.

## Decision
- All models are reached through **LangChain chat models** behind a tiny `NarrativeWriter` interface (`ukvet_agent/llm.py`), selected by environment variables: `LLM_PROVIDER` (`none` | `openai` | `anthropic` | `openai_compatible`), `LLM_MODEL`, `LLM_API_KEY`, `LLM_BASE_URL`.
- **Default is `none`**: no LLM, reports use a deterministic template narrative. The system is fully usable, and CI never needs a key.
- `openai_compatible` covers free-tier and open-weight endpoints (Groq, Together, OpenRouter, Ollama, vLLM), which also serves the Phase 5 comparison.
- The LLM is used in **one place only**: the Reporter's narrative (headline plus findings) as structured output. It has no tools (ADR-007).
- **Model IDs are not hard-coded.** The exact `LLM_MODEL` and provider must be recorded with every eval result and in the README results table. Pick the first model on cost and structured-output reliability after running the live smoke test (`make live`) against two or three candidates.

## Alternatives considered
| Option | Why not |
|---|---|
| Hard-code one provider SDK | Makes the Phase 5 comparison expensive |
| Require an LLM | Blocks offline use, CI and anyone without a key |
| Open-weight model from day one | Slower development; structured-output reliability unknown |

## Consequences
- Switching or comparing models is a config change.
- If the LLM errors, times out or fails the citation check twice, the report falls back to the template narrative. A report is always produced; `narrative_source` says which was used.
- Avoid provider-specific prompt features. `temperature` is only sent if `LLM_TEMPERATURE` is set, because some models reject it.

## Model chosen (21 Oct 2026, end of Phase 2)

**Provider `anthropic`, model `claude-haiku-5-5`** for development and the first eval runs.

Why: it is the cheapest Claude model, the Reporter makes one short call per report, and it passed the citation checker on every report in a real run. A larger model was not compared, so this is the first model that worked, not the best one tested.

Measured on 10 real companies (live Companies House API, `scripts/measure.py`, cold then warm cache, 20 runs):

| Measure | Result |
|---|---|
| Reports with an LLM narrative | 20 of 20 (no template fallback) |
| Claims failing the citation checker on the first attempt | 1 of 88 (cold run), 0 of 88 (warm run) |
| Retries | 1 in each run |
| Total time per report | median about 3.2 s, worst 5.9 s (template mode: median 0.18 s, worst 0.69 s) |
| Share of time spent in the LLM call | about 95% |
| Cost per report | about $0.0005 (about £0.0004): $0.01 for about 22 calls, provider dashboard rounded to the cent |

How to read these results:
- The sample is small (10 companies, 2 runs) and the run-to-run difference of 1 versus 0 dropped claims is noise.
- The citation checker verifies fact IDs, dates, numbers and banned wording. It does not check names or tone (R15), so this is not a hallucination rate. That is measured in Phase 3.
- Cost comes from a dashboard that rounds to the cent. Add a token-based figure when a larger run is done.

Revisit when: the Phase 3 evals show names or wording errors; a larger model scores clearly better on the eval set; or the Phase 5 comparison adds an open-weight model. Record the exact `LLM_MODEL` with every eval result.
