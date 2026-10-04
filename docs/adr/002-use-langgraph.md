# ADR-002: Use LangGraph for agent orchestration

- **Status:** Accepted
- **Date:** 04 Oct 2026

## Context
The agent follows plan → research → verify → report, with a possible loop back from verify to research. We need explicit state, controllable loops and good observability.

## Decision
Use LangGraph with a typed state object and four nodes (Planner, Researcher, Verifier, Reporter).

## Alternatives considered
| Option | Why not |
|---|---|
| Single ReAct-style agent loop | Less control; harder to enforce "report only from verified facts"; harder to evaluate step by step |
| Other agent frameworks (CrewAI, AutoGen, OpenAI Agents SDK) | Viable, but less explicit control over graph structure; no existing experience |
| Plain Python orchestration | Possible, but re-implements state, checkpointing and tracing integration |

## Consequences
- Each node can be tested and evaluated separately.
- Existing experience (Corrective RAG project) reduces risk.
- Dependency on LangGraph's API stability — pin versions.
