"""End-to-end through the real MCP protocol (in-memory client <-> server), fixtures behind it.

Note: the MCP client is opened inside each test (not in an async-generator fixture) because it
uses anyio task groups, which must be entered and exited in the same task.
"""

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any

import pytest
from conftest import EXPECTED_TOOLS
from mcp.client import Client
from ukvet_mcp import server
from ukvet_mcp.service import CompaniesHouseService

pytestmark = pytest.mark.usefixtures("ch_api")

Connect = Callable[[], AbstractAsyncContextManager[Client]]


@pytest.fixture
def connect(service: CompaniesHouseService) -> Connect:
    @asynccontextmanager
    async def _connect() -> AsyncIterator[Client]:
        server.set_service(service)
        try:
            async with Client(server.mcp) as c:
                yield c
        finally:
            server.set_service(None)

    return _connect


async def call(c: Client, name: str, **args: Any) -> Any:
    return await c.call_tool(name, args)


async def test_exactly_the_eight_documented_tools_are_exposed(connect: Connect) -> None:
    async with connect() as c:
        tools = (await c.list_tools()).tools
    assert {t.name for t in tools} == EXPECTED_TOOLS


async def test_every_tool_has_a_real_description_and_output_schema(connect: Connect) -> None:
    async with connect() as c:
        tools = (await c.list_tools()).tools
    for tool in tools:
        assert tool.description is not None
        assert len(tool.description) > 60, f"{tool.name}: description too thin to guide an LLM"
        assert tool.output_schema is not None, f"{tool.name}: no structured output schema"


async def test_server_instructions_warn_about_untrusted_text(connect: Connect) -> None:
    async with connect() as c:
        instructions = c.instructions
    assert instructions is not None
    assert "UNTRUSTED" in instructions
    assert "found=false" in instructions


async def test_profile_returns_structured_result_with_source(connect: Connect) -> None:
    async with connect() as c:
        res = await call(c, "get_company_profile", company_number="12345678")
    assert res.is_error is False
    body = res.structured_content
    assert body["found"] is True
    assert body["data"]["company_name"] == "ACME TEST LTD"
    assert body["source"]["url"].startswith(
        "https://find-and-update.company-information.service.gov.uk/"
    )
    assert body["source"]["retrieved_at"]


async def test_no_data_is_a_normal_result_not_an_error(connect: Connect) -> None:
    async with connect() as c:
        res = await call(c, "get_insolvency", company_number="12345678")
    assert res.is_error is False
    assert res.structured_content["found"] is False
    assert res.structured_content["notes"]


async def test_not_found_error_is_readable_and_actionable(connect: Connect) -> None:
    async with connect() as c:
        res = await call(c, "get_company_profile", company_number="404")
    assert res.is_error is True
    text = res.content[0].text
    assert "00000404" in text
    assert "search_company" in text
    assert "Traceback" not in text


async def test_invalid_number_error_is_readable(connect: Connect) -> None:
    async with connect() as c:
        res = await call(c, "get_officers", company_number="not-a-number")
    assert res.is_error is True
    assert "not a valid company number" in res.content[0].text


async def test_out_of_range_argument_is_rejected(connect: Connect) -> None:
    async with connect() as c:
        res = await call(c, "search_company", query="acme", limit=999)
    assert res.is_error is True


async def test_unexpected_exceptions_do_not_leak_internals(
    connect: Connect, service: CompaniesHouseService, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def boom(*_a: Any, **_k: Any) -> None:
        raise RuntimeError("secret internals: /home/user/.env key=abc")

    monkeypatch.setattr(service, "get_charges", boom)
    async with connect() as c:
        res = await call(c, "get_charges", company_number="12345678")
    assert res.is_error is True
    assert "secret internals" not in res.content[0].text
    assert "abc" not in res.content[0].text


async def test_all_tools_work_end_to_end(connect: Connect) -> None:
    calls: list[tuple[str, dict[str, Any]]] = [
        ("search_company", {"query": "acme"}),
        ("get_company_profile", {"company_number": "12345678"}),
        ("get_officers", {"company_number": "12345678", "include_resigned": True}),
        (
            "get_officer_appointments",
            {"officer_id": "OFFICERIDA1", "exclude_company_number": "12345678"},
        ),
        ("get_persons_with_significant_control", {"company_number": "12345678"}),
        ("get_charges", {"company_number": "12345678"}),
        ("get_insolvency", {"company_number": "87654321"}),
        (
            "get_filing_history",
            {"company_number": "12345678", "since": "2025-01-01", "category": "address"},
        ),
    ]
    async with connect() as c:
        for name, args in calls:
            res = await call(c, name, **args)
            assert res.is_error is False, f"{name}: {res.content[0].text}"
            assert res.structured_content["found"] is True, name
            assert res.structured_content["source"]["endpoint"], name


async def test_q8_flow_officers_then_appointments(connect: Connect) -> None:
    """The chain an agent follows for Q8: officers -> officer_id -> appointments."""
    async with connect() as c:
        officers = (await call(c, "get_officers", company_number="12345678")).structured_content
        officer_id = officers["data"]["items"][0]["officer_id"]
        res = await call(
            c,
            "get_officer_appointments",
            officer_id=officer_id,
            exclude_company_number="12345678",
        )
    assert res.structured_content["data"]["status_counts"] == {
        "active": 1,
        "dissolved": 1,
        "liquidation": 1,
    }
