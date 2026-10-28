"""`ukvet-check`: run reports from the terminal against the real stack.

    ukvet-check 00445790 17491796          one summary line per company
    ukvet-check --full "Acme Ltd"          also print headline, findings and red flags
    ukvet-check --json 00445790            full JSON report(s)

Uses the same wiring as the API (stdio MCP server + the LLM from LLM_* variables), so it is also
the tool for the manual 10-company check and for measuring real latency (see docs/12).
"""

import argparse
import asyncio
import logging
import sys
from collections.abc import Sequence
from typing import TextIO

from ukvet_agent.api import DepsFactory, default_deps
from ukvet_agent.errors import AgentConfigError, AgentError
from ukvet_agent.graph import build_graph, run_report
from ukvet_agent.schemas import NeedsSelection, Report
from ukvet_agent.tracing import flush_tracer


def _summary(report: Report) -> str:
    stats = report.citation_stats
    return (
        f"{report.company_number:<10} {report.company_name[:32]:<32} {report.risk_level:<18} "
        f"{report.narrative_source:<8} flags={len(report.red_flags)} gaps={len(report.gaps)} "
        f"dropped={stats.claims_dropped} retries={stats.retries} "
        f"{report.timings_ms.get('total', 0) / 1000:.1f}s"
    )


def _full(report: Report) -> str:
    lines = [f"  {report.assessment}", f"  Headline: {report.headline.text}"]
    lines += [f"  Red flag [{f.severity}]: {f.title}" for f in report.red_flags]
    lines += [f"  - {c.text} [{', '.join(c.fact_ids)}]" for c in report.findings]
    lines += [f"  Gap {g.question_id}: {g.reason}" for g in report.gaps]
    return "\n".join(lines)


async def check(
    companies: Sequence[str],
    *,
    full: bool = False,
    as_json: bool = False,
    deps_factory: DepsFactory = default_deps,
    out: TextIO | None = None,
) -> int:
    """Run each company in turn (sequential: kind to the Companies House rate limit)."""
    out = out or sys.stdout
    failures = 0
    async with deps_factory() as deps:
        graph = build_graph(deps)
        for company in companies:
            try:
                result = await run_report(graph, company)
            except AgentError as exc:
                failures += 1
                print(f"{company}: ERROR {type(exc).__name__}: {exc}", file=out)
                continue
            if as_json:
                print(result.model_dump_json(indent=2), file=out)
            elif isinstance(result, NeedsSelection):
                print(f"{company}: {result.message}", file=out)
                for c in result.candidates:
                    print(f"  {c.company_number}  {c.name}  ({c.status})", file=out)
            else:
                print(_summary(result), file=out)
                if full:
                    print(_full(result), file=out)
    return 1 if failures else 0


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="ukvet-check", description=__doc__.split("\n")[0])
    parser.add_argument("companies", nargs="+", help="company numbers or names")
    parser.add_argument("--full", action="store_true", help="print headline, findings, flags")
    parser.add_argument("--json", action="store_true", dest="as_json", help="print JSON reports")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING)
    try:
        code = asyncio.run(check(args.companies, full=args.full, as_json=args.as_json))
    except AgentConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        code = 2
    flush_tracer()
    sys.exit(code)


if __name__ == "__main__":
    main()
