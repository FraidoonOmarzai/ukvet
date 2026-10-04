# Legal and Ethics

| Field | Value |
|---|---|
| Version | 0.1 |
| Owner | Fraidoon Omarzai |
| Date | 4 Oct 2026 |

> This is an engineering assessment, not legal advice. If ukvet becomes a commercial product, get it reviewed by a qualified professional.

---

## 1. Data licence

- Companies House data is public and reusable under the **Open Government Licence v3.0 (OGL)**.
- OGL requires **attribution**. Every README, UI footer and report includes:
  > *Contains public sector information licensed under the Open Government Licence v3.0 (Companies House).*
- OGL does not permit implying official endorsement. ukvet must never suggest it is affiliated with, or approved by, Companies House.

## 2. Code licence

- ukvet's code is released under the **MIT License**. The MIT licence covers our code only, not the data.

## 3. Personal data (UK GDPR)

Directors' and PSCs' names, birth month/year, nationality and correspondence addresses are **personal data**, even though they are public.

| Principle | How ukvet complies |
|---|---|
| Purpose limitation | Used only to assess a **company**, never to profile an individual |
| Data minimisation | Only fields needed for Q1–Q10 are passed to the LLM and shown in reports |
| Storage limitation | Short-lived cache only (TTL, e.g. 24 hours). No long-term database of people |
| Accuracy | Every claim cited to the official record, so users can verify |
| Security | API keys in environment variables; no personal data in logs beyond what's needed for debugging |

### Specific rules
- **No person-search feature.** ukvet takes a company as input, never a person's name.
- **Raw API responses** (`data/raw/`) are git-ignored and never committed.
- **Test fixtures** committed to the repo must be either (a) about large public companies, or (b) anonymised — replace personal names with placeholders.
- **Tracing (Langfuse)** may capture prompts containing director names. Set a retention period and don't make traces public.
- **Eval datasets** published openly contain company-level facts; anonymise personal names where the question doesn't require them.

## 4. Output responsibility

- Every report carries the disclaimer:
  > *Informational only. Not legal, financial or credit advice. Based on public Companies House records at the time of the report, which may be incomplete or out of date. Verify before making decisions.*
- Risk levels are labelled as **the agent's assessment**, not fact.
- ukvet never states or implies wrongdoing by an individual. Example: say "Director X was also a director of 3 companies that were dissolved", **not** "Director X is a serial failed businessman".
- Where data is missing, ukvet says "insufficient data" instead of guessing.

## 5. Security and misuse

| Risk | Control |
|---|---|
| Prompt injection via company names or filing text (anyone can register a company name) | Treat all API text as untrusted data; delimit it in prompts; injection test cases in evals (metric M6) |
| Using ukvet to harass or profile individuals | No person search; company-only input; director details shown only in the context of a company |
| API key leakage | `.env` git-ignored; Gitleaks in CI; key never sent to the LLM |
| Scraping at scale / abuse of the Companies House API | Respect rate limits; caching; no bulk export feature |

## 6. Review triggers

Revisit this document if ukvet:
- adds a hosted public demo,
- stores any data longer than the cache TTL,
- adds new data sources (Gazette, FCA),
- becomes a paid product.
