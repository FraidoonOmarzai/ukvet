"""Companies House HTTP client.

Responsibilities: auth, rate limiting, retries with backoff, caching, pagination with a hard
item cap, and mapping HTTP statuses to typed errors.

Status handling:
  200            -> data (cached)
  404            -> returned as status 404 (cached); callers decide what "not found" means,
                    because for some endpoints 404 is a valid "no data" answer
  401 / 403      -> AuthError (never retried)
  400            -> InvalidInput (never retried)
  429, 5xx       -> retried with exponential backoff + jitter; then RateLimited / UpstreamError
  timeouts       -> retried; then UpstreamError
Nothing in logs includes the API key, response bodies or query text.
"""

import asyncio
import contextlib
import logging
import random
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx

from ukvet_mcp import __version__
from ukvet_mcp.cache import ResponseCache, make_key
from ukvet_mcp.config import Settings
from ukvet_mcp.errors import AuthError, InvalidInput, RateLimited, UpstreamError
from ukvet_mcp.rate_limit import SlidingWindowRateLimiter

log = logging.getLogger("ukvet_mcp.client")

RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})
MAX_PAGE_SIZE = 100
_MAX_BACKOFF = 8.0
_MAX_RETRY_AFTER = 30.0


@dataclass(frozen=True)
class ApiResponse:
    status: int  # 200 or 404 (everything else raises)
    data: dict[str, Any] | None
    retrieved_at: datetime
    from_cache: bool


@dataclass
class Page:
    """Result of a paginated fetch."""

    items: list[dict[str, Any]]
    total: int | None
    truncated: bool
    retrieved_at: datetime
    from_cache: bool
    not_found: bool = False
    stopped_by_predicate: bool = False
    first_page: dict[str, Any] = field(default_factory=dict)


def _utc(ts: float) -> datetime:
    return datetime.fromtimestamp(ts, tz=UTC)


class CompaniesHouseClient:
    def __init__(
        self,
        settings: Settings,
        *,
        http: httpx.AsyncClient | None = None,
        cache: ResponseCache | None = None,
        limiter: SlidingWindowRateLimiter | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        wall_clock: Callable[[], float] = time.time,
        jitter: Callable[[], float] = random.random,
    ) -> None:
        self._settings = settings
        self._http = http or httpx.AsyncClient(
            base_url=settings.base_url,
            auth=(settings.api_key.get_secret_value(), ""),
            timeout=settings.timeout_seconds,
            headers={
                "Accept": "application/json",
                "User-Agent": f"ukvet-mcp/{__version__}",
            },
        )
        self._cache = cache or ResponseCache(
            settings.cache_path,
            settings.cache_ttl_seconds,
            enabled=settings.cache_enabled,
        )
        # Don't let expired personal data linger on disk between runs (docs/06-legal-and-ethics.md).
        self._cache.purge_expired()
        self._limiter = limiter or SlidingWindowRateLimiter(
            settings.effective_rate_limit, settings.rate_limit_window_seconds
        )
        self._sleep = sleep
        self._wall_clock = wall_clock
        self._jitter = jitter

    async def aclose(self) -> None:
        await self._http.aclose()
        self._cache.close()

    # ---- single request ---------------------------------------------------------------------

    async def get(
        self, path: str, params: Mapping[str, Any] | None = None
    ) -> ApiResponse:
        key = make_key(path, params)
        cached = self._cache.get(key)
        if cached is not None:
            log.debug("GET %s -> %s (cache hit)", path, cached.status)
            return ApiResponse(cached.status, cached.body, _utc(cached.stored_at), True)

        status, body = await self._fetch(path, params)
        retrieved_at = self._wall_clock()
        self._cache.set(key, status, body)
        return ApiResponse(status, body, _utc(retrieved_at), False)

    async def _fetch(
        self, path: str, params: Mapping[str, Any] | None
    ) -> tuple[int, dict[str, Any] | None]:
        attempts = self._settings.max_attempts
        last_status: int | None = None
        for attempt in range(attempts):
            await self._limiter.acquire()
            started = time.perf_counter()
            try:
                resp = await self._http.get(
                    path, params=dict(params) if params else None
                )
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_status = None
                log.warning(
                    "GET %s failed: %s (attempt %d/%d)",
                    path,
                    type(exc).__name__,
                    attempt + 1,
                    attempts,
                )
                if attempt + 1 < attempts:
                    await self._backoff(attempt, None)
                    continue
                raise UpstreamError(
                    "Could not reach Companies House (network error or timeout). Try again shortly."
                ) from None

            elapsed_ms = (time.perf_counter() - started) * 1000
            status = resp.status_code
            log.info("GET %s -> %s (%.0f ms)", path, status, elapsed_ms)

            if status == 200:
                self._observe_headers(resp)
                try:
                    body = resp.json()
                except ValueError:
                    raise UpstreamError(
                        "Companies House returned a response that is not valid JSON."
                    ) from None
                if not isinstance(body, dict):
                    raise UpstreamError(
                        "Companies House returned an unexpected response shape."
                    )
                return 200, body
            if status == 404:
                self._observe_headers(resp)
                return 404, None
            if status in (401, 403):
                raise AuthError(status)
            if status == 400:
                raise InvalidInput(
                    "Companies House rejected the request parameters (HTTP 400)."
                )
            if status in RETRYABLE_STATUSES:
                last_status = status
                retry_after = self._retry_after(resp)
                if status == 429:
                    self._limiter.block_for(retry_after if retry_after else 5.0)
                if attempt + 1 < attempts:
                    await self._backoff(attempt, retry_after)
                    continue
                break
            raise UpstreamError(
                f"Companies House returned an unexpected HTTP {status}."
            )

        if last_status == 429:
            raise RateLimited()
        raise UpstreamError(
            f"Companies House is not responding correctly (HTTP {last_status}). Try again shortly."
        )

    async def _backoff(self, attempt: int, retry_after: float | None) -> None:
        if retry_after is not None:
            delay = min(retry_after, _MAX_RETRY_AFTER)
        else:
            delay = min(_MAX_BACKOFF, 0.5 * (2**attempt)) * (0.5 + self._jitter())
        await self._sleep(delay)

    @staticmethod
    def _retry_after(resp: httpx.Response) -> float | None:
        raw = resp.headers.get("Retry-After")
        if raw is None:
            return None
        try:
            return max(0.0, float(raw))
        except ValueError:
            return None

    def _observe_headers(self, resp: httpx.Response) -> None:
        try:
            remaining = int(resp.headers["X-Ratelimit-Remain"])
        except (KeyError, ValueError):
            return
        reset_in: float | None = None
        with contextlib.suppress(KeyError, ValueError):
            reset_in = max(
                0.0, float(resp.headers["X-Ratelimit-Reset"]) - self._wall_clock()
            )
        self._limiter.observe(remaining, reset_in)

    # ---- pagination ---------------------------------------------------------------------------

    async def get_paginated(
        self,
        path: str,
        *,
        items_key: str,
        total_key: str,
        max_items: int,
        params: Mapping[str, Any] | None = None,
        stop_after: Callable[[list[dict[str, Any]]], bool] | None = None,
    ) -> Page:
        """Fetch pages until everything is read, `max_items` is reached, or `stop_after(page)`.

        `max_items` is a hard cap so a company with thousands of filings cannot burn the rate
        limit. If the first page is a 404, returns a Page with `not_found=True` and no items.
        """
        per_page = min(MAX_PAGE_SIZE, max_items)
        items: list[dict[str, Any]] = []
        total: int | None = None
        first: ApiResponse | None = None
        stopped = False

        while True:
            query = dict(params or {})
            query["items_per_page"] = per_page
            query["start_index"] = len(items)
            resp = await self.get(path, query)
            if first is None:
                first = resp
                if resp.status == 404:
                    return Page(
                        [], 0, False, resp.retrieved_at, resp.from_cache, not_found=True
                    )
            body = resp.data or {}
            page_items = [i for i in body.get(items_key, []) if isinstance(i, dict)]
            raw_total = body.get(total_key)
            if isinstance(raw_total, int):
                total = raw_total
            items.extend(page_items)

            if stop_after is not None and page_items and stop_after(page_items):
                stopped = True
                break
            if len(items) >= max_items:
                break
            if not page_items or len(page_items) < per_page:
                break
            if total is not None and len(items) >= total:
                break

        truncated = False
        if len(items) > max_items:
            items = items[:max_items]
        if total is not None:
            truncated = total > len(items)
        elif len(items) >= max_items:
            truncated = True

        assert first is not None
        return Page(
            items=items,
            total=total,
            truncated=truncated,
            retrieved_at=first.retrieved_at,
            from_cache=first.from_cache,
            stopped_by_predicate=stopped,
            first_page=first.data or {},
        )


if __name__ == "__main__":
    import asyncio

    from ukvet_mcp.config import load_settings

    async def _demo() -> None:
        client = CompaniesHouseClient(load_settings())
        try:
            resp = await client.get("/company/00445790")
            print("status:", resp.status, "| from_cache:", resp.from_cache)
            print("name:", (resp.data or {}).get("company_name"))

            page = await client.get_paginated(
                "/company/00445790/officers",
                items_key="items",
                total_key="total_results",
                max_items=5,
            )
            print(
                "officers fetched:",
                len(page.items),
                "of",
                page.total,
                "| truncated:",
                page.truncated,
            )
        finally:
            await client.aclose()

    logging.basicConfig(level=logging.INFO)
    asyncio.run(_demo())
