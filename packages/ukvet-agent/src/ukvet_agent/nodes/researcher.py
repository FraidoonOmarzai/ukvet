"""Researcher: gather raw tool outcomes. Deterministic: no LLM decides which tools to call.

Stage 1 runs the independent calls in parallel (profile, officers, PSC, charges, insolvency,
filings). Stage 2 looks up each current director's other appointments (needs the officer IDs from
stage 1). On a verifier retry only the failed calls are repeated.
"""

import asyncio
from datetime import date, timedelta
from typing import Any

from ukvet_agent.errors import CompanyNotFoundError
from ukvet_agent.facts import current_directors, needed_tools
from ukvet_agent.mcp_client import ToolClient, ToolOutcome
from ukvet_agent.settings import AgentSettings

APPOINTMENT_MAX_ITEMS = 50


def _args(
    key: str,
    number: str,
    officers: ToolOutcome | None,
    cutoff: date,
    settings: AgentSettings,
) -> tuple[str, dict[str, Any]]:
    if key.startswith("appointments."):
        index = int(key.split(".", 1)[1])
        directors = current_directors(officers)[: settings.max_directors]
        officer_id = directors[index - 1].get("officer_id") if index <= len(directors) else None
        return "get_officer_appointments", {
            "officer_id": officer_id or "",
            "exclude_company_number": number,
            "max_items": APPOINTMENT_MAX_ITEMS,
        }
    table: dict[str, tuple[str, dict[str, Any]]] = {
        "profile": ("get_company_profile", {"company_number": number}),
        "officers": ("get_officers", {"company_number": number, "include_resigned": True}),
        "psc": ("get_persons_with_significant_control", {"company_number": number}),
        "charges": ("get_charges", {"company_number": number}),
        "insolvency": ("get_insolvency", {"company_number": number}),
        "filings": (
            "get_filing_history",
            {"company_number": number, "since": cutoff.isoformat()},
        ),
    }
    return table[key]


async def _fetch(
    tools: ToolClient,
    keys: list[str],
    number: str,
    officers: ToolOutcome | None,
    cutoff: date,
    settings: AgentSettings,
) -> dict[str, ToolOutcome]:
    async def one(key: str) -> tuple[str, ToolOutcome]:
        name, arguments = _args(key, number, officers, cutoff, settings)
        if key.startswith("appointments.") and not arguments["officer_id"]:
            return key, ToolOutcome(ok=False, error="Officer has no officer_id; cannot look up")
        return key, await tools.call(name, arguments)

    return dict(await asyncio.gather(*(one(k) for k in keys)))


async def research_node(
    state: dict[str, Any], tools: ToolClient, settings: AgentSettings, today: date
) -> dict[str, Any]:
    number: str = state["company_number"]
    plan: list[str] = state["plan"]
    raw: dict[str, ToolOutcome] = dict(state.get("raw") or {})
    retry: set[str] = set(state.get("retry_keys") or [])
    cutoff = today - timedelta(days=settings.changes_window_days)

    stage1 = [k for k in needed_tools(plan) if not retry or k in retry]
    raw.update(await _fetch(tools, stage1, number, raw.get("officers"), cutoff, settings))

    profile = raw.get("profile")
    if profile is not None and not profile.ok and "not found" in (profile.error or "").lower():
        raise CompanyNotFoundError(f"No company with number {number}")

    officers = raw.get("officers")
    if "Q8" in plan and officers is not None and officers.ok:
        count = len(current_directors(officers)[: settings.max_directors])
        stage2 = [
            f"appointments.{i}"
            for i in range(1, count + 1)
            if f"appointments.{i}" in retry or f"appointments.{i}" not in raw
        ]
        raw.update(await _fetch(tools, stage2, number, officers, cutoff, settings))

    return {"raw": raw, "retry_keys": []}
