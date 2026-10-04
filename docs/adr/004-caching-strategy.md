# ADR-004: Caching strategy

- **Status:** Accepted (TTL value to confirm after spike)
- **Date:** 04 Oct 2026

## Context
The rate limit (600 requests / 5 min) and repeated eval runs would otherwise hit the API heavily. Company data changes slowly. Personal data must not be kept long-term (see `06-legal-and-ethics.md`).

## Decision
- Cache API responses in **SQLite** keyed by endpoint + parameters, with a **TTL (default 24 hours)**.
- Separate **recorded fixtures** (committed, anonymised or large-public-company only) for unit tests and CI evals — no live API calls in CI.
- Cache is optional and configurable (can be disabled).

## Alternatives considered
| Option | Why not |
|---|---|
| In-memory cache only | Lost on restart; doesn't help eval runs |
| Redis | Extra service to run; unnecessary at this scale |
| No cache | Rate limits and slow evals |

## Consequences
- Fast, repeatable evals and tests.
- Reports may be up to 24 h stale — stated in the disclaimer via `retrieved_at`.
- Cache file must be git-ignored.
