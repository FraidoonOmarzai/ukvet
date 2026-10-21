"""Step 2.14: measure latency and LLM behaviour on the real stack. Prints numbers, saves a CSV.

    uv run python scripts/measure.py 00445790 17491796 12115175 01468547 12056899 17016019 03977902
    uv run python scripts/measure.py --out data/processed/measure.csv <numbers...>

Runs every company twice against the same fresh cache file:
  pass 1 = COLD cache (every Companies House call is real)
  pass 2 = WARM cache (answered from the 24 h SQLite cache)
Uses the LLM from LLM_* variables (default: none = template narrative, so you measure only
Companies House + agent time). Run it again with LLM_PROVIDER set to measure end to end.

Use company NUMBERS: a name that needs a choice returns candidates, not a report.
The CSV holds numbers and counts only: no company names, no director names (UK GDPR).
"""

import argparse
import asyncio
import csv
import logging
import os
import statistics
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any, TextIO

from ukvet_agent.api import DepsFactory, default_deps
from ukvet_agent.errors import AgentConfigError, AgentError
from ukvet_agent.graph import build_graph, run_report
from ukvet_agent.schemas import NeedsSelection

STAGES = ("plan", "research", "verify", "report")
TARGET_P95_S = 30.0


def _pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    return s[min(len(s) - 1, round(p * (len(s) - 1)))]


async def run_pass(
    label: str, companies: Sequence[str], deps_factory: DepsFactory
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    async with deps_factory() as deps:
        graph = build_graph(deps)
        for company in companies:
            row: dict[str, Any] = {"pass": label, "company": company}
            try:
                result = await run_report(graph, company)
            except AgentError as exc:
                row |= {"status": f"error:{type(exc).__name__}"}
            else:
                if isinstance(result, NeedsSelection):
                    row |= {"status": "needs_selection"}
                else:
                    t, s = result.timings_ms, result.citation_stats
                    row |= {
                        "status": "ok",
                        "risk_level": result.risk_level,
                        "narrative": result.narrative_source,
                        "flags": len(result.red_flags),
                        "gaps": len(result.gaps),
                        "claims": s.claims_total,
                        "dropped": s.claims_dropped,
                        "retries": s.retries,
                        "total_ms": t.get("total", 0),
                        **{f"{k}_ms": t.get(k, 0) for k in STAGES},
                    }
            rows.append(row)
    return rows


def summarise(rows: list[dict[str, Any]], label: str, out: TextIO) -> None:
    ok = [r for r in rows if r["status"] == "ok"]
    bad = [r for r in rows if r["status"] != "ok"]
    print(f"\n== {label}: {len(ok)} reports ok, {len(bad)} not ok ==", file=out)
    for r in bad:
        print(f"  NOT OK {r['company']}: {r['status']}", file=out)
    if not ok:
        return
    totals = [r["total_ms"] / 1000 for r in ok]
    print(
        f"  total seconds: median {statistics.median(totals):.2f}  "
        f"p95 {_pct(totals, 0.95):.2f}  worst {max(totals):.2f}",
        file=out,
    )
    for st in STAGES:
        v = [r[f"{st}_ms"] / 1000 for r in ok]
        print(f"    {st:<9} median {statistics.median(v):.2f}s  worst {max(v):.2f}s", file=out)
    claims = sum(r["claims"] for r in ok)
    dropped = sum(r["dropped"] for r in ok)
    llm = [r for r in ok if r["narrative"] != "template"]
    print(
        f"  narrative: {len(llm)} LLM, {len(ok) - len(llm)} template; "
        f"claims {claims}, dropped {dropped}, retries {sum(r['retries'] for r in ok)}",
        file=out,
    )
    if claims:
        print(f"  citation-checker drop rate: {dropped / claims:.1%}", file=out)
    print(f"  risk levels: {sorted({r['risk_level'] for r in ok})}", file=out)
    print(
        f"  vs target p95 < {TARGET_P95_S:.0f}s: "
        f"{'MET' if _pct(totals, 0.95) < TARGET_P95_S else 'NOT MET'}",
        file=out,
    )


async def measure(
    companies: Sequence[str],
    deps_factory: DepsFactory,
    *,
    out: TextIO | None = None,
    skip_warm: bool = False,
) -> list[dict[str, Any]]:
    out = out or sys.stdout
    cold = await run_pass("cold", companies, deps_factory)
    summarise(cold, "COLD cache", out)
    rows = list(cold)
    if not skip_warm:
        warm = await run_pass("warm", companies, deps_factory)
        summarise(warm, "WARM cache", out)
        rows += warm
    return rows


def write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    fields = sorted({k for r in rows for k in r}, key=lambda k: (k not in ("pass", "company"), k))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def main(argv: Sequence[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("companies", nargs="+", help="company NUMBERS")
    ap.add_argument("--out", type=Path, default=Path("data/processed/measure.csv"))
    ap.add_argument("--skip-warm", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.WARNING)
    # A throw-away cache file makes pass 1 genuinely cold. The MCP subprocess inherits this.
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["UKVET_CACHE_PATH"] = str(Path(tmp) / "measure_cache.sqlite")
        os.environ["UKVET_CACHE_ENABLED"] = "true"
        try:
            rows = asyncio.run(measure(args.companies, default_deps, skip_warm=args.skip_warm))
        except AgentConfigError as exc:
            print(f"Configuration error: {exc}", file=sys.stderr)
            sys.exit(2)
    write_csv(rows, args.out)
    print(f"\nSaved {len(rows)} rows to {args.out} (numbers and counts only).")
    print("LLM cost: not tracked here.")


if __name__ == "__main__":
    main()
