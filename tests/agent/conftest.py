"""Agent test fixtures: an in-memory ukvet-mcp server backed by the recorded fixtures.

The MCP client uses anyio task groups, so it is opened INSIDE the test (via `open_tools`), never
in a fixture.
"""

from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any

import pytest
from ukvet_agent.mcp_client import McpToolClient
from ukvet_agent.settings import AgentSettings
from ukvet_mcp import server as mcp_module
from ukvet_mcp.service import CompaniesHouseService


@pytest.fixture
def mcp_installed(ch_api: Any, service: CompaniesHouseService) -> Iterator[None]:
    """Install the fixture-backed service into the in-memory MCP server."""
    mcp_module.set_service(service)
    yield
    mcp_module.set_service(None)


@pytest.fixture
def open_tools(mcp_installed: None) -> Callable[[], AbstractAsyncContextManager[McpToolClient]]:
    @asynccontextmanager
    async def _open() -> AsyncIterator[McpToolClient]:
        async with McpToolClient(mcp_module.mcp, timeout_seconds=10) as tools:
            yield tools

    return _open


@pytest.fixture
def agent_settings() -> AgentSettings:
    return AgentSettings(_env_file=None)  # type: ignore[call-arg]
