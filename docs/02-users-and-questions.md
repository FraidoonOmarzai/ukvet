# Users and Core Questions

| Field | Value |
|---|---|
| Version | 0.1 (Draft) |
| Date | 24 Sep 2026 |
| Owner | Fraidoon Omarzai |

---

## 1. Primary personas (For now its *unvalidated*)

### Persona 1 — Sarah, self-employed plumber
- **Context:** Runs a one-person plumbing business. Mostly domestic work, but increasingly quoted by property management and small construction companies.
- **Trigger:** A new company client asks for 60-day payment terms on a £4,000 job.
- **Goal:** Know quickly whether the company is real, active and likely to pay.
- **Pain:** Has heard of Companies House but doesn't know what to look for. No time — checks happen on her phone between jobs.
- **Tech comfort:** Low–medium. Wants a plain-English answer, not raw data.
- **"Good" looks like:** A clear verdict with the key red flags in under a minute.

### Persona 2 — Daniel, operations manager at a small charity
- **Context:** Handles procurement for a 25-person charity with no compliance team.
- **Trigger:** Choosing between three IT suppliers for a 2-year contract.
- **Goal:** Confirm each supplier is stable and has no history of insolvency or problem directors.
- **Pain:** Has to justify supplier choice to trustees; manual checks take too long across multiple suppliers.
- **Tech comfort:** Medium.
- **"Good" looks like:** A report with sources he can paste into a board paper.

### Persona 3 — Amira, freelance software developer
- **Context:** Works with startups on contracts of £5k–£20k.
- **Trigger:** A young startup offers a contract; she's been burned by an unpaid invoice before.
- **Goal:** Check whether the company is newly formed, who's behind it, and whether its founders have a history of failed companies.
- **Pain:** Tracing directors' other companies manually is tedious.
- **Tech comfort:** High. Would also use the MCP server directly inside Claude Desktop or Cursor.
- **"Good" looks like:** Director history and red flags, with links to verify herself.

### Secondary user — AI developers
Developers who want UK company data inside their own AI applications. They use the **MCP server**, not the agent. Success for them = easy install, reliable tools, clear docs.

---

## 2. Core user questions

These ten questions define the MVP. Each becomes a **requirement** and an **evaluation category** (Phase 3).

Data sources are **hypotheses** until confirmed in Phase 0 Step 5 (API spike).

| ID | Question | Why it matters | Likely data source (to confirm) | Answer type | Personas |
|---|---|---|---|---|---|
| Q1 | Is the company active, dissolved or in liquidation? | Dissolved companies can't trade | Company profile | Status + date | All |
| Q2 | How old is the company? | Very new companies carry more risk | Company profile (incorporation date) | Date + age | All |
| Q3 | Who are the current directors? | Know who you're dealing with | Officers | List of names + appointment dates | All |
| Q4 | Are the accounts or confirmation statement overdue? | Overdue filings are a common warning sign | Company profile (accounts / confirmation statement) | Yes/No + due dates | All |
| Q5 | Who ultimately controls the company? | Hidden ownership is a risk | Persons with significant control | List of PSCs + nature of control | 2, 3 |
| Q6 | Are there any charges (secured debts) against it? | Indicates borrowing secured on assets | Charges | Count + outstanding/satisfied | 2 |
| Q7 | Does it have any insolvency history? | Direct financial-risk signal | Insolvency | Yes/No + case details | All |
| Q8 | Have the directors been involved with companies that were dissolved or went insolvent? | Pattern of failed companies is a major red flag | Officer appointments → each linked company profile | List of linked companies + statuses | 2, 3 |
| Q9 | Have there been recent changes to directors or registered address? | Frequent recent changes can signal instability | Officers (appointed/resigned dates), filing history | List of changes in last 12 months | 2, 3 |
| Q10 | Overall, what are the red flags? | The user's real question | Synthesis of Q1–Q9 | Cited summary + risk level | All |

### Rules that apply to every answer
- Every factual claim must cite the specific Companies House record it came from.
- If data is missing or unavailable, the agent must say **"insufficient data"** rather than guess.
- Q10 must only use facts established in Q1–Q9 — no outside knowledge.
- Opinions (e.g. "risk level") must be clearly labelled as the agent's assessment, not fact.

---

## 3. Example requests (natural language)

Used for UI design and as early eval inputs:

- "Is ACME Building Services Ltd safe to work with?"
- "Check company number 01234567."
- "Who's behind this company and have they run failed businesses before?"
- "Has this supplier filed its accounts on time?"
- "Give me a due-diligence summary for [company name]."

---

## 4. User validation plan

Personas above are **assumptions**. I must validate them before Phase 2.

**Who:** 3–5 people matching the personas (tradespeople, small-organisation staff, freelancers).

**Interview script (15 minutes):**
1. When did you last start working with a new company? What did you check first?
2. Have you ever used Companies House? What was that like?
3. Have you ever been burned by a client or supplier? What would have warned you?
4. Which of these ten questions (show list) matter most to you? Which don't?
5. *(Show a mock report.)* Would you trust this? What would make you trust it more?
6. Where would you want to use this — phone, laptop, inside another tool?

**Output:** Update the personas, re-rank Q1–Q10, and record findings in `docs/user-research.md`.

**If interviews aren't possible in time:** proceed, but I must mark personas as *unvalidated*.
