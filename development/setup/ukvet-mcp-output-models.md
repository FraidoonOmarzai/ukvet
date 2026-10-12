# UKVet MCP Output Models

The output models define the structure of data returned by UKVet MCP tools. They use Pydantic to validate results from Companies House and provide consistent, structured outputs for the LLM.

## Why we use them

- Defines a clear, consistent data contract for MCP tool outputs.
- Validates the structure and types of returned data using Pydantic.
- Uses a generic `ToolResult[T]` wrapper to include data, source information, and notes.
- Includes source metadata so facts can be traced back to Companies House.
- Distinguishes valid results with no matching records from actual errors.
- Computes counts, ages, and other derived values in application logic rather than leaving calculations to the LLM.
- Limits returned fields to those needed to answer the intended questions (Q1–Q10).
- Supports data minimisation by excluding unnecessary personal information.

## Main models

- `Source` — records the API endpoint, verification URL, retrieval timestamp, and whether the result came from the cache.
- `ToolResult[T]` — common wrapper for tool results, containing `found`, `data`, `source`, and optional `notes`.
- `Listing` — shared fields for list results: total records, returned records, and truncation status.
- `SearchHit` and `SearchData` — company search results.
- `CompanyProfile` — company details, filing deadlines, age, SIC codes, and risk indicators.
- `Officer` and `OfficersData` — company officers and active/resigned counts.
- `Appointment` and `AppointmentsData` — an officer's appointments across companies.
- `PersonWithSignificantControl` and `PscData` — persons or entities with significant control.
- `Charge` and `ChargesData` — company charges and their satisfaction status.
- `InsolvencyDate`, `InsolvencyCase`, and `InsolvencyData` — insolvency cases and associated dates.
- `Filing` and `FilingsData` — company filing history.

## Design principles

- **Consistent results:** Every tool result uses the common `ToolResult[T]` structure.
- **Traceability:** Results include source metadata to help users verify information.
- **Explicit missing data:** Optional fields use `None` when information is unavailable.
- **Valid empty results:** `found=False` can represent a successful query with no matching records; it does not automatically mean an error.
- **Deterministic calculations:** Counts, ages, and derived flags are calculated by application code.
- **Pagination awareness:** List models expose whether results are truncated, preventing partial results from being mistaken for complete records.
- **Data minimisation:** Models include only the information required for the intended questions.

## Important details

- `SecretStr` is used for sensitive configuration values; output models should not unnecessarily expose secrets.
- Pydantic validates field types and required values, but does not automatically verify that computed counts, dates, or flags are logically correct.
- The service or tool implementation must populate source metadata and calculate derived values correctly.
- `retrieved_at` records when the application fetched the data, not necessarily when Companies House last updated it.
- Optional fields represent unavailable information; they should not be replaced with assumptions.
- Truncated results must be clearly identified so the LLM does not present partial data as complete.

## Testing

Tests should verify:

- Required fields and data types.
- Handling of missing or optional values.
- Correct calculation of counts, ages, and status flags.
- Correct source metadata and cache indicators.
- Empty results versus actual errors.
- Truncation indicators for partial lists.
- Exclusion of unnecessary personal information.