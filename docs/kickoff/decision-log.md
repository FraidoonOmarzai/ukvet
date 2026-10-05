# Decision Log

Every meaningful decision, in order. Short entries.

| # | Date | Decision | Why | Alternatives | Made by |
|---|---|---|---|---|---|
| 1 | 26 Sep 2026 | Build ukvet (Companies House due-diligence agent) as portfolio project 2 | Fully solo-controllable; UK-relevant; covers agents, MCP, evals | Client-facing trades receptionist agent (needed clients) | Fraidoon |
| 2 | 26 Sep 2026 | Proceed even though Companies House MCP servers already exist | Differentiation is measured reliability (evals, verifier, citations), not data access | Pick a different data source | Fraidoon |
| 3 | 26 Sep 2026 | Name: `ukvet` (repo), `ukvet-mcp`, `ukvet-agent` (packages) | Short, descriptive, not tied to one data source | probity, redflag-uk, companycheck-agent | Fraidoon |
| 4 | 26 Sep 2026 | MIT licence, copyright Fraidoon Omarzai | Maximise adoption; matches MCP SDK and LangGraph licences | Apache-2.0, AGPL-3.0 | Fraidoon |
| 5 | 26 Sep 2026 | Start with Phase 0 planning before code | Avoid building on unverified data assumptions | Start coding immediately | Fraidoon |
