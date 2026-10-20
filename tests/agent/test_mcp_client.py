from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

from ukvet_agent.mcp_client import McpToolClient, is_retryable, stdio_params
from ukvet_mcp import server as mcp_module


def test_is_retryable() -> None:
    assert is_retryable("Companies House is not responding. Try again.")
    assert is_retryable("Rate limit exceeded")
    assert not is_retryable("Company 123 was not found")


def test_stdio_params_pass_environment() -> None:
    params = stdio_params({"CH_API_KEY": "abc"})
    assert params.args == ["-m", "ukvet_mcp"]
    assert params.env is not None
    assert dict(params.env).get("CH_API_KEY") == "abc"


async def test_call_before_open_never_raises() -> None:
    outcome = await McpToolClient(mcp_module.mcp).call("get_charges", {})
    assert not outcome.ok and outcome.retryable


async def test_success_maps_found_data_source(
    open_tools: Callable[[], AbstractAsyncContextManager[McpToolClient]],
) -> None:
    async with open_tools() as tools:
        out = await tools.call("get_company_profile", {"company_number": "12345678"})
        assert out.ok and out.found
        assert out.data["company_name"] == "ACME TEST LTD"
        assert out.source is not None and out.source["endpoint"]


async def test_no_data_is_ok_but_not_found(
    open_tools: Callable[[], AbstractAsyncContextManager[McpToolClient]],
) -> None:
    async with open_tools() as tools:
        out = await tools.call("get_insolvency", {"company_number": "12345678"})
        assert out.ok and not out.found


async def test_tool_error_becomes_failed_outcome(
    open_tools: Callable[[], AbstractAsyncContextManager[McpToolClient]],
) -> None:
    async with open_tools() as tools:
        out = await tools.call("get_company_profile", {"company_number": "99999999"})
        assert not out.ok and "not found" in (out.error or "").lower() and not out.retryable


async def test_bad_arguments_never_raise(
    open_tools: Callable[[], AbstractAsyncContextManager[McpToolClient]],
) -> None:
    async with open_tools() as tools:
        out = await tools.call("get_company_profile", {"wrong": 1})
        assert not out.ok
        out = await tools.call("no_such_tool", {})
        assert not out.ok


async def test_ping_counts_tools(
    open_tools: Callable[[], AbstractAsyncContextManager[McpToolClient]],
) -> None:
    async with open_tools() as tools:
        assert await tools.ping() == 8
