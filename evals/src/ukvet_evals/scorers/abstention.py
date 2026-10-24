"""M3: does ukvet admit what it could not check, without inventing or corrupting anything?

For each case the pipeline runs twice on the same frozen company: clean, and with faults injected.
A case PASSES only if every check below holds.
"""

from dataclasses import dataclass, field
from fnmatch import fnmatch
from typing import Any

from ukvet_agent.schemas import Report

from ukvet_evals.schema import AbstentionCase
from ukvet_evals.scorers.narrative import report_claim_errors


@dataclass
class CaseResult:
    case: str
    passed: bool
    failed_checks: list[str] = field(default_factory=list)
    detail: dict[str, Any] = field(default_factory=dict)


def expected_risk(report: Report) -> str:
    """The documented risk rule, restated independently (docs/04, 'risk level')."""
    severities = {f.severity for f in report.red_flags}
    if "high" in severities:
        return "high"
    if len({g.question_id for g in report.gaps}) >= 3:
        return "insufficient_data"
    if "medium" in severities:
        return "medium"
    return "low"


def score_case(case: AbstentionCase, clean: Report, faulty: Report) -> CaseResult:
    failed: list[str] = []
    detail: dict[str, Any] = {}

    # Gaps that already exist in the clean run (e.g. an officer whose appointments are not
    # recorded) are not caused by the fault, so they are subtracted.
    clean_gaps = {(g.question_id, g.tool) for g in clean.gaps}
    gap_qs = sorted(
        {g.question_id for g in faulty.gaps if (g.question_id, g.tool) not in clean_gaps}
    )
    detail["gap_questions"] = gap_qs
    if gap_qs != sorted(case.expected_gap_questions):
        failed.append(
            f"gap_questions: expected {sorted(case.expected_gap_questions)}, got {gap_qs}"
        )

    faulty_ids = {f.id for f in faulty.facts}
    for pattern in case.expected_absent_fact_ids:
        present = sorted(i for i in faulty_ids if fnmatch(i, pattern))
        if present:
            failed.append(f"fact must be absent but is present: {present}")

    clean_by_id = {f.id: f for f in clean.facts}
    faulty_by_id = {f.id: f for f in faulty.facts}
    for fid, fact in faulty_by_id.items():
        if fid not in clean_by_id:
            failed.append(f"invented fact {fid} (not in the clean run)")
        elif fact.value != clean_by_id[fid].value and not _network_partial(fid, case):
            failed.append(f"fact {fid} changed value under fault")
    for fid in clean_by_id:
        expected_absent = any(fnmatch(fid, p) for p in case.expected_absent_fact_ids)
        if fid not in faulty_by_id and not expected_absent:
            failed.append(f"fact {fid} disappeared but was not expected to")

    want = case.expected_risk or expected_risk(faulty)
    detail["risk"] = faulty.risk_level
    if faulty.risk_level != want:
        failed.append(f"risk_level: expected {want}, got {faulty.risk_level}")
    if case.expected_risk and expected_risk(faulty) != faulty.risk_level:
        failed.append("risk_level breaks the documented risk rule")

    if faulty.gaps and not (
        "could not be completed" in faulty.assessment or "not enough data" in faulty.assessment
    ):
        failed.append("assessment text does not mention the missing checks")

    for _text, errors in report_claim_errors(faulty):
        failed.extend(f"claim problem under fault: {err}" for err in errors)

    return CaseResult(case.id, not failed, failed, detail)


def _network_partial(fact_id: str, case: AbstentionCase) -> bool:
    """When some (not all) appointment lookups fail, the network summary legitimately changes."""
    return fact_id == "Q8.network" and any(
        f.tool == "get_officer_appointments" for f in case.faults
    )
