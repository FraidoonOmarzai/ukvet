# Problem Statement — UK Company Due-Diligence Agent

| Field | Value |
|---|---|
| Project | UK Company Due-Diligence Agent + Companies House MCP Server |
| Organisation | Afghanistan Artificial Intelligence Institute (AAII) |
| Owner | Fraidoon Omarzai |
| Version | 0.1 (Draft) |
| Date | 24 Sep 2026 |

---

## 1. Background

Every UK limited company must register with Companies House, which publishes company profiles, officers (directors), filing history, persons with significant control (PSC), charges (secured debts) and insolvency records. This data is free, official and available through a public API.

Despite this, most small businesses and individuals never check who they are dealing with before signing a contract, extending payment terms or paying a deposit.

## 2. The problem

Checking a company properly is **slow, manual and requires know-how**:

- The information is spread across several pages (profile, officers, filings, PSC, charges, insolvency).
- Spotting risk requires interpretation — e.g. knowing that overdue accounts, frequent director changes or directors linked to many dissolved companies are warning signs.
- Tracing a director's other companies means opening each appointment one by one.
- A thorough check can take **20–40 minutes** *(assumption — to be validated with users, see §7)*.

As a result, people either skip the check or do a shallow one (e.g. "the company exists, so it's fine").

## 3. Who is affected

- **Small business owners and tradespeople** taking on new commercial clients.
- **Freelancers and contractors** deciding whether a client is likely to pay.
- **Procurement and operations staff at small organisations** (charities, SMEs) vetting suppliers without a dedicated compliance team.

Full personas: see `02-users-and-questions.md`.

## 4. Current alternatives and their gaps

| Alternative | Gap |
|---|---|
| Manual Companies House search | Slow; requires expertise to interpret; no cross-referencing of directors |
| Paid business-intelligence tools (e.g. Endole, Creditsafe) | Cost money; built for professionals; overkill for a one-off check |
| General chatbots (ChatGPT, Claude, etc.) without data access | No reliable live data; can invent facts about companies and people |

## 5. Why an AI agent

The data is structured, but the **judgement** is not. A useful answer requires:

1. Deciding what to look up based on the question,
2. Calling several data sources,
3. Cross-checking facts (e.g. a director's other appointments),
4. Summarising risk in plain English — **with a source for every claim**.

This multi-step "plan → retrieve → verify → report" loop is what agentic systems are suited for. Grounding every statement in official data addresses the main weakness of general chatbots: hallucination.

## 6. Proposed solution

Two deliverables:

1. **Companies House MCP server (open source).** Exposes Companies House data as Model Context Protocol tools, so any MCP-compatible AI application (Claude Desktop, Cursor, custom agents) can use it. Published to PyPI.
2. **Due-diligence agent.** A LangGraph agent that uses the MCP server to produce a cited risk report for a UK company, with an evaluation harness proving its accuracy.

### Final problem statement

> UK small businesses and freelancers regularly engage suppliers and clients without checking their legitimacy, because manual Companies House research is slow and requires expertise. We will build an AI agent that produces a cited due-diligence report on any UK company in under 30 seconds, using only official public data, and an open-source MCP server so other AI tools can access the same data.

## 7. Assumptions to validate

These are **beliefs, not facts**, until checked. Validation method: short interviews with 3–5 target users (see `02-users-and-questions.md`, §4). `I will check with a few users, if not will go with assumption`

| ID | Assumption | How to validate | Status |
|---|---|---|---|
| A1 | Target users rarely check companies before engaging them | User interviews | Open |
| A2 | A manual check takes 20–40 minutes | Time 3 manual checks yourself + ask users | Open |
| A3 | Users would trust an AI report if every claim is cited | User interviews (show a mock report) | Open |
| A4 | Companies House data can answer the 10 core questions | Phase 0 Step 5 API spike | Open |
| A5 | The report can be generated in under 30 seconds within API rate limits | Phase 0 Step 5 API spike | Open |

## 8. Related documents

- `02-users-and-questions.md` — personas and core user questions
- `03-scope.md` — in scope, out of scope, later
- `04-success-metrics.md` — measurable targets

## 9. Sign-off

| Role | Name | Decision | Date |
|---|---|---|---|
| Engineer / Owner | Fraidoon Omarzai | Proposed | 24 Sep 2026 |
| AAII Stakeholder | | | |
