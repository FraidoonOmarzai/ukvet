"""Recorded (anonymised) Companies House responses, and the replay harness that serves them.

A snapshot is the raw API world for ONE company on ONE day. Replaying it through the real
ukvet-mcp client and the real agent graph makes evaluation free, fast and identical every run.
"""

import json
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import httpx
import respx
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from ukvet_agent.graph import Deps, build_graph, run_report
from ukvet_agent.llm import NarrativeWriter
from ukvet_agent.mcp_client import McpToolClient, ToolClient
from ukvet_agent.schemas import NeedsSelection, Report
from ukvet_agent.settings import AgentSettings
from ukvet_mcp import server as mcp_module
from ukvet_mcp.cache import ResponseCache
from ukvet_mcp.client import CompaniesHouseClient
from ukvet_mcp.config import Settings
from ukvet_mcp.rate_limit import SlidingWindowRateLimiter
from ukvet_mcp.service import CompaniesHouseService

BASE = "https://api.company-information.service.gov.uk"
ENDPOINTS = ("profile", "officers", "psc", "charges", "insolvency", "filings")
_SUFFIX = {
    "officers": "/officers",
    "psc": "/persons-with-significant-control",
    "charges": "/charges",
    "insolvency": "/insolvency",
    "filings": "/filing-history",
}


class Endpoint(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: int
    body: dict[str, Any] | None = None


class SnapshotMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")
    company_number: str
    as_of: date
    recorded: date | None = None
    public: bool = False
    synthetic: bool = False
    truncated: list[str] = Field(default_factory=list, description="Endpoints cut at a fetch cap.")


class Snapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")
    meta: SnapshotMeta
    endpoints: dict[str, Endpoint] = Field(default_factory=dict)
    appointments: dict[str, Endpoint] = Field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> "Snapshot":
        return cls.model_validate_json(path.read_text(encoding="utf-8"))

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.model_dump(mode="json"), indent=1, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )


class _Clock:
    """Instant fake sleep: replay never waits and never touches the real rate limiter."""

    def __init__(self) -> None:
        self.t = 1_000.0

    def now(self) -> float:
        return self.t

    async def sleep(self, seconds: float) -> None:
        self.t += seconds


def _page(ep: Endpoint, request: httpx.Request) -> httpx.Response:
    """Serve one page of a stored list response, honouring start_index / items_per_page."""
    if ep.status != 200 or ep.body is None:
        return httpx.Response(ep.status)
    body = dict(ep.body)
    items = body.get("items")
    if isinstance(items, list):
        start = int(request.url.params.get("start_index", 0))
        per = int(request.url.params.get("items_per_page", 35))
        body["items"] = items[start : start + per]
        body["start_index"] = start
        body["items_per_page"] = per
    return httpx.Response(200, json=body)


class ReplayHarness:
    """Serve every snapshot of a dataset through the real MCP server and agent graph."""

    def __init__(self, snapshots: dict[str, Snapshot]) -> None:
        self.snapshots = snapshots
        self._as_of: date = date(2000, 1, 1)
        self._router: respx.MockRouter | None = None
        self.tools: McpToolClient | None = None
        self.settings = AgentSettings(_env_file=None)  # type: ignore[call-arg]

    @classmethod
    def from_dir(cls, snapshot_dir: Path, numbers: list[str]) -> "ReplayHarness":
        snaps = {n: Snapshot.load(snapshot_dir / f"{n}.json") for n in numbers}
        return cls(snaps)

    # ---- routes -----------------------------------------------------------------------------
    def _mount(self) -> respx.MockRouter:
        router = respx.mock(base_url=BASE, assert_all_called=False, assert_all_mocked=True)
        router.start()

        def make_handler(snap: Snapshot, key: str) -> Callable[[httpx.Request], httpx.Response]:
            def handler(request: httpx.Request) -> httpx.Response:
                ep = snap.endpoints.get(key)
                return _page(ep, request) if ep else httpx.Response(404)

            return handler

        for number, snap in self.snapshots.items():
            router.get(f"/company/{number}").mock(side_effect=make_handler(snap, "profile"))
            for key, suffix in _SUFFIX.items():
                router.get(f"/company/{number}{suffix}").mock(side_effect=make_handler(snap, key))
            for oid, ep in snap.appointments.items():
                router.get(f"/officers/{oid}/appointments").mock(
                    side_effect=lambda r, ep=ep: _page(ep, r)
                )
        router.get(path__regex=r"^/(company|officers)/.*").mock(return_value=httpx.Response(404))
        router.get("/search/companies").mock(
            return_value=httpx.Response(200, json={"total_results": 0, "items": []})
        )
        return router

    @asynccontextmanager
    async def open(self) -> AsyncIterator["ReplayHarness"]:
        clock = _Clock()
        settings = Settings(api_key=SecretStr("offline"), cache_enabled=False, _env_file=None)  # type: ignore[call-arg]
        client = CompaniesHouseClient(
            settings,
            cache=ResponseCache(":memory:", 3600, enabled=False),
            limiter=SlidingWindowRateLimiter(10_000, 300, clock=clock.now, sleep=clock.sleep),
            sleep=clock.sleep,
            wall_clock=clock.now,
            jitter=lambda: 0.5,
        )
        service = CompaniesHouseService(client, max_items=100, today=lambda: self._as_of)
        mcp_module.set_service(service)
        self._router = self._mount()
        try:
            async with McpToolClient(mcp_module.mcp, timeout_seconds=20) as tools:
                self.tools = tools
                yield self
        finally:
            self.tools = None
            self._router.stop()
            mcp_module.set_service(None)
            await service.aclose()

    # ---- running ----------------------------------------------------------------------------
    async def run(
        self,
        number: str,
        *,
        writer: NarrativeWriter | None = None,
        wrap_tools: Callable[[ToolClient], ToolClient] | None = None,
    ) -> Report:
        """Run the real agent graph for one recorded company (clock frozen at its `as_of`)."""
        if self.tools is None:
            raise RuntimeError("harness is not open; use `async with harness.open()`")
        snap = self.snapshots[number]
        self._as_of = snap.meta.as_of
        now = datetime(
            snap.meta.as_of.year, snap.meta.as_of.month, snap.meta.as_of.day, 12, 0, tzinfo=UTC
        )
        tools: ToolClient = wrap_tools(self.tools) if wrap_tools else self.tools
        graph = build_graph(
            Deps(tools=tools, settings=self.settings, writer=writer, clock=lambda: now)
        )
        result = await run_report(graph, number)
        if isinstance(result, NeedsSelection):
            raise RuntimeError(f"{number}: planner asked for a selection (not a company number?)")
        return result
