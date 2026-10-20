"""Shared Phase 1 test support (importable as `ch_support`; `conftest` names are ambiguous)."""

import json
from datetime import date
from pathlib import Path
from typing import Any

from ukvet_mcp.cache import ResponseCache
from ukvet_mcp.client import CompaniesHouseClient
from ukvet_mcp.config import Settings
from ukvet_mcp.rate_limit import SlidingWindowRateLimiter

BASE = "https://api.company-information.service.gov.uk"
FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "ch"
TODAY = date(2026, 3, 4)

EXPECTED_TOOLS = {
    "search_company",
    "get_company_profile",
    "get_officers",
    "get_officer_appointments",
    "get_persons_with_significant_control",
    "get_charges",
    "get_insolvency",
    "get_filing_history",
}


class FakeClock:
    """Deterministic time: `sleep` advances the clock instantly and records the delay."""

    def __init__(self, start: float = 1_000.0) -> None:
        self.t = start
        self.sleeps: list[float] = []

    def now(self) -> float:
        return self.t

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.t += seconds


def load_fixture(name: str) -> dict[str, Any]:
    """Return the `body` of a fixture file."""
    data = json.loads((FIXTURE_DIR / f"{name}.json").read_text())
    return data["body"]  # type: ignore[no-any-return]


def make_client(
    settings: Settings, clock: FakeClock, *, cache: ResponseCache | None = None
) -> CompaniesHouseClient:
    return CompaniesHouseClient(
        settings,
        cache=cache or ResponseCache(":memory:", 3600, enabled=False),
        limiter=SlidingWindowRateLimiter(10_000, 300, clock=clock.now, sleep=clock.sleep),
        sleep=clock.sleep,
        wall_clock=clock.now,
        jitter=lambda: 0.5,  # factor 1.0 -> backoff is exactly 0.5 * 2**attempt
    )
