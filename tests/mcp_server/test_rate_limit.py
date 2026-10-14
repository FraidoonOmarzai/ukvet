import asyncio

import pytest
from conftest import FakeClock
from ukvet_mcp.rate_limit import SlidingWindowRateLimiter


def limiter(clock: FakeClock, n: int = 10, window: float = 100.0) -> SlidingWindowRateLimiter:
    return SlidingWindowRateLimiter(n, window, clock=clock.now, sleep=clock.sleep)


async def test_under_limit_never_waits(clock: FakeClock) -> None:
    lim = limiter(clock)
    for _ in range(10):
        await lim.acquire()
    assert clock.sleeps == []


async def test_waits_when_limit_reached(clock: FakeClock) -> None:
    lim = limiter(clock)
    start = clock.now()
    for _ in range(11):
        await lim.acquire()
    assert clock.sleeps  # 11th request had to wait
    assert clock.now() - start >= 100.0 - 1e-6  # ...until the first request left the window


async def test_never_exceeds_limit_in_any_window(clock: FakeClock) -> None:
    lim = limiter(clock, n=10, window=100.0)
    grants: list[float] = []
    for _ in range(75):
        await lim.acquire()
        grants.append(clock.now())
    for i, t in enumerate(grants):
        in_window = [g for g in grants[: i + 1] if t - g < 100.0]
        assert len(in_window) <= 10


async def test_safe_under_concurrency(clock: FakeClock) -> None:
    lim = limiter(clock, n=5, window=60.0)
    grants: list[float] = []

    async def worker() -> None:
        await lim.acquire()
        grants.append(clock.now())

    await asyncio.gather(*(worker() for _ in range(23)))
    assert len(grants) == 23
    for t in grants:
        assert len([g for g in grants if t - 60.0 < g <= t]) <= 5


async def test_block_for_pauses_everyone(clock: FakeClock) -> None:
    lim = limiter(clock)
    lim.block_for(30)
    start = clock.now()
    await lim.acquire()
    assert clock.now() - start >= 30


async def test_block_for_is_bounded_by_one_window(clock: FakeClock) -> None:
    lim = limiter(clock, window=100.0)
    lim.block_for(10_000)
    start = clock.now()
    await lim.acquire()
    assert clock.now() - start <= 100.0 + 1e-6


async def test_observe_slows_down_when_server_says_nearly_out(clock: FakeClock) -> None:
    lim = limiter(clock, n=600, window=300.0)
    lim.observe(remaining=2, reset_in_seconds=45.0)
    start = clock.now()
    await lim.acquire()
    assert clock.now() - start >= 45.0


async def test_observe_ignores_healthy_or_missing_headers(clock: FakeClock) -> None:
    lim = limiter(clock, n=600, window=300.0)
    lim.observe(remaining=500, reset_in_seconds=45.0)
    lim.observe(remaining=None, reset_in_seconds=None)
    await lim.acquire()
    assert clock.sleeps == []


def test_invalid_config_rejected() -> None:
    with pytest.raises(ValueError):
        SlidingWindowRateLimiter(0, 10)
    with pytest.raises(ValueError):
        SlidingWindowRateLimiter(1, 0)
