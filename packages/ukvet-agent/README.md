# ukvet-agent

LangGraph due-diligence agent for UK companies. Part of [ukvet](../../README.md).

A fixed workflow, not an autonomous agent: **Planner → Researcher → Verifier → Reporter**. The first three are deterministic code over the [`ukvet-mcp`](../ukvet-mcp) tools. Only the Reporter can use an LLM, and every sentence it writes must cite fact IDs and pass a deterministic check (IDs exist, dates and numbers match the cited facts, no wrongdoing wording) or it is dropped. Red flags and the risk level come from rules.

```bash
export CH_API_KEY=...                 # Companies House key
ukvet-check --full 00445790           # terminal
python -m ukvet_agent                 # API on :8000 (POST /v1/reports, GET /health)
```

Optional narrative LLM: `LLM_PROVIDER` (`openai` | `anthropic` | `openai_compatible`), `LLM_MODEL`, `LLM_API_KEY`, `LLM_BASE_URL`. Default is no LLM (template narrative).