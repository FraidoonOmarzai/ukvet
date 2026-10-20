"""Opt-in smoke tests against a REAL LLM. Never run in CI.

    LLM_PROVIDER=openai LLM_MODEL=... LLM_API_KEY=... uv run pytest -m live --no-cov

They still use the recorded Companies House fixtures, so only the LLM is live. They answer the
questions the offline tests cannot: does a real model produce claims that pass the citation
checker, and how long does the Reporter take?
"""

import time
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

import pytest
from agent_helpers import make_deps
from ukvet_agent.graph import build_graph, run_report
from ukvet_agent.llm import LlmSettings, build_writer
from ukvet_agent.mcp_client import McpToolClient
from ukvet_agent.schemas import Report
from ukvet_agent.settings import AgentSettings

pytestmark = pytest.mark.live


async def test_real_llm_narrative_passes_the_citation_checker(
    open_tools: Callable[[], AbstractAsyncContextManager[McpToolClient]],
    agent_settings: AgentSettings,
) -> None:
    llm = LlmSettings()
    writer = build_writer(llm)
    if writer is None:
        pytest.skip("set LLM_PROVIDER / LLM_MODEL / LLM_API_KEY to run live tests")
    async with open_tools() as tools:
        deps = make_deps(tools, agent_settings, writer)
        deps.llm_timeout_seconds = llm.timeout_seconds + 2
        start = time.perf_counter()
        report = await run_report(build_graph(deps), "12345678")
        elapsed = time.perf_counter() - start
    assert isinstance(report, Report)
    print(
        f"\nmodel={writer.model_name} source={report.narrative_source} "
        f"kept={report.citation_stats.claims_kept}/{report.citation_stats.claims_total} "
        f"retries={report.citation_stats.retries} total={elapsed:.1f}s "
        f"report_node={report.timings_ms.get('report', 0) / 1000:.1f}s"
    )
    for violation in report.citation_stats.violations:
        print("  violation:", violation)
    assert report.narrative_source == "llm", report.citation_stats.violations
