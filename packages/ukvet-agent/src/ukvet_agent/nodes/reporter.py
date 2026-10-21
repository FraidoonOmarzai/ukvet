"""Reporter: red flags (rules), then narrative (LLM or template), then citation check.

The Reporter is the only LLM call in the system. It has no tools and cannot add facts. Whatever it
writes is checked claim by claim; invalid claims are dropped. If the LLM is off, times out, errors
or produces nothing valid, a deterministic template narrative built from the facts is used instead,
so a report is always produced.
"""

import asyncio
import logging
import re
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from ukvet_agent.citations import MAX_CLAIM_CHARS, Violation, check_claims
from ukvet_agent.llm import NarrativeDraft, NarrativeWriter
from ukvet_agent.mcp_client import ToolOutcome
from ukvet_agent.redflags import assessment_text, evaluate_red_flags, risk_level
from ukvet_agent.schemas import CitationStats, Claim, Fact, RedFlag, Report
from ukvet_agent.text import sanitise_registry_text

log = logging.getLogger("ukvet_agent.reporter")
_PROMPTS = Path(__file__).resolve().parent.parent / "prompts"
_PLACEHOLDER = re.compile(r"\{(\w+)\}")
MAX_FINDINGS = 8


def _fill(template: str, values: Mapping[str, str]) -> str:
    """Single-pass substitution so registry text containing '{x}' is never re-expanded."""
    return _PLACEHOLDER.sub(lambda m: values.get(m.group(1), m.group(0)), template)


def system_prompt() -> str:
    return (_PROMPTS / "reporter_system.md").read_text(encoding="utf-8")


def render_user_prompt(
    company_number: str, facts: list[Fact], flags: list[RedFlag], feedback: str = ""
) -> str:
    fact_lines = []
    for f in facts:
        line = f"[{f.id}] {f.statement}"
        if f.caveats:
            line += f" (caveats: {' '.join(f.caveats)})"
        fact_lines.append(line)
    flag_lines = [
        f"- [{fl.severity}] {fl.title} (facts: {', '.join(fl.fact_ids)})" for fl in flags
    ] or ["- none"]
    note = ""
    if feedback:
        note = f"\nYour previous answer had problems. Fix them and keep to the rules:\n{feedback}\n"
    template = (_PROMPTS / "reporter_user.md").read_text(encoding="utf-8")
    return _fill(
        template,
        {
            "company_number": company_number,
            "facts": "\n".join(fact_lines) or "(no facts available)",
            "flags": "\n".join(flag_lines),
            "feedback": note,
        },
    )


def _clip(text: str) -> str:
    return text if len(text) <= MAX_CLAIM_CHARS else text[: MAX_CLAIM_CHARS - 1].rstrip() + "…"


def template_narrative(
    facts: list[Fact], flags: list[RedFlag], number: str, name: str
) -> NarrativeDraft:
    """Deterministic fallback: states the facts as written, red-flag facts first."""
    by_id = {f.id: f for f in facts}
    q1 = by_id.get("Q1.status")
    if q1 is not None:
        headline = Claim(text=_clip(q1.statement), fact_ids=[q1.id])
    else:
        headline = Claim(
            text=f"Status information for {name} ({number}) could not be retrieved.", fact_ids=[]
        )
    flagged = [i for fl in flags for i in fl.fact_ids]  # every flag's evidence is shown
    order = list(dict.fromkeys([*flagged, *(f.id for f in facts)]))
    findings = [
        Claim(text=_clip(by_id[i].statement), fact_ids=[i])
        for i in order
        if i in by_id and i != "Q1.status"
    ][:MAX_FINDINGS]
    return NarrativeDraft(headline=headline, findings=findings)


async def _llm_narrative(
    writer: NarrativeWriter,
    number: str,
    facts: list[Fact],
    flags: list[RedFlag],
    timeout: float,
) -> tuple[NarrativeDraft | None, CitationStats]:
    by_id = {f.id: f for f in facts}
    stats = CitationStats()
    feedback = ""
    for attempt in range(2):
        user = render_user_prompt(number, facts, flags, feedback)
        try:
            draft = await asyncio.wait_for(writer.write(system_prompt(), user), timeout)
        except Exception as exc:  # LLM/network/schema failure: fall back, never crash
            log.warning("narrative attempt %d failed: %s", attempt + 1, type(exc).__name__)
            stats.violations.append(f"LLM error ({type(exc).__name__})")
            if attempt == 0:
                stats.retries = 1
            continue

        claims = [draft.headline, *draft.findings[:MAX_FINDINGS]]
        head = check_claims([draft.headline], by_id)
        rest = check_claims(draft.findings[:MAX_FINDINGS], by_id)
        violations: list[Violation] = [*head.violations, *rest.violations]
        stats.claims_total = len(claims)
        stats.claims_kept = len(head.kept) + len(rest.kept)
        stats.claims_dropped = stats.claims_total - stats.claims_kept
        stats.violations = [str(v) for v in violations]

        if head.kept and rest.kept and not violations:
            return NarrativeDraft(headline=head.kept[0], findings=rest.kept), stats
        if attempt == 0 and violations:
            stats.retries = 1
            feedback = "\n".join(f"- {v}" for v in violations[:6])
            continue
        if head.kept and rest.kept:
            return NarrativeDraft(headline=head.kept[0], findings=rest.kept), stats
        break
    return None, stats


async def report_node(
    state: dict[str, Any],
    writer: NarrativeWriter | None,
    now: datetime,
    llm_timeout_seconds: float,
) -> dict[str, Any]:
    facts: list[Fact] = state["facts"]
    gaps = state["gaps"]
    number: str = state["company_number"]
    raw: dict[str, ToolOutcome] = state.get("raw") or {}
    profile = raw.get("profile")
    name = sanitise_registry_text(
        profile.data.get("company_name")
        if profile is not None and profile.ok
        else state.get("company_name") or number
    )

    flags = evaluate_red_flags(facts)
    level = risk_level(flags, gaps)

    narrative: NarrativeDraft | None = None
    stats = CitationStats()
    if writer is not None and facts:
        narrative, stats = await _llm_narrative(writer, number, facts, flags, llm_timeout_seconds)
    source = "llm" if narrative is not None else "template"
    if narrative is None:
        narrative = template_narrative(facts, flags, number, name)

    report = Report(
        company_number=number,
        company_name=name,
        generated_at=now,
        risk_level=level,
        assessment=assessment_text(level, flags, gaps),
        headline=narrative.headline,
        findings=narrative.findings,
        red_flags=flags,
        facts=facts,
        gaps=gaps,
        data_quality_notes=list(state.get("notes") or []),
        narrative_source="llm" if source == "llm" else "template",
        model=writer.model_name if source == "llm" and writer is not None else None,
        citation_stats=stats,
    )
    return {"result": report}
