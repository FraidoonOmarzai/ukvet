"""Sliding-window rate limiter.

Companies House allows 600 requests per 5 minutes. A token bucket would allow a full burst plus
a refill inside the same window (up to ~2x the limit), so we keep a log of request timestamps and
only allow a request if fewer than `max_requests` happened in the last `window_seconds`. This can
never exceed the limit in ANY window. See docs/adr/006-sliding-window-rate-limiter.md.
"""

import asyncio
import time
from collections import deque
from collections.abc import Awaitable, Callable

_MIN_SLEEP = 1e-3  # guards against float rounding causing a busy loop


class SlidingWindowRateLimiter:
    def __init__(
        self,
        max_requests: int,
        window_seconds: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if max_requests < 1 or window_seconds <= 0:
            raise ValueError("max_requests must be >= 1 and window_seconds > 0")
        self._max = max_requests
        self._window = float(window_seconds)
        self._clock = clock
        self._sleep = sleep
        self._stamps: deque[float] = deque()
        self._blocked_until = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Wait until a request is allowed, then record it. FIFO under concurrency."""
        async with self._lock:
            while True:
                now = self._clock()
                if now < self._blocked_until:
                    await self._sleep(max(self._blocked_until - now, _MIN_SLEEP))
                    continue
                while self._stamps and now - self._stamps[0] >= self._window:
                    self._stamps.popleft()
                if len(self._stamps) < self._max:
                    self._stamps.append(now)
                    return
                await self._sleep(max(self._stamps[0] + self._window - now, _MIN_SLEEP))

    def block_for(self, seconds: float) -> None:
        """Pause all callers for `seconds` (bounded by one window). Used after an HTTP 429."""
        if seconds <= 0:
            return
        self._blocked_until = max(self._blocked_until, self._clock() + min(seconds, self._window))

    def observe(self, remaining: int | None, reset_in_seconds: float | None) -> None:
        """Second safety check from the `X-Ratelimit-*` headers: if the server says we're nearly
        out (e.g. the key is shared with another process), pause until its window resets.
        """
        if remaining is None:
            return
        threshold = max(3, int(self._max * 0.03))
        if remaining <= threshold:
            self.block_for(reset_in_seconds if reset_in_seconds else 1.0)
