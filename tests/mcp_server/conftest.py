"""Shared fixtures: fake clock, mocked Companies House API served from tests/fixtures/ch/."""

import json
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from ukvet_mcp.cache import ResponseCache
from ukvet_mcp.client import CompaniesHouseClient
from ukvet_mcp.config import Settings
from ukvet_mcp.rate_limit import SlidingWindowRateLimiter
from ukvet_mcp.service import CompaniesHouseService

BASE = "https://api.company-information.service.gov.uk"
FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "ch"
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


@pytest.fixture
def settings() -> Settings:
    return Settings(api_key="test-key", cache_enabled=False, _env_file=None)  # type: ignore[call-arg]


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def router() -> Iterator[respx.MockRouter]:
    """Empty mocked Companies House API; tests register their own routes."""
    with respx.mock(base_url=BASE, assert_all_called=False, assert_all_mocked=True) as r:
        yield r


@pytest.fixture
def ch_api(router: respx.MockRouter) -> respx.MockRouter:
    """Mocked API serving every fixture file; unknown company/officer paths return 404."""
    for file in sorted(FIXTURE_DIR.glob("*.json")):
        data = json.loads(file.read_text())
        path = data["request"]["path"]
        if path == "/search/companies":
            continue
        if data["status"] == 200:
            router.get(path).mock(return_value=httpx.Response(200, json=data["body"]))
        else:
            router.get(path).mock(return_value=httpx.Response(data["status"]))

    search_body = load_fixture("search__acme")

    def search(request: httpx.Request) -> httpx.Response:
        if "acme" in request.url.params.get("q", "").lower():
            return httpx.Response(200, json=search_body)
        return httpx.Response(200, json={"total_results": 0, "items": []})

    router.get("/search/companies").mock(side_effect=search)
    router.get(path__regex=r"^/(company|officers)/.*").mock(return_value=httpx.Response(404))
    return router


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


@pytest.fixture
def client(settings: Settings, clock: FakeClock) -> CompaniesHouseClient:
    return make_client(settings, clock)


@pytest.fixture
def service(client: CompaniesHouseClient) -> CompaniesHouseService:
    return CompaniesHouseService(client, max_items=100, today=lambda: TODAY)
