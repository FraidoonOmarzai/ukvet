# ADR-006: Sliding-window rate limiter (instead of a token bucket)

- **Status:** Accepted
- **Date:** 8 Oct 2026
- **Supersedes:** the "token bucket" wording in `08-architecture.md` and the Phase 1 roadmap

## Context
Companies House allows 600 requests per 5 minutes (confirmed in the spike). We want a client-side
limiter that can never cause an HTTP 429 from our own traffic.

## Decision
Keep a log of request timestamps and allow a request only if fewer than `max_requests` happened in
the last `window_seconds`. `max_requests` = 600 x 0.9 = 540 (10% safety margin). On HTTP 429 or
low `X-Ratelimit-Remain` headers, pause all callers (bounded by one window).

## Alternatives considered
| Option | Why not |
|---|---|
| Token bucket | Allows a full burst of N plus a refill inside the same window (up to ~2N in one window), so it can exceed the real limit |
| Fixed window counter | Allows 2N across a window boundary |
| No limiter, rely on retries | Burns the budget and slows everything once throttled |

## Consequences
- Guarantees no window ever exceeds the limit (tested with a fake clock, including concurrency).
- Memory is O(limit) timestamps: trivial at 540.
- Requests are served FIFO under contention.