# Phase 1 Roadmap: `ukvet-mcp` (the MCP server)

**Phase goal:** a published, tested MCP server that gives any AI app reliable, citable access to Companies House data.

**Exit criteria:** it's on PyPI, installs with `uvx ukvet-mcp`, works in Claude Desktop, and all tools are tested with fixtures, with coverage at 80% or above.

---

## Before you start: prerequisites

- [ ] The Phase 0 spike is done and `05-data-notes.md` is filled in. Phase 1 depends on three findings from it: the **"no data" status codes**, the **rate limit**, and the **Q8 call cost**. Don't start the code without them.
- [ ] The GitHub repo is live, `main` is protected, and the backlog issues are created.
- [ ] Every step below is **one branch → one PR → merged with green CI**.

---

## Step 1.1: Dependencies and module layout (½ day)

**Add dependencies:**

```bash
uv add --package ukvet-mcp mcp httpx pydantic pydantic-settings
uv add --dev respx pytest-asyncio
```

`respx` mocks httpx calls so tests never hit the real API.

**Create this structure:**

```
packages/ukvet-mcp/src/ukvet_mcp/
├── __main__.py      # entry point: starts the server
├── server.py        # MCP tool definitions
├── config.py        # settings from env
├── errors.py        # typed errors
├── models.py        # output models (with Source)
├── client.py        # Companies House HTTP client
├── rate_limit.py    # token bucket
├── cache.py         # SQLite TTL cache
├── normalise.py     # "no data" handling, company number format
└── filing_codes.py  # filing description codes → plain English
tests/mcp/           # one test file per module
tests/fixtures/ch/   # recorded API responses
```

**Done when:** CI is still green and the empty modules import cleanly.

---

## Step 1.2: Config (½ day)

- Use `pydantic-settings` to read `CH_API_KEY`, the base URL, the timeout, `UKVET_CACHE_TTL_HOURS`, `UKVET_CACHE_PATH`, `UKVET_CACHE_ENABLED`, and the rate-limit values.
- **Fail fast:** if the key is missing, show a clear message ("Set CH_API_KEY — get one at…"), not a stack trace.
- The key must never appear in logs, errors or `repr()`. Use `SecretStr`.

**Tests:** the key is loaded, the missing-key error is clear, defaults are correct, and the secret is masked.


The code uses two important libraries:
- Pydantic — validates the settings and converts values to the expected types.
- Pydantic Settings — loads configuration from environment variables and an optional .env file.

```python
from pydantic import (
    AliasChoices,  # Allows multiple names for one setting
    Field,  # Defines defaults, aliases and validation constraints
    SecretStr,  # Masks sensitive values such as API keys
    ValidationError,  # Lets you run custom validation logic
    field_validator,  # Represents settings that failed validation
)
from pydantic_settings import BaseSettings, SettingsConfigDict
# BaseSettings 	Loads settings from the environment and .env file.
# SettingsConfigDict	Configures how settings are loaded.
```
---

## Step 1.3: Errors and output models (½ day)

This is the foundation for citations.

**Errors (`errors.py`):**

| Error             | Meaning                          |
| ----------------- | -------------------------------- |
| `AuthError`       | 401: bad or missing key          |
| `CompanyNotFound` | The company number doesn't exist |
| `RateLimited`     | 429 after retries were exhausted |
| `UpstreamError`   | 5xx or timeout after retries     |
| `InvalidInput`    | Bad company number format        |

**Important:** "no data" (for example, no charges) is **not an error**. It's a valid empty result.

**Every tool result carries a source (`models.py`):**

```python
class Source(BaseModel):
    endpoint: str  # "/company/01234567/charges"
    url: str  # public Companies House page for the user to verify
    retrieved_at: datetime


class ToolResult(BaseModel):
    found: bool  # False = valid "no data"
    data: ...  # typed per tool
    source: Source
```

Also create typed models per tool (CompanyProfile, Officer, Appointment, PSC, Charge, InsolvencyCase, Filing), including only the fields needed for Q1–Q10. This is also your GDPR data-minimisation rule in code.

**Tests:** models validate against the real fixture shapes.

`Note: ` 
> The code inside model.py defines the output data models for your UK Companies House MCP project. It describes the exact shape of the data your tools return when someone asks questions about a company, its directors, its filings, its charges, or its insolvency history.
> The key idea is: your tools return structured, validated data instead of giving the LLM raw API responses and asking it to figure everything out.
> For example, when someone asks, “Does this company have any outstanding charges?”, your application can return a clear result with the charge count, the relevant records, and a source that lets the user verify the information.

---

## Step 1.4: HTTP client (1 day)

- `httpx.AsyncClient` with Basic auth (the key as username, an empty password) and timeouts.
- **Retries** with exponential backoff and jitter on 429, 502, 503 and 504, with a maximum of 3 attempts. **Never retry** 401, 404 or 400.
- Map status codes to the errors from Step 1.3.
- **Pagination helper:** fetch pages with `items_per_page` and `start_index`, up to a **maximum item cap** so a company with 2,000 filings can't burn your rate limit.
- Log the endpoint, status and latency without the key. Keep personal data out of logs.

**Tests (with respx):** success, 401 → `AuthError`, 404, 429 then success, 429 ×3 → `RateLimited`, 500 → retry, timeout, pagination across 3 pages, and the pagination cap.

---

## Step 1.5: Rate limiter (½ day)

- A token bucket set to the limit **you confirmed in the spike** (documented as 600 per 5 minutes). Aim slightly under, at about 90%, as a safety margin.
- Async-safe, since calls run in parallel from Phase 2.
- Read the rate-limit headers (`X-Ratelimit-Remain`) as a second safety check.

**Tests:** it never exceeds the limit (use a fake clock, not real waiting), it's safe under concurrent calls, and it slows down when headers show low remaining capacity.

---

## Step 1.6: Cache (½ day)

- SQLite, keyed by endpoint plus sorted params, with a TTL defaulting to 24 hours (ADR-004).
- Cache **successful and valid "no data" responses**. Never cache errors.
- It can be disabled with `UKVET_CACHE_ENABLED=false`.
- The cache file is git-ignored.

**Tests:** hit, miss, expiry (fake clock), disabled mode, errors not cached, and "no data" cached.

---

## Step 1.7: Normalisation (½ day)

- **Company numbers:** trim and uppercase them, and zero-pad numeric ones to 8 digits (`1234` → `00001234`). Keep prefixes like `SC`, `NI` and `OC`. Validate the format and raise `InvalidInput` with a helpful message.
- **"No data" mapping:** apply exactly what you observed in the spike. For example, if `/charges` returns 404 for a company with no charges, return `found=False` with an empty list, **not** `CompanyNotFound`.
- **Watch this trap:** a 404 on `/charges` can mean "no charges" _or_ "company doesn't exist". Solve it by confirming the company exists first (its profile, which you cache), so the two cases are never confused.
- **Filing codes:** map the address-change and other key filing `description` codes you found in the spike to plain English.

**Tests:** number formats (valid, invalid, padding, prefixes), each endpoint's no-data case, the 404 disambiguation, and code mapping.

---

## Step 1.8: The MCP tools (2 days)

Define the tools in `server.py` using the MCP SDK's FastMCP. There are **8 tools**:

| Tool                                   | Input                                                            | Answers       |
| -------------------------------------- | ---------------------------------------------------------------- | ------------- |
| `search_company`                       | `query`, `limit` (default 10)                                    | Name → number |
| `get_company_profile`                  | `company_number`                                                 | Q1, Q2, Q4    |
| `get_officers`                         | `company_number`, `include_resigned`                             | Q3, Q9        |
| `get_officer_appointments`             | `officer_id`                                                     | Q8            |
| `get_persons_with_significant_control` | `company_number`                                                 | Q5            |
| `get_charges`                          | `company_number`                                                 | Q6            |
| `get_insolvency`                       | `company_number`                                                 | Q7            |
| `get_filing_history`                   | `company_number`, `since` (optional date), `category` (optional) | Q9            |

**Tool design rules (these matter for the agent in Phase 2):**

- **Tool descriptions are prompts.** Write them carefully: what the tool returns, when to use it, and what `found=false` means. The LLM decides based on these words.
- **Keep outputs small.** Return only the model fields, not the raw API response. Large outputs cost tokens and confuse the model.
- **Keep errors readable by the LLM.** Return messages like "Company 12345678 not found. Check the number or use search_company." Never return a stack trace.
- `get_officers` includes each officer's `officer_id`, so the agent can call `get_officer_appointments` next.
- `get_officer_appointments` returns each linked company's status, if the spike showed the API includes it. It should also carry a **cap on items**, stated in the output ("showing 50 of 120").
- `__main__.py` starts the server over **stdio** (ADR-005).

**Tests per tool:** normal result, no data, company not found, invalid input, and the output schema. Run all of them against fixtures.

---

## Step 1.9: Fixtures (½ day; start it early and use it throughout)

- Write `scripts/record_fixtures.py` to call the real API for your spike test set and save responses to `tests/fixtures/ch/`.
- **Anonymise** personal data before saving: replace names with placeholders like "DIRECTOR A" and remove dates of birth and addresses. Large public plcs can stay as they are (see the legal doc).
- Tests load these fixtures through respx, so **CI never needs an API key or network access**.

**Done when:** `uv run pytest` passes with Wi-Fi turned off.

---

## Step 1.10: Manual testing (½ day)

1. **MCP Inspector:** run `npx @modelcontextprotocol/inspector uv run ukvet-mcp`, then call every tool by hand and check the outputs look right.
2. **Claude Desktop:** add the server to its config, then ask real questions like "Is [company] active? Who are its directors? Any charges?" Check that it picks the right tools and that the answers match the Companies House website.
3. Record a **short GIF** of this for the README. It's your strongest visual proof.
4. Write down anything the model misuses. That usually means a tool description needs fixing.

---

## Step 1.11: Package documentation (½ day)

The `packages/ukvet-mcp/README.md` should include:

- What it is, in one sentence, with the GIF
- Install and configure instructions: `uvx ukvet-mcp` and the Claude Desktop JSON config
- The tool list with a one-line description each
- Configuration (environment variables)
- Limits: rate limit, caching, caps, and the "same person, multiple IDs" limitation
- OGL attribution and the disclaimer

---

## Step 1.12: Release (½ day)

1. Set the package metadata: version `0.1.0`, description, keywords, URLs, classifiers, and the MIT licence.
2. `uv build --package ukvet-mcp`
3. Publish to **TestPyPI** first, then install it on a clean environment and test it.
4. Set up **PyPI Trusted Publishing** through a GitHub Actions workflow triggered by a version tag. This means no API token stored anywhere, which is more secure and good to mention in interviews.
5. Tag `ukvet-mcp-v0.1.0`, and the workflow publishes to PyPI.
6. Verify from a clean machine that `uvx ukvet-mcp` works in Claude Desktop.

---

## Step 1.13: Close the phase (½ day)

- [ ] All Phase 1 issues are closed and the milestone is closed.
- [ ] Coverage is 80% or above, CI is green, and Gitleaks is clean.
- [ ] The decision log is updated (caps chosen, how 404s are handled, the TTL value).
- [ ] The risk register is updated. R1 (rate limit) and R8 (API changes) should now be mitigated.
- [ ] The main README status says "Phase 1 complete — ukvet-mcp on PyPI".
- [ ] Friday demo to AAII: a live Claude Desktop session.
- [ ] Weekly update written.
- [ ] Optional: a short LinkedIn post with the GIF saying you published an MCP server.

---

## Order and dependencies

```
1.1 → 1.2 → 1.3 → 1.4 → 1.5 → 1.6 → 1.7 → 1.8 → 1.10 → 1.11 → 1.12 → 1.13
                    ↑
                   1.9 (fixtures: record right after 1.4, use everywhere)
```

## Honest notes

- **The client, errors and normalisation (Steps 1.3–1.7) are the boring part,** and they're what separates your server from the existing ones. Anyone can wrap 8 endpoints in an afternoon. Correct "no data" handling, rate limiting and citable sources are what the agent's accuracy depends on in Phase 3.
- **Tool descriptions will need rewriting** after the Claude Desktop test. That's normal, so budget time for it.
- **Don't add extra tools** (Gazette, FCA, document downloads). They're v2 items, and adding them now is scope creep.

Once your spike findings are in, send me the "no data" status codes and the Q8 call numbers, and I'll write the complete Phase 1 code step by step, starting with Steps 1.1–1.4.
