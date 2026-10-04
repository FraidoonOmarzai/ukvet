# ADR-003: Initial LLM and model abstraction

- **Status:** Proposed — finalise at start of Phase 2
- **Date:** 04 Oct 2026

## Context
We need one LLM for development now and a second (open-weight) model for the Phase 5 comparison. Requirements: reliable tool calling, structured output, low cost per report (M8 < £0.05).

## Decision
- Start with **one frontier API model** that supports tool calling and structured output. Choose on cost and structured-output reliability at the start of Phase 2, and record the exact model ID here.
- Access all models through a **single chat-model interface** (LangChain chat models), configured by environment variable, so swapping models is a config change.
- Phase 5 open-weight model is served through an **OpenAI-compatible endpoint** (e.g. vLLM), which the same interface supports.

## Alternatives considered
| Option | Why not |
|---|---|
| Open-weight model from day one | Slower development; tool-calling reliability risk early on |
| Hard-code one provider's SDK | Makes the Phase 5 comparison expensive to build |

## Consequences
- Model comparison is cheap to run.
- Must avoid provider-specific features in prompts and tools.
- Record exact model IDs with every eval result.
