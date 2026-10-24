"""Fault injection at the tool boundary (what the agent sees when Companies House misbehaves).

HTTP-level behaviour (retries, 429 back-off, 5xx handling inside ukvet-mcp) is covered by the
unit tests in tests/mcp_server. These faults test the layer above: does the AGENT turn a failed
tool into an explicit gap, keep every other fact intact, and refuse to invent anything?
"""

from typing import Any

from ukvet_agent.mcp_client import ToolClient, ToolOutcome

from ukvet_evals.schema import FaultSpec

_MESSAGES = {
    "timeout": ("{tool} timed out", True),
    "unavailable": ("Companies House is not responding (injected fault)", True),
    "permanent": ("Companies House returned an error for this request (injected fault)", False),
}


class FaultyTools:
    """Wraps a ToolClient and fails selected calls. Satisfies the ToolClient protocol."""

    def __init__(self, inner: ToolClient, faults: list[FaultSpec]) -> None:
        self._inner = inner
        self._faults = faults
        self._calls: dict[int, int] = {}  # fault index -> calls seen (for transient)
        self._officer_order: list[str] = []  # first-seen officer ids = director order

    async def ping(self) -> int:
        return await self._inner.ping()

    def _director_index(self, arguments: dict[str, Any]) -> int:
        oid = str(arguments.get("officer_id", ""))
        if oid not in self._officer_order:
            self._officer_order.append(oid)
        return self._officer_order.index(oid) + 1

    async def call(self, name: str, arguments: dict[str, Any]) -> ToolOutcome:
        index = self._director_index(arguments) if name == "get_officer_appointments" else None
        for n, fault in enumerate(self._faults):
            if fault.tool != name:
                continue
            if fault.director_index is not None and fault.director_index != index:
                continue
            if fault.mode == "transient":
                seen = self._calls.get(n, 0)
                self._calls[n] = seen + 1
                if seen < fault.times:
                    return ToolOutcome(
                        ok=False,
                        error="Companies House is not responding (injected transient fault)",
                        retryable=True,
                    )
                continue
            message, retryable = _MESSAGES[fault.mode]
            return ToolOutcome(ok=False, error=message.format(tool=name), retryable=retryable)
        return await self._inner.call(name, arguments)
