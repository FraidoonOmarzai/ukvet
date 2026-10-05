# ukvet — AI Due-Diligence Agent for UK Companies

**Vet any UK company in 30 seconds — cited, evaluated, open source.**

<!-- [![CI](https://github.com/fraidoonomarzai/ukvet/actions/workflows/ci.yml/badge.svg)](https://github.com/fraidoonomarzai/ukvet/actions/workflows/ci.yml) -->
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

> **Status: Phase 0 — planning and API spike.** Not yet functional. Follow progress on the project board.

## What it does

Enter a UK company name or number. ukvet checks official Companies House records and returns a risk report answering:

1. Is it active, dissolved or insolvent?
2. How old is it?
3. Who are the directors?
4. Are its accounts or confirmation statement overdue?
5. Who controls it?
6. Does it have secured debts (charges)?
7. Any insolvency history?
8. Have its directors run companies that failed?
9. Any recent changes of directors or address?
10. **What are the red flags?**

Every fact is cited to the official record. When data is missing, ukvet says so instead of guessing.

## How it's built

| Part | What |
|---|---|
| `ukvet-mcp` | Open-source MCP server exposing Companies House data to any MCP client |
| `ukvet-agent` | LangGraph agent: Planner → Researcher → Verifier → Reporter |
| Evals | 200+ item benchmark; accuracy, hallucination, citation validity; gated in CI |
| Observability | Langfuse tracing of cost, latency and tool calls |

Architecture: [docs/08-architecture.md](docs/08-architecture.md)

## Results



## Development

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/YOUR_GITHUB_USERNAME/ukvet.git
cd ukvet
cp .env.example .env      # add your Companies House API key
make install              # dependencies + git hooks
make check                # lint, type check, tests
make notebook             # API exploration notebook
```

## Project documents

| Doc | Contents |
|---|---|
| [01 Problem statement](docs/01-problem-statement.md) | Why ukvet exists |
| [02 Users and questions](docs/02-users-and-questions.md) | Personas and Q1–Q10 |
| [03 Scope](docs/03-scope.md) | In, out, later |
| [04 Success metrics](docs/04-success-metrics.md) | Targets fixed before building |
| [05 Data notes](docs/05-data-notes.md) | API findings |
| [06 Legal and ethics](docs/06-legal-and-ethics.md) | Licensing, UK GDPR, misuse |
| [07 Risks](docs/07-risks.md) | Risk register |
| [08 Architecture](docs/08-architecture.md) | Design + [ADRs](docs/adr/) |
| [09 Plan](docs/09-plan.md) | Milestones, backlog, workflow |

## Disclaimer

ukvet is informational only. It is not legal, financial or credit advice. Reports are based on public records at the time of retrieval, which may be incomplete or out of date. Always verify before making decisions. ukvet is not affiliated with Companies House.

## Attribution

Contains public sector information licensed under the [Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/) (Companies House).

## Licence

Code: [MIT](LICENSE) © 2026 Fraidoon Omarzai
