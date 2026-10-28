"""M7, M8, M9 from a batch of LIVE reports (latency, cost, tool calls).

Replay timings exclude the network and say nothing about M7, so these numbers come from real runs
(`scripts/phase4_metrics.py`). This module only does the arithmetic, so it can be unit-tested.

Honesty rules baked in:
* the sample size is printed next to every number;
* a p95 from fewer than 20 runs is labelled "weak";
* cost is only reported when token prices were configured (we do not guess prices).
"""

import math
from collections.abc import Sequence
from statistics import mean, median
from typing import Any

from ukvet_agent.schemas import Report

TARGET_P95_MS = 30_000
TARGET_COST_GBP = 0.05
MIN_RUNS_FOR_P95 = 20


def percentile(values: Sequence[float], q: float) -> float | None:
    """Nearest-rank percentile (q in 0..100). None for an empty sample."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(q / 100 * len(ordered)))
    return ordered[min(rank, len(ordered)) - 1]


def summarise(reports: Sequence[Report]) -> dict[str, Any]:
    totals = [r.timings_ms.get("total", 0) for r in reports]
    n = len(reports)
    nodes = sorted({k for r in reports for k in r.timings_ms if k != "total"})
    costs = [r.usage.cost_gbp for r in reports if r.usage.cost_gbp is not None]
    llm = [r for r in reports if r.narrative_source == "llm"]
    p95 = percentile(totals, 95)
    mean_cost = mean(costs) if costs else None
    return {
        "reports": n,
        "m7_latency_ms": {
            "p50": percentile(totals, 50),
            "p95": p95,
            "worst": max(totals) if totals else None,
            "target_p95": TARGET_P95_MS,
            "met": None if p95 is None else p95 < TARGET_P95_MS,
            "weak": n < MIN_RUNS_FOR_P95,
        },
        "m8_cost_gbp": {
            "mean": mean_cost,
            "max": max(costs) if costs else None,
            "target": TARGET_COST_GBP,
            "met": None if mean_cost is None else mean_cost < TARGET_COST_GBP,
            "priced_reports": len(costs),
            "note": "" if costs else "no token prices set (UKVET_PRICE_IN/OUT_GBP_PER_MTOK)",
        },
        "m9_tool_calls": {
            "mean": mean(r.usage.tool_calls for r in reports) if reports else None,
            "median": median(r.usage.tool_calls for r in reports) if reports else None,
            "max": max((r.usage.tool_calls for r in reports), default=None),
            "target": "tracked (baseline only)",
        },
        "tokens": {
            "mean_input": mean(r.usage.input_tokens for r in reports) if reports else None,
            "mean_output": mean(r.usage.output_tokens for r in reports) if reports else None,
            "mean_llm_calls": mean(r.usage.llm_calls for r in reports) if reports else None,
        },
        "per_node_ms_mean": {
            k: round(mean(r.timings_ms.get(k, 0) for r in reports)) for k in nodes
        },
        "llm_reports": len(llm),
        "template_fallbacks": n - len(llm),
        "llm_retries": sum(r.citation_stats.retries for r in reports),
        "claims_dropped": sum(r.citation_stats.claims_dropped for r in reports),
    }


def _ms(v: float | None) -> str:
    return "n/a" if v is None else f"{v / 1000:.1f} s"


def render_markdown(s: dict[str, Any]) -> str:
    m7, m8, m9 = s["m7_latency_ms"], s["m8_cost_gbp"], s["m9_tool_calls"]

    def verdict(met: bool | None) -> str:
        return "n/a" if met is None else ("met" if met else "**MISSED**")

    weak = " (weak: fewer than 20 runs)" if m7["weak"] else ""
    cost = "n/a" if m8["mean"] is None else f"£{m8['mean']:.5f}"
    out = [
        f"# Phase 4 live metrics ({s['reports']} reports)\n",
        "| Metric | Target | Result | Verdict |\n|---|---|---|---|",
        f"| M7 latency p95 | < {TARGET_P95_MS // 1000} s | {_ms(m7['p95'])}{weak} "
        f"(p50 {_ms(m7['p50'])}, worst {_ms(m7['worst'])}) | {verdict(m7['met'])} |",
        f"| M8 mean cost per report | < £{TARGET_COST_GBP} | {cost} "
        f"over {m8['priced_reports']} priced reports | {verdict(m8['met'])} |",
        f"| M9 tool calls per report | {m9['target']} | mean {m9['mean']:.1f}, "
        f"median {m9['median']}, max {m9['max']} | baseline |"
        if s["reports"]
        else "| M9 | | no reports | |",
    ]
    if m8["note"]:
        out.append(f"\nNote: {m8['note']}.")
    t = s["tokens"]
    if s["reports"]:
        out.append(
            f"\nTokens per report: mean {t['mean_input']:.0f} in, {t['mean_output']:.0f} out, "
            f"{t['mean_llm_calls']:.1f} LLM calls."
        )
    out.append("\n## Where the time goes (mean per node)\n")
    out += [f"- {k}: {v} ms" for k, v in s["per_node_ms_mean"].items()]
    out.append(
        f"\nNarrative: {s['llm_reports']} written by the LLM, {s['template_fallbacks']} fell back "
        f"to the template; {s['llm_retries']} retries; {s['claims_dropped']} claims dropped by "
        "the checker."
    )
    return "\n".join(out) + "\n"
