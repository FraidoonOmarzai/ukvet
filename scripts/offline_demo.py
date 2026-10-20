"""Run the whole agent graph offline on the recorded fixtures and print what each stage produced.

    uv run python scripts/offline_demo.py                # report for 12345678
    uv run python scripts/offline_demo.py 87654321       # dissolved company
    uv run python scripts/offline_demo.py acme           # ambiguous name -> candidates

No API keys, no network, no LLM. Uses the same fixtures as the tests.
"""

import asyncio
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx
import respx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
from ch_support import BASE, FIXTURE_DIR, TODAY, FakeClock, load_fixture, make_client  # noqa: E402
from ukvet_agent.errors import AgentError  # noqa: E402
from ukvet_agent.graph import Deps, build_graph, run_report  # noqa: E402
from ukvet_agent.mcp_client import McpToolClient  # noqa: E402
from ukvet_agent.schemas import NeedsSelection  # noqa: E402
from ukvet_agent.settings import AgentSettings  # noqa: E402
from ukvet_mcp import server as mcp_module  # noqa: E402
from ukvet_mcp.config import Settings  # noqa: E402
from ukvet_mcp.service import CompaniesHouseService  # noqa: E402

NOW = datetime(2026, 3, 4, 12, 0, tzinfo=UTC)


def mock_companies_house() -> respx.MockRouter:
    router = respx.mock(base_url=BASE, assert_all_called=False, assert_all_mocked=True)
    router.start()
    for f in sorted(FIXTURE_DIR.glob("*.json")):
        d = json.loads(f.read_text())
        if d["request"]["path"] == "/search/companies":
            continue
        resp = (
            httpx.Response(200, json=d["body"])
            if d["status"] == 200
            else httpx.Response(d["status"])
        )
        router.get(d["request"]["path"]).mock(return_value=resp)
    search = load_fixture("search__acme")
    router.get("/search/companies").mock(
        side_effect=lambda r: httpx.Response(
            200,
            json=search
            if "acme" in r.url.params.get("q", "").lower()
            else {"total_results": 0, "items": []},
        )
    )
    router.get(path__regex=r"^/(company|officers)/.*").mock(return_value=httpx.Response(404))
    return router


async def main(request: str) -> int:
    logging.disable(logging.CRITICAL)
    mock_companies_house()
    settings = Settings(api_key="offline", cache_enabled=False, _env_file=None)  # type: ignore[call-arg]
    mcp_module.set_service(
        CompaniesHouseService(
            make_client(settings, FakeClock()), max_items=100, today=lambda: TODAY
        )
    )
    async with McpToolClient(mcp_module.mcp, timeout_seconds=10) as tools:
        agent_settings = AgentSettings(_env_file=None)  # type: ignore[call-arg]
        graph = build_graph(Deps(tools=tools, settings=agent_settings, clock=lambda: NOW))
        try:
            result = await run_report(graph, request)
        except AgentError as exc:
            print(f"ERROR {type(exc).__name__} (HTTP {exc.http_status}): {exc}")
            return 1

    if isinstance(result, NeedsSelection):
        print(result.message)
        for c in result.candidates:
            print(f"  {c.company_number}  {c.name}  ({c.status})")
        return 0

    print(f"{result.company_name} ({result.company_number})  risk={result.risk_level}")
    print(result.assessment, "\n")
    print("HEADLINE:", result.headline.text, result.headline.fact_ids)
    for c in result.findings:
        print(" -", c.text, c.fact_ids)
    print("\nRED FLAGS:", [(f.severity, f.id) for f in result.red_flags])
    print("GAPS:", [(g.question_id, g.tool, g.retryable) for g in result.gaps])
    print("FACT IDS:", [f.id for f in result.facts])
    print(
        "NARRATIVE:",
        result.narrative_source,
        "| CITATION STATS:",
        result.citation_stats.model_dump(),
    )
    print("TIMINGS (ms):", result.timings_ms)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "12345678")))
