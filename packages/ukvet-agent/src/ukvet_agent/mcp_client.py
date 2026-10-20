"""Typed access to the ukvet-mcp tools.

`McpToolClient.call` NEVER raises: every outcome (success, "no data", tool error, timeout,
transport failure) comes back as a `ToolOutcome`, so one failing endpoint becomes a *gap* in the
report instead of a crash.

The MCP client uses anyio task groups, so enter and exit it in the same task (an `async with`
block or a FastAPI lifespan), never across pytest fixtures or separate tasks.
"""

import asyncio
import os
import sys
from contextlib import AsyncExitStack
from types import TracebackType
from typing import Any, Protocol

from mcp.client import Client
from mcp.client.stdio import StdioServerParameters
from pydantic import BaseModel, Field

_RETRYABLE_HINTS = (
    "rate limit",
    "not responding",
    "network error or timeout",
    "try again",
    "timed out",
    "transport error",
)


class ToolOutcome(BaseModel):
    ok: bool
    found: bool = False
    data: dict[str, Any] = Field(default_factory=dict)
    source: dict[str, Any] | None = None
    notes: list[str] = Field(default_factory=list)
    error: str | None = None
    retryable: bool = False


class ToolClient(Protocol):
    async def call(self, name: str, arguments: dict[str, Any]) -> ToolOutcome: ...

    async def ping(self) -> int:
        """Return the number of tools the server exposes (raises if the session is dead)."""
        ...


def is_retryable(message: str) -> bool:
    lowered = message.lower()
    return any(hint in lowered for hint in _RETRYABLE_HINTS)


def stdio_params(extra_env: dict[str, str] | None = None) -> StdioServerParameters:
    """Launch `python -m ukvet_mcp` with the current environment (CH_API_KEY etc.)."""
    env = {**os.environ, **(extra_env or {})}
    return StdioServerParameters(command=sys.executable, args=["-m", "ukvet_mcp"], env=env)


class McpToolClient:
    def __init__(self, target: Any, *, timeout_seconds: float = 20.0) -> None:
        self._target = target  # StdioServerParameters, or an in-process MCPServer (tests)
        self._timeout = timeout_seconds
        self._stack: AsyncExitStack | None = None
        self._client: Client | None = None

    @classmethod
    def stdio(
        cls, *, timeout_seconds: float = 20.0, extra_env: dict[str, str] | None = None
    ) -> "McpToolClient":
        return cls(stdio_params(extra_env), timeout_seconds=timeout_seconds)

    async def __aenter__(self) -> "McpToolClient":
        self._stack = AsyncExitStack()
        try:
            self._client = await self._stack.enter_async_context(Client(self._target))
        except BaseException:
            await self._stack.aclose()
            raise
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._stack is not None:
            await self._stack.aclose()
        self._client = None

    async def ping(self) -> int:
        if self._client is None:
            raise RuntimeError("MCP session is not open")
        async with asyncio.timeout(self._timeout):
            return len((await self._client.list_tools()).tools)

    async def call(self, name: str, arguments: dict[str, Any]) -> ToolOutcome:
        if self._client is None:
            return ToolOutcome(
                ok=False, error="MCP session is not open (transport error)", retryable=True
            )
        try:
            async with asyncio.timeout(self._timeout):
                res = await self._client.call_tool(name, arguments)
        except TimeoutError:
            return ToolOutcome(ok=False, error=f"{name} timed out", retryable=True)
        except Exception as exc:
            return ToolOutcome(
                ok=False, error=f"tool transport error ({type(exc).__name__})", retryable=True
            )

        if res.is_error:
            text = res.content[0].text if res.content and hasattr(res.content[0], "text") else ""
            message = text or f"{name} failed"
            return ToolOutcome(ok=False, error=message, retryable=is_retryable(message))

        body = res.structured_content or {}
        return ToolOutcome(
            ok=True,
            found=bool(body.get("found")),
            data=body.get("data") or {},
            source=body.get("source"),
            notes=[str(n) for n in body.get("notes") or []],
        )
