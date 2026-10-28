"""Shared fixtures: fake clock, mocked Companies House API served from tests/fixtures/ch/."""

import json
from collections.abc import Iterator

import httpx
import pytest
import respx
from ch_support import BASE, FIXTURE_DIR, TODAY, FakeClock, load_fixture, make_client
from ukvet_mcp.client import CompaniesHouseClient
from ukvet_mcp.config import Settings
from ukvet_mcp.service import CompaniesHouseService


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


@pytest.fixture
def client(settings: Settings, clock: FakeClock) -> CompaniesHouseClient:
    return make_client(settings, clock)


@pytest.fixture
def service(client: CompaniesHouseClient) -> CompaniesHouseService:
    return CompaniesHouseService(client, max_items=100, today=lambda: TODAY)


@pytest.fixture(autouse=True)
def _isolate_llm_env(monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest) -> None:
    """Tests must not depend on the developer's real LLM settings (shell variables or .env)."""
    if request.node.get_closest_marker("live"):
        return  # live tests deliberately use the real LLM settings
    from ukvet_agent.llm import LlmSettings

    monkeypatch.setitem(LlmSettings.model_config, "env_file", None)
    for name in (
        "LLM_PROVIDER",
        "LLM_MODEL",
        "LLM_API_KEY",
        "LLM_BASE_URL",
        "LLM_TEMPERATURE",
        "LLM_MAX_TOKENS",
        "LLM_TIMEOUT_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def no_real_tracing() -> Iterator[None]:
    """A developer's .env with LANGFUSE keys must never make a test talk to Langfuse."""
    from ukvet_agent.tracing import NoopTracer, set_tracer

    set_tracer(NoopTracer())
    yield
    set_tracer(None)
