"""Verifier: build facts from raw outcomes, cross-check them, and decide whether to retry.

Deterministic. Retries only calls that failed with a retryable error, at most
`max_verifier_loops` times. Whatever is still missing becomes an explicit gap in the report.
"""

from datetime import date
from typing import Any

from ukvet_agent.facts import FAILED_STATUSES, build_facts
from ukvet_agent.mcp_client import ToolOutcome
from ukvet_agent.schemas import Gap
from ukvet_agent.settings import AgentSettings


def check_consistency(raw: dict[str, ToolOutcome]) -> list[str]:
    """Cross-check endpoints that should agree; disagreements become data-quality notes."""
    notes: list[str] = []
    profile, charges, insolvency = raw.get("profile"), raw.get("charges"), raw.get("insolvency")
    if profile is None or not profile.ok:
        return notes
    p = profile.data

    if charges is not None and charges.ok:
        if p.get("has_charges") is True and not charges.found:
            notes.append(
                "The company profile says charges exist, but the charges list returned none."
            )
        if p.get("has_charges") is False and charges.found:
            notes.append(
                "The company profile says no charges exist, but the charges list returned some."
            )
    if insolvency is not None and insolvency.ok:
        if p.get("has_insolvency_history") is True and not insolvency.found:
            notes.append(
                "The company profile indicates insolvency history, but no insolvency record "
                "was returned."
            )
        if p.get("status") in FAILED_STATUSES and not insolvency.found:
            notes.append(
                f"The company status is '{p.get('status')}' but no insolvency record was returned."
            )
    return notes


def coverage_gaps(gaps: list[Gap]) -> list[str]:
    """Distinct tool keys of retryable gaps, in order."""
    return list(dict.fromkeys(g.tool for g in gaps if g.retryable))


def verify_node(state: dict[str, Any], settings: AgentSettings, today: date) -> dict[str, Any]:
    raw: dict[str, ToolOutcome] = state["raw"]
    facts, gaps = build_facts(
        raw,
        state["plan"],
        today=today,
        window_days=settings.changes_window_days,
        max_directors=settings.max_directors,
    )
    loops = int(state.get("loops") or 0)
    retry = coverage_gaps(gaps) if loops < settings.max_verifier_loops else []
    return {
        "facts": facts,
        "gaps": gaps,
        "notes": check_consistency(raw),
        "retry_keys": retry,
        "loops": loops + 1 if retry else loops,
    }
