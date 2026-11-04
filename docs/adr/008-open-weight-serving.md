# ADR-008: Serving the open-weight model for the Phase 5 comparison

| Field   | Value                                     |
| ------- | ----------------------------------------- |
| Status  | Draft: fill in while doing Phase 5 step 4 |
| Date    | 04/11/2026                                          |
| Related | ADR-003 (LLM abstraction), risk R13       |

## Context

Phase 5 compares one frontier API model with one open-weight model on the same dataset, prompt and
code. The open-weight model must be reachable through an OpenAI-compatible endpoint
(`LLM_PROVIDER=openai_compatible`).

## Decision

| Item                           | Value                                                                                                                                                                                                                                         |
| ------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Model (HF id)                  | `Qwen/Qwen3.6-27B`                                                                                                                                                                                                                            |
| Parameters / quantisation      | 27B dense, no quantisation (bf16)                                                                                                                                                                                                             |
| Licence                        | Apache 2.0 (per the Hugging Face model card)                                                                                                                                                                                                  |
| Context                        | 262,144 native; we serve 8192 to 16384 (ukvet prompts are small)                                                                                                                                                                              |
| Serving software               | vLLM, version 0.19.0 or newer (needed for the Qwen3.6 architecture); pin the exact tag you use                                                                                                                                                |
| Hardware                       | one 80 GB GPU (27B in bf16 is about 54 GB of weights, plus room for the KV cache). Record the GPU type, provider and price per hour when you rent it                                                                                          |
| Structured output / tool flags | `--enable-auto-tool-choice --tool-call-parser qwen3_coder` (the model card and a serving write-up both say the parser is required for tool calls, otherwise they fail silently); thinking switched OFF (see below)                            |
| Why this model                 | Passed the four checks: supports tool calling and structured output in vLLM; fits one rentable 80 GB GPU; permissive licence I can cite; recent (2026). Dense 27B is simpler to serve and to explain than the mixture-of-experts alternatives |

## Alternatives considered

- Hosted open-weight endpoint (Together, Groq, OpenRouter): cheaper and quicker, but latency and
  cost then describe that provider, not self-hosting. Used only as a labelled fallback.
- Ollama on a laptop: fine for a smoke test, not for M7.

## Consequences

- Cost per report for self-hosting depends on GPU utilisation; reports are generated one at a time,
  so the figure is a worst case. Stated next to the number in docs/results.md.
- The recordings in evals/llm_cache are specific to this model id and the current prompt text.
