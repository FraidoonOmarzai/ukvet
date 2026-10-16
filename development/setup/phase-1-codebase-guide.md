# UKVET MCP — Phase 1 Codebase Guide

This README explains the purpose of each main Python file in the `ukvet-mcp` package, how the files connect, and how a request travels through the application.

## 1. Project overview

The goal of Phase 1 is to build an MCP server that lets an AI assistant access UK Companies House data reliably. The server returns structured information and includes source details so users can verify the results.

Think of the application as a small team: each file has one main responsibility, and together they answer questions such as:

> Who are the current directors of this company?

## 2. How the files work together

```text
AI assistant
    |
    v
server.py
Exposes MCP tools the AI can call
    |
    v
service.py
Coordinates the work needed to answer a question
    |
    +-------------------+
    |                   |
    v                   v
normalise.py         client.py
Checks inputs        Communicates with Companies House
                         |
             +-----------+-----------+
             |           |           |
             v           v           v
          config.py    cache.py   rate_limit.py
          Settings     Saved       Request-speed
                       responses   control
    |
    v
mappers.py
Converts API responses into the fields the application needs
    |
    +--------------------+
    |                    |
    v                    v
models.py           filing_codes.py
Defines result       Explains filing codes in
shapes               plain English
    |
    v
Structured result returned to the AI

errors.py defines meaningful errors used across the request flow.
```

This is a conceptual overview. The exact execution order depends on the tool and whether, for example, the cache already contains the requested response.

## 3. What each file does

### `config.py` — settings manager

**Why we use it:** It keeps application settings in one place instead of hard-coding them throughout the project.

Typical settings include:

- Companies House API key (`CH_API_KEY`)
- API base URL and request timeout
- Cache enabled/disabled
- Cache lifetime and file path
- Rate-limit settings

**How it is used:** Other components read the settings they need. For example, the client needs the API key and timeout, while the cache needs its path and expiry settings.

The Phase 1 plan uses `pydantic-settings` to load environment variables and optionally a `.env` file, and `SecretStr` to help prevent the API key from being exposed accidentally.

### `errors.py` — error dictionary

**Why we use it:** Different failures need different meanings and handling.

| Error | Meaning |
|---|---|
| `AuthError` | The API key is missing or incorrect. |
| `CompanyNotFound` | The requested company could not be found. |
| `RateLimited` | The request limit was reached and retries did not resolve it. |
| `UpstreamError` | Companies House failed or timed out after retries. |
| `InvalidInput` | An input, such as a company number, is invalid. |

**How it is used:** The client can raise these errors when requests fail. Higher layers can handle them and return clear messages.

**Important:** A valid empty result—for example, a company with no charges—is not automatically an error.

### `models.py` — data shapes

**Why we use it:** The API has its own response format. The project needs predictable, validated output for the MCP tools.

Models include types for results such as:

- `CompanyProfile`
- `Officer`
- `Appointment`
- `PSC` (person with significant control)
- `Charge`
- `InsolvencyCase`
- `Filing`
- `Source` and `ToolResult`

A source can record the API endpoint, a public URL for verification, and the retrieval time.

**How it is used:** Mappers prepare the relevant fields, and models define and validate the structure of the result. Keeping output models small also helps avoid returning unnecessary personal information.

### `normalise.py` — input cleaner

**Why we use it:** Inputs can contain extra whitespace, inconsistent letter casing, or incomplete numeric company numbers.

**How it is used:** The application standardises and validates inputs before making a request. For example:

```python
normalise_company_number(" 1234 ")
# "00001234"
```

Company numbers are trimmed and uppercased, and numeric numbers are zero-padded to eight digits. Valid prefixes such as `SC`, `NI`, and `OC` are preserved. The module also contains helpers for officer IDs and filing categories.

Normalisation is also related to “no data” handling. A `404` from a data endpoint can mean that the company has no records of that type, rather than that the company itself does not exist. The Phase 1 plan says to confirm the company exists before treating an endpoint's `404` as a valid empty result.

### `rate_limit.py` — request traffic controller

**Why we use it:** Companies House limits how many requests can be made in a period. Sending requests too quickly can result in `429 Too Many Requests`.

**How it is used:** The client works with the rate limiter before sending requests. The limiter tracks request usage, coordinates concurrent requests, and can react to rate-limit headers from the API.

The Phase 1 plan records a target of 600 requests per five minutes, with a safety margin, based on the earlier project spike.

> Filename note: the Phase 1 roadmap names this file `rate_limit.py`. Make sure the actual filename and imports match; `rate_limt.py` would be a spelling mismatch.

### `cache.py` — short-term memory

**Why we use it:** The same company information may be requested repeatedly. Reusing a saved response can reduce network calls and improve response speed.

**How it is used:** The SQLite cache stores eligible responses under a key based on the endpoint and request parameters. When the same request is made again before the entry expires, the application can reuse the cached response.

Common operations include:

- `get` — retrieve a cached response
- `set` — save a response
- `purge_expired` — remove expired entries
- `clear` — remove cached entries
- `close` — close the cache connection

The Phase 1 design caches successful responses and valid “no data” responses, but not errors. The planned default TTL is 24 hours, and caching can be disabled through configuration.

### `client.py` — Companies House communicator

**Why we use it:** The rest of the application should not need to implement HTTP authentication, timeouts, retries, pagination, and status-code handling separately for each tool.

**How it is used:** The client sends asynchronous HTTP requests to the Companies House API and handles technical details, including:

- API-key authentication
- Request timeouts
- Cache lookups and storage
- Rate limiting
- Retries for selected temporary failures
- Conversion of HTTP failures into application errors
- Reading rate-limit headers
- Pagination with a maximum item cap

For example, when the service requests company officers, the client handles how the request is sent and what happens if the API temporarily fails.

The Phase 1 plan calls for retries on selected temporary statuses such as `429`, `502`, `503`, and `504`, while not retrying `400`, `401`, or `404`.

### `filing_codes.py` — filing-code dictionary

**Why we use it:** Filing history can contain codes or descriptions that are not immediately meaningful to a user.

**How it is used:** The module maps selected filing codes to plain-English descriptions. It includes:

- `FILING_CODES` — filing-code descriptions
- `ADDRESS_CHANGE_CODES` — codes associated with address changes
- `describe_filing()` — returns a readable description
- `is_address_change()` — checks whether a filing is an address-change filing

This helps the application interpret filing records consistently instead of asking the AI to guess what a code means.

### `mappers.py` — API data translator

**Why we use it:** Companies House responses can contain many fields, while the MCP tools only need a smaller, consistent subset.

**How it is used:** Each mapper extracts and prepares the fields needed by the application.

| Mapper | Purpose |
|---|---|
| `map_search_hit` | Maps a company search result |
| `map_profile` | Maps a company profile |
| `map_officer` | Maps an officer record |
| `map_appointment` | Maps an officer appointment |
| `map_psc` | Maps a person with significant control |
| `map_charge` | Maps a company charge |
| `map_insolvency_case` | Maps an insolvency record |
| `map_filing` | Maps a filing-history record |

Helpers such as `_date` and `_obj` support extracting or handling fields.

**Example:** `map_profile()` takes a company-profile response and prepares the relevant fields in the shape expected by the project. This keeps the rest of the application from having to understand every detail of the raw API response.

### `service.py` — operation coordinator

**Why we use it:** The server should not have to repeat all the business logic, mapping, and result construction for every tool.

**How it is used:** The service combines the client and mapping functions to carry out complete operations. It provides methods for:

- `search_company`
- `get_company_profile`
- `get_officers`
- `get_officer_appointments`
- `get_persons_with_significant_control`
- `get_charges`
- `get_insolvency`
- `get_filing_history`

Helpers such as `_mapped`, `_source`, and `_collection` support mapping data, building source information, and handling collections of records.

For example, `get_charges()` coordinates retrieving charge data and preparing the result for the server to return.

### `server.py` — front door for the AI

**Why we use it:** Python functions do not automatically become MCP tools. The server exposes the operations through the Model Context Protocol so compatible AI applications can discover and call them.

**How it is used:** The server sets up FastMCP, defines the eight tools, validates tool inputs, and connects each tool to the service.

The tools are:

1. `search_company`
2. `get_company_profile`
3. `get_officers`
4. `get_officer_appointments`
5. `get_persons_with_significant_control`
6. `get_charges`
7. `get_insolvency`
8. `get_filing_history`

Functions such as `build_service`, `set_service`, and `get_service` help create and access the service. Lifespan handling supports cleanup when the server shuts down, and `_run` provides a shared path for running operations and handling errors.

Tool descriptions are important: they tell the AI what each tool does, when to use it, and what a valid empty result means.

## 4. Example: a request from beginning to end

Suppose you ask:

> Who are the current directors of company 00001234?

A simplified flow is:

1. **`server.py`** receives the AI's call to `get_officers`.
2. **`service.py`** coordinates the operation.
3. **`normalise.py`** standardises and validates the company number.
4. **`client.py`** obtains the data, consulting **`cache.py`** and **`rate_limit.py`** as needed. It uses settings from **`config.py`**.
5. **`errors.py`** provides meaningful error types if something goes wrong.
6. **`mappers.py`** extracts the officer fields the application needs.
7. **`models.py`** defines the expected structure of the result, including source information.
8. **`service.py`** returns the prepared result to **`server.py`**.
9. **`server.py`** returns the result to the AI assistant.

`filing_codes.py` is not needed for every request. It is mainly useful when handling filing history.

The exact execution order can vary. For example, a cache hit may mean no new API request is needed.

## 5. Quick reference

| File | Remember it as… |
|---|---|
| `config.py` | Settings manager |
| `errors.py` | Error dictionary |
| `models.py` | Data-shape definitions |
| `normalise.py` | Input cleaner |
| `rate_limit.py` | Traffic controller |
| `cache.py` | Short-term memory |
| `client.py` | API communicator |
| `filing_codes.py` | Filing-code dictionary |
| `mappers.py` | Data translator |
| `service.py` | Coordinator |
| `server.py` | Front door for the AI |
| `__main__.py` | Server entry point |

## 6. Suggested learning order

If you are learning the codebase, study it in this order:

1. **`models.py` and `errors.py`** — understand result shapes and failure types.
2. **`normalise.py` and `filing_codes.py`** — understand input checks and filing interpretation.
3. **`config.py`, `cache.py`, and `rate_limit.py`** — understand settings and request controls.
4. **`client.py`** — understand API communication.
5. **`mappers.py` and `service.py`** — understand how responses become application results.
6. **`server.py` and `__main__.py`** — understand how the AI calls the tools and how the server starts.

## 7. Main takeaway

`server.py` exposes the tools, `service.py` coordinates the work, and `client.py` communicates with Companies House. The other files make that process more consistent, testable, efficient, and safer.

These responsibilities are separated so each part can be understood and tested independently.
