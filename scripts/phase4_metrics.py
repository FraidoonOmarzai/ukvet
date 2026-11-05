"""Measure M7 (latency), M8 (cost) and M9 (tool calls) with LIVE reports.

    uv run python scripts/phase4_metrics.py 00445790 03977902 12056899 --out evals/results/phase4
    uv run python scripts/phase4_metrics.py --file numbers.txt

Needs CH_API_KEY, plus LLM_PROVIDER / LLM_MODEL / LLM_API_KEY for a real narrative. For cost, set
UKVET_PRICE_IN_GBP_PER_MTOK and UKVET_PRICE_OUT_GBP_PER_MTOK from your provider's price page.
Tracing to Langfuse happens too when LANGFUSE_* keys are set.

Company numbers are real and the output folder is git-ignored; do not commit what it writes.
Replay timings exclude the network, so this must use the live API (that is the point).
"""

import argparse
import asyncio
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

from ukvet_agent.api import default_deps
from ukvet_agent.graph import build_graph, run_report
from ukvet_agent.llm import LlmSettings
from ukvet_agent.schemas import NeedsSelection, Report
from ukvet_agent.tracing import flush_tracer
from ukvet_evals import perf


async def measure(numbers: list[str]) -> list[Report]:
    reports: list[Report] = []
    async with default_deps() as deps:
        graph = build_graph(deps)
        for n in numbers:  # one at a time: kind to the Companies House rate limit
            result = await run_report(graph, n)
            if isinstance(result, NeedsSelection):
                print(f"{n}: not a company number (needs selection); skipped", file=sys.stderr)
                continue
            reports.append(result)
            print(
                f"{n}: {result.timings_ms.get('total', 0) / 1000:.1f}s "
                f"tools={result.usage.tool_calls} {result.narrative_source}"
            )
    return reports


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("numbers", nargs="*", help="company numbers (8 characters)")
    ap.add_argument("--file", help="text file with one company number per line")
    ap.add_argument("--out", default="evals/results/phase4")
    ap.add_argument("--label", default="", help="name of the model being measured (Phase 5)")
    args = ap.parse_args()
    numbers = list(args.numbers)
    if args.file:
        numbers += [ln.strip() for ln in Path(args.file).read_text().splitlines() if ln.strip()]
    if not numbers:
        ap.error("give company numbers or --file")
    logging.basicConfig(level=logging.WARNING)
    llm = LlmSettings()
    started = datetime.now(UTC)
    reports = asyncio.run(measure(numbers))
    flush_tracer()
    summary = perf.summarise(reports)
    summary["run"] = {
        "label": args.label,
        "provider": llm.provider,
        "model": llm.model or "",
        "started": started.isoformat(timespec="seconds"),
        "finished": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "metrics.json").write_text(json.dumps(summary, indent=1, default=str) + "\n")
    (out / "metrics.md").write_text(perf.render_markdown(summary), encoding="utf-8")
    print(perf.render_markdown(summary))
    print(f"written to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
