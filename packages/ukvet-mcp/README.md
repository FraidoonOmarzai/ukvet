# ukvet-mcp

**MCP server for UK Companies House data.** Gives Claude Desktop, Cursor and any other MCP client
reliable, citable access to official company records: status, directors, controllers, charges,
insolvency and filing history.

Part of [ukvet](https://github.com/fraidoonomarzai/ukvet) (an AI due-diligence agent with an
evaluation benchmark). This package is the data layer and works on its own.

![ukvet-mcp demo](https://raw.githubusercontent.com/FraidoonOmarzai/ukvet/main/docs/ukvet-demo.gif)

## Why another Companies House server?

It focuses on correctness, not just endpoint coverage:

- **Every result is citable:** `{found, data, source, notes}`, where `source.url` is the public
  Companies House page and `retrieved_at` says how fresh it is.
- **"No data" is not an error.** A company with no charges returns `found: false`, and a 404 on a
  sub-endpoint is checked against the company profile so "no insolvency record" is never reported
  for a company that doesn't exist.
- **Computed facts, not LLM arithmetic:** company age, status counts, outstanding-charge counts.
- **Data minimisation:** no dates of birth, home addresses, nationality or occupation (UK GDPR).
- **Safe by construction:** sliding-window rate limiter (never exceeds the 600/5 min limit),
  retries with backoff, hard pagination caps, short-lived cache, API key never logged.

## Install

You need a free Companies House API key: create an application at
<https://developer.company-information.service.gov.uk/> and add a **REST** key for the **live**
environment.

```bash
CH_API_KEY=your-key uvx ukvet-mcp --check     # verifies the key, prints OK
```

### Claude Desktop

Edit `claude_desktop_config.json` (macOS: `~/Library/Application Support/Claude/`, Windows:
`%APPDATA%\Claude\`), then restart Claude Desktop:

```json
{
  "mcpServers": {
    "ukvet": {
      "command": "uvx",
      "args": ["ukvet-mcp"],
      "env": { "CH_API_KEY": "your-key" }
    }
  }
}
```

Try: *"Is Tesco PLC active, who are its directors, and does it have any outstanding charges?"*

**Claude setup guide:** `ukvet\development\setup\claude-desktop-ukvet-setup.md`

### Cursor and other clients

Same command and environment variable: `uvx ukvet-mcp`, transport `stdio`.

## Tools

| Tool | Answers |
|---|---|
| `search_company` | Find a company number from a name |
| `get_company_profile` | Status, age, overdue accounts / confirmation statement, flags |
| `get_officers` | Current (or all) directors and secretaries, with appointment dates |
| `get_officer_appointments` | A director's other companies and their statuses |
| `get_persons_with_significant_control` | Who owns or controls the company |
| `get_charges` | Secured debts, with outstanding / satisfied counts |
| `get_insolvency` | Liquidation, administration, CVA, receivership cases |
| `get_filing_history` | Filings with plain-English descriptions; address changes flagged |

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `CH_API_KEY` | (required) | Companies House REST API key |
| `UKVET_CACHE_ENABLED` | `true` | Cache responses locally |
| `UKVET_CACHE_TTL_HOURS` | `24` | Cache lifetime |
| `UKVET_CACHE_PATH` | `~/.cache/ukvet/ch_cache.sqlite` | Cache file |
| `UKVET_RATE_LIMIT_REQUESTS` / `_WINDOW_SECONDS` / `_SAFETY` | `600` / `300` / `0.9` | Client-side limit (90% of the API limit) |
| `UKVET_MAX_ITEMS` | `100` | Per-tool cap on records fetched |
| `UKVET_MAX_ATTEMPTS` | `3` | Attempts per request (429/5xx/timeouts retried) |
| `UKVET_HTTP_TIMEOUT_SECONDS` | `20` | Request timeout |
| `UKVET_LOG_LEVEL` | `WARNING` | Logs go to stderr |

## Limits (read these)

- Data can be up to 24 hours old (cache); `source.retrieved_at` shows the real timestamp.
- Results are capped (`UKVET_MAX_ITEMS`); truncation is always reported in `notes`.
- The same real person can appear under several officer IDs, so director track records can be
  incomplete. Treat them as a lower bound.
- PSC `found: false` does not prove a company has no owner (it may be exempt or have filed a
  statement, which this server does not cover).
- Only Companies House API data: no Gazette, FCA register or filed-accounts contents.

## Attribution and disclaimer

Contains public sector information licensed under the
[Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/)
(Companies House). Not affiliated with or endorsed by Companies House. Informational only; not
legal, financial or credit advice.

MIT licence.
