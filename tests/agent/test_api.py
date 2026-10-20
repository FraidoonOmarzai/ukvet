import threading
from collections.abc import AsyncIterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from typing import Any

import pytest
from agent_helpers import FakeWriter, ScriptedTools, draft, make_deps, ok, scripted_company
from fastapi import FastAPI
from fastapi.testclient import TestClient
from ukvet_agent import api
from ukvet_agent.api import create_app
from ukvet_agent.errors import AgentConfigError
from ukvet_agent.graph import Deps
from ukvet_agent.mcp_client import McpToolClient, ToolOutcome
from ukvet_agent.settings import AgentSettings
from ukvet_mcp import server as mcp_module


def settings(**kw: Any) -> AgentSettings:
    return AgentSettings(_env_file=None, **kw)  # type: ignore[call-arg]


def mcp_app(writer: Any = None, **kw: Any) -> FastAPI:
    """App wired to the in-memory MCP server (opened inside the lifespan task)."""

    @asynccontextmanager
    async def factory() -> AsyncIterator[Deps]:
        async with McpToolClient(mcp_module.mcp, timeout_seconds=10) as tools:
            yield make_deps(tools, settings(**kw), writer)

    return create_app(factory)


def tools_app(tools: Any, **kw: Any) -> FastAPI:
    @asynccontextmanager
    async def factory() -> AsyncIterator[Deps]:
        yield make_deps(tools, settings(**kw))

    return create_app(factory)


def post(client: TestClient, company: str) -> Any:
    return client.post("/v1/reports", json={"company": company})


def test_report_ok(mcp_installed: None) -> None:
    with TestClient(mcp_app()) as client:
        res = post(client, "12345678")
    body = res.json()
    assert res.status_code == 200 and body["kind"] == "report"
    assert body["company_name"] == "ACME TEST LTD" and body["risk_level"] == "medium"
    assert body["disclaimer"] and body["attribution"]
    assert "dates" not in body["facts"][0] and "numbers" not in body["facts"][0]
    assert body["facts"][0]["sources"][0]["url"].startswith("https://")


def test_llm_narrative_through_the_api(mcp_installed: None) -> None:
    writer = FakeWriter(
        draft(("ACME TEST LTD is active.", ["Q1.status"]), ("Accounts overdue.", ["Q4.accounts"]))
    )
    with TestClient(mcp_app(writer)) as client:
        body = post(client, "12345678").json()
    assert body["narrative_source"] == "llm" and body["model"] == "fake-model"


def test_ambiguous_name_returns_candidates(mcp_installed: None) -> None:
    with TestClient(mcp_app()) as client:
        res = post(client, "acme")
    body = res.json()
    assert res.status_code == 200 and body["kind"] == "needs_selection"
    assert len(body["candidates"]) == 2


def test_unknown_company_is_404(mcp_installed: None) -> None:
    with TestClient(mcp_app()) as client:
        res = post(client, "99999999")
    assert res.status_code == 404 and res.json()["error"] == "CompanyNotFoundError"


@pytest.mark.parametrize("payload", [{}, {"company": ""}, {"company": "x" * 201}, {"company": 5}])
def test_bad_request_bodies_are_422(payload: dict[str, Any]) -> None:
    with TestClient(tools_app(scripted_company())) as client:
        assert client.post("/v1/reports", json=payload).status_code == 422


def test_whitespace_only_company_is_422_from_the_planner() -> None:
    with TestClient(tools_app(scripted_company())) as client:
        res = post(client, "   ")
    assert res.status_code == 422 and "Enter a company" in res.json()["message"]


def test_search_outage_is_503() -> None:
    tools = scripted_company(search_company=ToolOutcome(ok=False, error="not responding"))
    with TestClient(tools_app(tools)) as client:
        res = post(client, "some name")
    assert res.status_code == 503
    assert res.json()["message"] == "The report could not be generated."


def test_deadline_returns_504() -> None:
    class Slow(ScriptedTools):
        async def call(self, name: str, arguments: dict[str, Any]) -> ToolOutcome:
            import asyncio

            await asyncio.sleep(2)
            return ok({})

    with TestClient(tools_app(Slow({}), request_timeout_seconds=0.1)) as client:
        res = post(client, "12345678")
    assert res.status_code == 504 and res.json()["error"] == "ReportTimeout"


def test_unexpected_errors_do_not_leak_internals() -> None:
    class Broken(ScriptedTools):
        async def call(self, name: str, arguments: dict[str, Any]) -> ToolOutcome:
            raise RuntimeError("secret-api-key-123 at /srv/internal")

    with TestClient(tools_app(Broken({})), raise_server_exceptions=False) as client:
        res = post(client, "12345678")
    assert res.status_code == 500
    assert "secret" not in res.text and "/srv" not in res.text
    assert res.json()["error"] == "InternalError"


@pytest.mark.parametrize(("limit", "expected_max"), [(1, 1), (3, 3)])
def test_concurrency_is_capped(limit: int, expected_max: int) -> None:
    lock = threading.Lock()
    state = {"now": 0, "max": 0}

    class Counting(ScriptedTools):
        async def call(self, name: str, arguments: dict[str, Any]) -> ToolOutcome:
            import asyncio

            if name == "get_company_profile":
                with lock:
                    state["now"] += 1
                    state["max"] = max(state["max"], state["now"])
                await asyncio.sleep(0.15)
                with lock:
                    state["now"] -= 1
            return await super().call(name, arguments)

    tools = Counting(scripted_company().outcomes)
    app = tools_app(tools, max_concurrent_reports=limit)
    with TestClient(app) as client, ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: post(client, "12345678").status_code, range(4)))
    assert results == [200] * 4
    assert state["max"] == expected_max


def test_health_ok_and_degraded() -> None:
    with TestClient(tools_app(scripted_company())) as client:
        body = client.get("/health").json()
    assert body["status"] == "ok" and body["mcp_tools"] == 8
    assert body["narrative"] == "template-only"

    class Dead(ScriptedTools):
        async def ping(self) -> int:
            raise RuntimeError("session closed")

    with TestClient(tools_app(Dead({}))) as client:
        res = client.get("/health")
    assert res.status_code == 503 and res.json()["status"] == "degraded"


def test_health_reports_the_model() -> None:
    @asynccontextmanager
    async def factory() -> AsyncIterator[Deps]:
        yield make_deps(scripted_company(), settings(), FakeWriter())

    with TestClient(create_app(factory)) as client:
        assert client.get("/health").json()["narrative"] == "fake-model"


def test_openapi_documents_the_endpoint() -> None:
    with TestClient(tools_app(scripted_company())) as client:
        schema = client.get("/openapi.json").json()
    assert "/v1/reports" in schema["paths"] and "/health" in schema["paths"]


# ---- production wiring (default_deps) ----------------------------------------------------------


def test_default_wiring_with_in_memory_mcp(
    mcp_installed: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "none")
    monkeypatch.setattr(
        McpToolClient, "stdio", classmethod(lambda cls, **kw: cls(mcp_module.mcp, **kw))
    )
    with TestClient(api.app_factory()) as client:
        assert client.get("/health").json()["status"] == "ok"
        assert post(client, "12345678").status_code == 200


def test_misconfigured_llm_fails_at_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.delenv("LLM_MODEL", raising=False)
    with pytest.raises(AgentConfigError), TestClient(api.app_factory()):
        pass


def test_main_starts_uvicorn(monkeypatch: pytest.MonkeyPatch) -> None:
    import uvicorn
    from ukvet_agent import __main__ as entry

    captured: dict[str, Any] = {}
    monkeypatch.setattr(uvicorn, "run", lambda *a, **kw: captured.update(args=a, **kw))
    monkeypatch.setenv("UKVET_PORT", "9000")
    entry.main()
    assert captured["args"] == ("ukvet_agent.api:app_factory",)
    assert captured["factory"] is True and captured["port"] == 9000
