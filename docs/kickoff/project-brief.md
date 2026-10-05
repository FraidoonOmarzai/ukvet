# Project Brief — ukvet

**To:** AAII leadership  
**From:** Fraidoon Omarzai  
**Date:** 05 Oct 2026  
**Decision needed:** Approve to proceed

---

**What:**  
`ukvet` — an AI agent that produces a cited due-diligence report on a UK company using official Companies House data, with an open-source MCP server so other AI tools can access the same data.

**Why:**  
Small businesses and freelancers may not check who they are dealing with because manual due-diligence checks are time-consuming and require expertise. Existing tools are often paid, while existing open-source MCP servers primarily provide data access without measured end-to-end reliability. `ukvet` focuses on a verified and evaluated agent with source citations.

**Why AAII:**  
The project demonstrates production-oriented agentic AI, MCP integration and evaluation practices. It also produces open-source tooling and potential teaching material for the AAII curriculum.

**Scope (MVP):**  
One UK company per report; 10 core questions covering company status, age, directors, overdue filings, control, charges, insolvency, director history, recent changes and red flags.

Out of scope: credit scoring, financial/legal advice, non-UK companies and paid data sources.

**Success measures:**  
- ≥ 90% factual accuracy
- < 2% hallucination rate
- 100% cited claims
- < 30 seconds per report
- < £0.05 per report

Results will be published, including failures and limitations.

**Timeline:**  
Approximately 6 weeks across 7 phases, from project definition through to launch.

**Cost:**  
The Companies House API is free. LLM and GPU costs will be tracked, with an initial total budget estimate of < £100. Actual costs will be measured during development and model evaluation.

**Top risks:**  
API rate limits → caching and recorded fixtures  
Hallucination → verification and evaluation  
Personal data handling → data minimisation, short-lived local caching and no unnecessary person profiling  
Scope creep → fixed MVP scope and controlled backlog

**Deliverables:**  
- `ukvet-mcp` published to PyPI
- `ukvet` agent with API and UI
- Docker-based deployment
- Open evaluation benchmark
- Evaluation results and model comparison
- Two project articles

**Full details:**  
See `docs/01`–`09` and the supporting development documentation in `development/`.

---

| Decision | Name | Date |
|---|---|---|
| ☐ Approved ☐ Approved with changes ☐ Not approved | | |