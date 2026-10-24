"""Helpers for the evaluation-harness tests (importable as `evals_helpers`)."""

import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ukvet_agent.schemas import CitationStats, Claim, Fact, Gap, RedFlag, Report

REPO = Path(__file__).resolve().parents[2]


def make_root(tmp_path: Path) -> Path:
    """A throw-away repo root holding what the demo builder and recorder need."""
    (tmp_path / "tests" / "fixtures").mkdir(parents=True)
    shutil.copytree(REPO / "tests" / "fixtures" / "ch", tmp_path / "tests" / "fixtures" / "ch")
    (tmp_path / "scripts").mkdir()
    shutil.copy(REPO / "scripts" / "anonymise.py", tmp_path / "scripts" / "anonymise.py")
    return tmp_path


def fact(fid: str, statement: str, **value: Any) -> Fact:
    return Fact(id=fid, question_id=fid.split(".")[0], statement=statement, value=value)


def report(
    facts: list[Fact] | None = None,
    headline: Claim | None = None,
    findings: list[Claim] | None = None,
    gaps: list[Gap] | None = None,
    flags: list[RedFlag] | None = None,
    risk: str = "low",
    assessment: str = "ukvet's automated assessment: LOW risk.",
    stats: CitationStats | None = None,
    source: str = "template",
) -> Report:
    facts = (
        facts
        if facts is not None
        else [fact("Q1.status", "ACME LTD (12345678) has status 'active'", status="active")]
    )
    return Report(
        company_number="12345678",
        company_name="ACME LTD",
        generated_at=datetime(2026, 3, 4, tzinfo=UTC),
        risk_level=risk,  # type: ignore[arg-type]
        assessment=assessment,
        headline=headline or Claim(text="ACME LTD is active.", fact_ids=["Q1.status"]),
        findings=findings or [],
        red_flags=flags or [],
        facts=facts,
        gaps=gaps or [],
        data_quality_notes=[],
        narrative_source=source,  # type: ignore[arg-type]
        citation_stats=stats or CitationStats(),
    )
