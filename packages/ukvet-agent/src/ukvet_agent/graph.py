"""LangGraph assembly: plan -> research -> verify -> (research again?) -> report.

The graph is FIXED (ADR-007): the model never chooses which node runs next, so behaviour is
testable and every path is bounded by `max_verifier_loops`.
"""

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any, Protocol, TypedDict

from langgraph.graph import END, START, StateGraph

from ukvet_agent.llm import NarrativeWriter
from ukvet_agent.mcp_client import ToolClient, ToolOutcome
from ukvet_agent.nodes.planner import plan_node
from ukvet_agent.nodes.reporter import report_node
from ukvet_agent.nodes.researcher import research_node
from ukvet_agent.nodes.verifier import verify_node
from ukvet_agent.schemas import Fact, Gap, NeedsSelection, Report
from ukvet_agent import usage as usage_mod
from ukvet_agent.settings import AgentSettings
from ukvet_agent.tracing import TracedTools, get_tracer


class AgentState(TypedDict, total=False):
    request: str
    company_number: str
    company_name: str | None
    plan: list[str]
    raw: dict[str, ToolOutcome]
    facts: list[Fact]
    gaps: list[Gap]
    notes: list[str]
    retry_keys: list[str]
    loops: int
    timings_ms: dict[str, int]
    result: Report | NeedsSelection


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass
class Deps:
    tools: ToolClient
    settings: AgentSettings = field(default_factory=AgentSettings)
    writer: NarrativeWriter | None = None
    llm_timeout_seconds: float = 30.0
    clock: Callable[[], datetime] = _utcnow

    def today(self) -> date:
        return self.clock().date()


class NodeFn(Protocol):
    def __call__(self, state: AgentState) -> Awaitable[Any]: ...


def _timed(name: str, fn: NodeFn) -> NodeFn:
    """Accumulate per-node wall time (ms) in state, summed across loops."""

    async def wrapper(state: AgentState) -> dict[str, Any]:
        start = time.perf_counter()
        with get_tracer().node(name):
            update = await fn(state)
        elapsed = round((time.perf_counter() - start) * 1000)
        timings = dict(state.get("timings_ms") or {})
        timings[name] = timings.get(name, 0) + elapsed
        return {**update, "timings_ms": timings}

    return wrapper


def build_graph(deps: Deps) -> Any:
    tools = TracedTools(deps.tools)  # counts every call (M9) and opens a span when tracing is on

    async def plan(state: AgentState) -> dict[str, Any]:
        return await plan_node(dict(state), tools)

    async def research(state: AgentState) -> dict[str, Any]:
        return await research_node(dict(state), tools, deps.settings, deps.today())

    async def verify(state: AgentState) -> dict[str, Any]:
        return verify_node(dict(state), deps.settings, deps.today())

    async def report(state: AgentState) -> dict[str, Any]:
        return await report_node(dict(state), deps.writer, deps.clock(), deps.llm_timeout_seconds)

    def after_plan(state: AgentState) -> str:
        return "end" if "result" in state else "research"

    def after_verify(state: AgentState) -> str:
        return "research" if state.get("retry_keys") else "report"

    graph = StateGraph(AgentState)
    graph.add_node("plan", _timed("plan", plan))
    graph.add_node("research", _timed("research", research))
    graph.add_node("verify", _timed("verify", verify))
    graph.add_node("report", _timed("report", report))
    graph.add_edge(START, "plan")
    graph.add_conditional_edges("plan", after_plan, {"end": END, "research": "research"})
    graph.add_edge("research", "verify")
    graph.add_conditional_edges(
        "verify", after_verify, {"research": "research", "report": "report"}
    )
    graph.add_edge("report", END)
    return graph.compile()


async def run_report(graph: Any, request: str) -> Report | NeedsSelection:
    """Run one request through the graph and return the typed result."""
    start = time.perf_counter()
    recorder, token = usage_mod.start()
    try:
        with get_tracer().report(request):
            final: AgentState = await graph.ainvoke({"request": request})
    finally:
        usage_mod.stop(token)
    result = final["result"]
    if isinstance(result, Report):
        timings = dict(final.get("timings_ms") or {})
        timings["total"] = round((time.perf_counter() - start) * 1000)
        result.timings_ms = timings
        result.usage = recorder.snapshot()
    return result
