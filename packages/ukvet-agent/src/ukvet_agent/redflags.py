"""Deterministic red-flag rules and the risk level.

Red flags come from RULES, not the LLM: they can be unit-tested, their recall is measurable (M5),
and the LLM cannot invent or hide one. Wording is neutral: it describes patterns in public records
and never implies wrongdoing by an individual.
"""

from datetime import date
from typing import Any

from ukvet_agent.facts import FAILED_STATUSES
from ukvet_agent.schemas import Fact, Gap, RedFlag, RiskLevel, Severity
from ukvet_agent.text import plural

PATTERN_NOTE = "This is a pattern in public records, not a finding about anyone's conduct."
_HEALTHY = {"active", "open", "registered"}


def _v(facts: dict[str, Fact], fact_id: str) -> dict[str, Any] | None:
    fact = facts.get(fact_id)
    return fact.value if fact else None


def _within_days(a: str, b: str, days: int) -> bool:
    try:
        return abs((date.fromisoformat(a) - date.fromisoformat(b)).days) <= days
    except ValueError:
        return False


def evaluate_red_flags(facts_list: list[Fact]) -> list[RedFlag]:
    facts = {f.id: f for f in facts_list}
    flags: list[RedFlag] = []

    def add(rid: str, severity: Severity, title: str, detail: str, *fact_ids: str) -> None:
        flags.append(
            RedFlag(id=rid, severity=severity, title=title, detail=detail, fact_ids=list(fact_ids))
        )

    q1 = _v(facts, "Q1.status")
    status = (q1 or {}).get("status")
    is_active = status in _HEALTHY

    q7 = _v(facts, "Q7.insolvency")
    case_types = [str(t) for t in (q7 or {}).get("case_types") or []]
    # A members' voluntary liquidation is a solvent wind-up chosen by the directors, not distress.
    mvl_only = bool(case_types) and all("members-voluntary" in t for t in case_types)

    if q1 is not None and status:
        if status == "liquidation" and mvl_only:
            add(
                "status",
                "medium",
                "Company is in a members' voluntary liquidation",
                "This is a solvent wind-up: the directors declared the company can pay its debts. "
                "The company is closing down.",
                "Q1.status",
            )
        elif status == "dissolved":
            add(
                "status",
                "high",
                "Company is dissolved",
                "A dissolved company no longer exists as a legal entity and cannot trade.",
                "Q1.status",
            )
        elif status in FAILED_STATUSES:
            add(
                "status",
                "high",
                f"Company status is '{status}'",
                "The company is in a formal insolvency or restructuring process.",
                "Q1.status",
            )
        elif status not in _HEALTHY:
            add(
                "status",
                "medium",
                f"Company status is '{status}'",
                "The company is not recorded as active.",
                "Q1.status",
            )

    if (q1 or {}).get("status_detail") == "active-proposal-to-strike-off":
        add(
            "strike_off",
            "high",
            "Company has a proposal to be struck off the register",
            "Companies House has started the process to dissolve this company.",
            "Q1.status",
        )

    status_covers_mvl = mvl_only and status == "liquidation"  # avoid a duplicate flag
    if q7 and q7.get("case_count", 0) > 0 and not status_covers_mvl:
        add(
            "insolvency",
            "medium" if mvl_only else "high",
            "Members' voluntary liquidation on file (solvent wind-up)"
            if mvl_only
            else "Insolvency record on file",
            f"Companies House holds {plural(q7['case_count'], 'insolvency case')} "
            "for this company.",
            "Q7.insolvency",
        )

    q2 = _v(facts, "Q2.age")
    days = (q2 or {}).get("age_days")
    if is_active and isinstance(days, int):
        if days < 365:
            add(
                "age",
                "medium",
                "Company is less than a year old",
                "Very new companies have little track record to check.",
                "Q2.age",
            )
        elif days < 730:
            add(
                "age",
                "low",
                "Company is less than two years old",
                "Newer companies have a short track record.",
                "Q2.age",
            )

    for fid, rid, label in (
        ("Q4.accounts", "accounts_overdue", "Accounts"),
        ("Q4.confirmation_statement", "confirmation_overdue", "Confirmation statement"),
    ):
        block = _v(facts, fid)
        if block and block.get("overdue") is True:
            add(
                rid,
                "medium",
                f"{label} {'are' if label == 'Accounts' else 'is'} overdue",
                "Filings past their due date often signal administrative or financial strain.",
                fid,
            )

    q6 = _v(facts, "Q6.charges")
    if q6 and q6.get("outstanding", 0) > 0:
        add(
            "charges",
            "low",
            "Outstanding secured charges",
            f"{plural(q6['outstanding'], 'charge')} secured on company assets "
            "are outstanding. "
            "This is common and not necessarily negative.",
            "Q6.charges",
        )

    q8 = _v(facts, "Q8.network")
    if q8 and q8.get("other_companies", 0) > 0:
        counts = q8.get("status_counts", {})
        failed = sum(n for s, n in counts.items() if s in FAILED_STATUSES)
        dissolved = counts.get("dissolved", 0)
        if failed >= 3:
            add(
                "network",
                "high",
                "Directors linked to several companies in insolvency processes",
                f"Current directors have other appointments at {failed} companies now in "
                f"liquidation, administration or a similar process. {PATTERN_NOTE}",
                "Q8.network",
            )
        elif failed == 2:
            add(
                "network",
                "medium",
                "Directors linked to two companies in insolvency processes",
                f"Current directors have other appointments at 2 companies now in "
                f"liquidation, administration or a similar process. {PATTERN_NOTE}",
                "Q8.network",
            )
        elif failed == 1:
            add(
                "network",
                "low",
                "Directors linked to a company in an insolvency process",
                f"Current directors have other appointments at "
                f"{plural(failed, 'company', 'companies')} now in liquidation, administration "
                f"or a similar process (this can be a routine, solvent closure). {PATTERN_NOTE}",
                "Q8.network",
            )
        elif dissolved >= 5:
            add(
                "network",
                "low",
                "Directors linked to many dissolved companies",
                f"Current directors have other appointments at {dissolved} dissolved companies. "
                f"Dissolution is often routine. {PATTERN_NOTE}",
                "Q8.network",
            )

    q9 = _v(facts, "Q9.officer_changes")
    if q9:
        created = (_v(facts, "Q2.age") or {}).get("date_of_creation") or ""
        dates = q9.get("turnover_appointed_dates", q9.get("appointed_dates", []))
        resigned = q9.get("turnover_resigned", q9.get("resigned", 0))
        appointed = len(dates) if "turnover_appointed_dates" in q9 else q9.get("appointed", 0)
        formation = sum(1 for d in dates if created and _within_days(d, created, 30))
        changes = appointed - formation + resigned
        if changes >= 3:
            add(
                "officer_turnover",
                "medium",
                "Several officer changes recently",
                f"{changes} officer appointments or resignations were recorded recently.",
                "Q9.officer_changes",
            )
        elif changes == 2:
            add(
                "officer_turnover",
                "low",
                "Some officer changes recently",
                "2 officer appointments or resignations were recorded recently.",
                "Q9.officer_changes",
            )

    q9a = _v(facts, "Q9.address_changes")
    if q9a and q9a.get("count", 0) >= 2:
        add(
            "address_changes",
            "medium",
            "Registered office changed several times recently",
            f"The registered office address was changed {q9a['count']} times recently.",
            "Q9.address_changes",
        )

    q3 = _v(facts, "Q3.officers_current")
    if q3 is not None and is_active and not q3.get("directors"):
        add(
            "no_directors",
            "medium",
            "No current director is recorded",
            "An active company is expected to have at least one director on record.",
            "Q3.officers_current",
        )

    q5 = _v(facts, "Q5.control")
    if q5 is not None and is_active and q5.get("current_total", 0) == 0:
        add(
            "no_psc",
            "info",
            "No person with significant control on record",
            "This may be because the company is exempt or has filed a statement instead.",
            "Q5.control",
        )

    order = {"high": 0, "medium": 1, "low": 2, "info": 3}
    flags.sort(key=lambda f: order[f.severity])
    return flags


def risk_level(flags: list[RedFlag], gaps: list[Gap]) -> RiskLevel:
    """Overall level from the flags.

    A high-severity flag always wins (a dissolved company is high risk even if other checks
    failed). Otherwise, with three or more checks missing we cannot honestly say low or medium.
    """
    severities = {f.severity for f in flags}
    if "high" in severities:
        return "high"
    if len({g.question_id for g in gaps}) >= 3:
        return "insufficient_data"
    if "medium" in severities:
        return "medium"
    return "low"


ASSESSMENT_PREFIX = (
    "ukvet's automated assessment (an opinion generated from rules, not a statement of fact): "
)


def assessment_text(level: RiskLevel, flags: list[RedFlag], gaps: list[Gap]) -> str:
    """Deterministic, honest, labelled as opinion."""
    prefix = ASSESSMENT_PREFIX
    counted = [f for f in flags if f.severity != "info"]
    if level == "insufficient_data":
        body = (
            "there is not enough data to assess risk: "
            f"{len({g.question_id for g in gaps})} checks could not be completed."
        )
        if counted:
            body += f" Red flags found so far: {'; '.join(f.title for f in counted[:4])}."
        return prefix + body
    if not counted:
        body = f"{level.upper()} risk. No red flags were identified from the records checked."
    else:
        titles = "; ".join(f.title for f in counted[:4])
        more = f" and {len(counted) - 4} more" if len(counted) > 4 else ""
        body = f"{level.upper()} risk. {len(counted)} red flag(s): {titles}{more}."
    if gaps:
        body += f" {len({g.question_id for g in gaps})} check(s) could not be completed."
    return prefix + body
