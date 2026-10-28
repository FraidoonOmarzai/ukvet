"""Phase 4: usage counting (M8, M9) and optional tracing. No network, no Langfuse account."""

from collections.abc import Callable, Iterator
from contextlib import AbstractAsyncContextManager, contextmanager
from typing import Any

import pytest
from agent_helpers import FakeWriter, draft, make_deps
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult
from ukvet_agent import tracing, usage
from ukvet_agent.graph import build_graph, run_report
from ukvet_agent.llm import LangChainNarrativeWriter, NarrativeDraft
from ukvet_agent.mcp_client import McpToolClient, ToolOutcome
from ukvet_agent.schemas import Report
from ukvet_agent.settings import AgentSettings
from ukvet_agent.tracing import NoopTracer, TracedTools, TraceSettings, build_tracer
from ukvet_agent.usage import UsageCallback, UsageRecorder, UsageSettings

OpenTools = Callable[[], AbstractAsyncContextManager[McpToolClient]]


# ---- usage ------------------------------------------------------------------------------------


def test_cost_is_none_without_prices_and_exact_with_them() -> None:
    rec = UsageRecorder()
    rec.llm_call(2000, 500)
    rec.tool_call("get_company_profile")
    no_prices = rec.snapshot(UsageSettings(_env_file=None))  # type: ignore[call-arg]
    assert no_prices.cost_gbp is None  # we never guess a price
    assert (no_prices.input_tokens, no_prices.output_tokens, no_prices.tool_calls) == (2000, 500, 1)
    priced = rec.snapshot(
        UsageSettings(price_in_gbp_per_mtok=1.0, price_out_gbp_per_mtok=4.0, _env_file=None)  # type: ignore[call-arg]
    )
    assert priced.cost_gbp == pytest.approx((2000 * 1.0 + 500 * 4.0) / 1_000_000)


def test_usage_callback_reads_token_counts_from_the_message() -> None:
    rec = UsageRecorder()
    msg = AIMessage(
        content="x", usage_metadata={"input_tokens": 120, "output_tokens": 30, "total_tokens": 150}
    )
    UsageCallback(rec).on_llm_end(LLMResult(generations=[[ChatGeneration(message=msg)]]))
    snap = rec.snapshot(UsageSettings(_env_file=None))  # type: ignore[call-arg]
    assert (snap.llm_calls, snap.input_tokens, snap.output_tokens) == (1, 120, 30)


def test_usage_callback_falls_back_to_llm_output() -> None:
    rec = UsageRecorder()
    result = LLMResult(
        generations=[[ChatGeneration(message=AIMessage(content="x"))]],
        llm_output={"token_usage": {"prompt_tokens": 7, "completion_tokens": 3}},
    )
    UsageCallback(rec).on_llm_end(result)
    assert (rec.input_tokens, rec.output_tokens) == (7, 3)


async def test_report_carries_tool_call_counts(
    open_tools: OpenTools, agent_settings: AgentSettings
) -> None:
    async with open_tools() as tools:
        result = await run_report(build_graph(make_deps(tools, agent_settings)), "12345678")
    assert isinstance(result, Report)
    assert result.usage.tool_calls == len(result.usage.tools) > 3
    assert "get_company_profile" in result.usage.tools
    assert result.usage.llm_calls == 0 and result.usage.cost_gbp is None  # template mode


async def test_two_concurrent_reports_do_not_share_counters(
    open_tools: OpenTools, agent_settings: AgentSettings
) -> None:
    import asyncio

    async with open_tools() as tools:
        graph = build_graph(make_deps(tools, agent_settings))
        a, b = await asyncio.gather(run_report(graph, "12345678"), run_report(graph, "87654321"))
    assert isinstance(a, Report) and isinstance(b, Report)
    assert a.usage.tool_calls != b.usage.tool_calls  # one is a dissolved company: fewer calls
    assert a.usage.tool_calls + b.usage.tool_calls == len(a.usage.tools) + len(b.usage.tools)


class _Structured:
    def __init__(self) -> None:
        self.config: Any = "unset"

    async def ainvoke(self, messages: list[Any], config: Any = None) -> Any:
        self.config = config
        return NarrativeDraft.model_validate({"headline": {"text": "h", "fact_ids": ["Q1.status"]}})


class _Chat:
    def __init__(self) -> None:
        self.structured = _Structured()

    def with_structured_output(self, schema: type) -> _Structured:
        return self.structured


async def test_writer_attaches_the_usage_callback_only_inside_a_report() -> None:
    chat = _Chat()
    writer = LangChainNarrativeWriter(chat, "m")
    await writer.write("s", "u")
    assert chat.structured.config is None  # outside run_report: plain call, nothing attached
    recorder, token = usage.start()
    try:
        await writer.write("s", "u")
    finally:
        usage.stop(token)
    callbacks = chat.structured.config["callbacks"]
    assert any(isinstance(c, UsageCallback) for c in callbacks)
    assert recorder.llm_calls == 0  # the callback only counts when the model actually reports


# ---- tracing ----------------------------------------------------------------------------------


class RecordingTracer:
    enabled = True

    def __init__(self) -> None:
        self.spans: list[str] = []
        self.failures: list[str] = []

    @contextmanager
    def _span(self, name: str) -> Iterator[Any]:
        self.spans.append(name)
        tracer = self

        class Handle:
            def fail(self, message: str) -> None:
                tracer.failures.append(message)

        yield Handle()

    def report(self, request: str) -> Any:
        return self._span("report")

    def node(self, name: str) -> Any:
        return self._span(f"node.{name}")

    def tool(self, name: str, arguments: dict[str, Any]) -> Any:
        return self._span(f"tool.{name}")

    def llm_callbacks(self) -> list[Any]:
        return []

    def flush(self) -> None:
        return None


async def test_spans_cover_the_report_every_node_and_tool_call(
    open_tools: OpenTools, agent_settings: AgentSettings
) -> None:
    tracer = RecordingTracer()
    tracing.set_tracer(tracer)
    async with open_tools() as tools:
        result = await run_report(build_graph(make_deps(tools, agent_settings)), "12345678")
    assert isinstance(result, Report)
    assert tracer.spans[0] == "report"
    for node in ("plan", "research", "verify", "report"):
        assert f"node.{node}" in tracer.spans
    tool_spans = [s for s in tracer.spans if s.startswith("tool.")]
    assert len(tool_spans) == result.usage.tool_calls


async def test_a_failed_tool_call_marks_its_span() -> None:
    class Inner:
        async def ping(self) -> int:
            return 1

        async def call(self, name: str, arguments: dict[str, Any]) -> ToolOutcome:
            return ToolOutcome(ok=False, error="Companies House is not responding")

    tracer = RecordingTracer()
    outcome = await TracedTools(Inner(), tracer).call("get_charges", {"company_number": "1"})
    assert not outcome.ok
    assert tracer.failures == ["Companies House is not responding"]


def test_without_keys_tracing_is_a_noop() -> None:
    tracer = build_tracer(TraceSettings(_env_file=None))  # type: ignore[call-arg]
    assert isinstance(tracer, NoopTracer) and not tracer.enabled
    with tracer.report("x"), tracer.node("plan"), tracer.tool("t", {}):
        pass
    assert tracer.llm_callbacks() == []


def test_missing_langfuse_package_degrades_to_untraced(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(_: TraceSettings) -> Any:
        raise ImportError("no langfuse")

    monkeypatch.setattr(tracing, "LangfuseTracer", boom)
    keys = TraceSettings(public_key="pk", secret_key="sk", _env_file=None)  # type: ignore[arg-type,call-arg]
    assert isinstance(build_tracer(keys), NoopTracer)


def test_langfuse_is_configured_redacted_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    langfuse = pytest.importorskip("langfuse")
    seen: dict[str, Any] = {}

    class FakeLangfuse:
        def __init__(self, **kwargs: Any) -> None:
            seen.update(kwargs)

        def flush(self) -> None:
            seen["flushed"] = True

    monkeypatch.setattr(langfuse, "Langfuse", FakeLangfuse)
    s = TraceSettings(public_key="pk", secret_key="sk", host="https://lf.example", _env_file=None)  # type: ignore[arg-type,call-arg]
    tracer = build_tracer(s)
    assert tracer.enabled
    assert seen["base_url"] == "https://lf.example"
    assert seen["mask"](data={"officer": "A PERSON"}) == "[redacted]"  # no names leave the machine
    tracer.flush()
    assert seen["flushed"]

    seen.clear()
    full = TraceSettings(
        public_key="pk",
        secret_key="sk",
        content="full",
        _env_file=None,  # type: ignore[arg-type,call-arg]
    )
    build_tracer(full)
    assert "mask" not in seen


async def test_tracing_failures_never_break_a_report(
    monkeypatch: pytest.MonkeyPatch, open_tools: OpenTools, agent_settings: AgentSettings
) -> None:
    langfuse = pytest.importorskip("langfuse")

    class Exploding:
        def __init__(self, **_: Any) -> None:
            pass

        def start_as_current_observation(self, **_: Any) -> Any:
            raise RuntimeError("langfuse is down")

        def flush(self) -> None:
            raise RuntimeError("still down")

    monkeypatch.setattr(langfuse, "Langfuse", Exploding)
    tracing.set_tracer(
        build_tracer(TraceSettings(public_key="pk", secret_key="sk", _env_file=None))
    )  # type: ignore[arg-type,call-arg]
    async with open_tools() as tools:
        result = await run_report(
            build_graph(make_deps(tools, agent_settings, FakeWriter(draft(("x", []))))), "12345678"
        )
    assert isinstance(result, Report)
    tracing.flush_tracer()  # must not raise
