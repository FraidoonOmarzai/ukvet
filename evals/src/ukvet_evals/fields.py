"""The checkable fields per question, and extraction of them from a pipeline Report.

The oracle (oracle.py) produces the same keys from raw API JSON. A field is "correct" when the
pipeline's value equals the oracle's value after normalisation.
"""

from typing import Any

from ukvet_agent.schemas import Fact, Report

MISSING = "<missing>"

FIELDS: dict[str, list[str]] = {
    "Q1": ["Q1.status", "Q1.status_detail", "Q1.date_of_cessation"],
    "Q2": ["Q2.date_of_creation", "Q2.age_days"],
    "Q3": [
        "Q3.current_total",
        "Q3.director_count",
        "Q3.director_appointed_on",
        "Q3.other_officers",
    ],
    "Q4": [
        "Q4.accounts.overdue",
        "Q4.accounts.next_due",
        "Q4.accounts.last_made_up_to",
        "Q4.confirmation.overdue",
        "Q4.confirmation.next_due",
        "Q4.confirmation.last_made_up_to",
    ],
    "Q5": ["Q5.current_total", "Q5.corporate_count"],
    "Q6": ["Q6.outstanding", "Q6.part_satisfied", "Q6.satisfied", "Q6.total"],
    "Q7": ["Q7.case_count", "Q7.case_types"],
    "Q8": [
        "Q8.directors_checked",
        "Q8.directors_current",
        "Q8.other_companies",
        "Q8.status_counts",
        "Q8.per_director_other_totals",
    ],
    "Q9": ["Q9.appointed", "Q9.resigned", "Q9.address_changes"],
}


def question_of(field: str) -> str:
    return field.split(".", 1)[0]


def normalise(value: Any) -> Any:
    """Make values comparable: dates as strings, lists as given (sorting is done by the caller)."""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): normalise(v) for k, v in sorted(value.items())}
    if isinstance(value, list):
        return [normalise(v) for v in value]
    return value


def _val(facts: dict[str, Fact], fid: str) -> dict[str, Any] | None:
    fact = facts.get(fid)
    return fact.value if fact is not None else None


def extract_fields(report: Report) -> dict[str, Any]:
    """Pipeline-side values for every field in FIELDS (MISSING when the fact is absent)."""
    facts = {f.id: f for f in report.facts}
    out: dict[str, Any] = {}

    def put(keys: list[str], source: dict[str, Any] | None, getter: Any) -> None:
        for key in keys:
            out[key] = MISSING if source is None else normalise(getter(source, key))

    q1 = _val(facts, "Q1.status")
    put(
        FIELDS["Q1"],
        q1,
        lambda v, k: v.get(k.split(".", 1)[1]),
    )
    q2 = _val(facts, "Q2.age")
    put(
        FIELDS["Q2"],
        q2,
        lambda v, k: v.get(k.split(".", 1)[1]),
    )
    q3 = _val(facts, "Q3.officers_current")

    def q3get(v: dict[str, Any], k: str) -> Any:
        directors = v.get("directors", [])
        if k == "Q3.current_total":
            return v.get("current_total")
        if k == "Q3.director_count":
            return len(directors)
        if k == "Q3.director_appointed_on":
            return sorted(d.get("appointed_on") or "" for d in directors)
        return v.get("other_officers")

    put(FIELDS["Q3"], q3, q3get)

    for fid, prefix in (("Q4.accounts", "accounts"), ("Q4.confirmation_statement", "confirmation")):
        block = _val(facts, fid)
        for suffix in ("overdue", "next_due", "last_made_up_to"):
            out[f"Q4.{prefix}.{suffix}"] = (
                MISSING if block is None else normalise(block.get(suffix))
            )

    q5 = _val(facts, "Q5.control")
    put(
        FIELDS["Q5"],
        q5,
        lambda v, k: (
            v.get("current_total")
            if k == "Q5.current_total"
            else sum(1 for c in v.get("controllers", []) if c.get("is_corporate"))
        ),
    )
    q6 = _val(facts, "Q6.charges")
    put(FIELDS["Q6"], q6, lambda v, k: v.get(k.split(".", 1)[1]))
    q7 = _val(facts, "Q7.insolvency")
    put(
        FIELDS["Q7"],
        q7,
        lambda v, k: (
            v.get("case_count")
            if k == "Q7.case_count"
            else sorted(str(t) for t in v.get("case_types", []))
        ),
    )

    # Q8: the network fact exists only if at least one appointment lookup worked, or there are
    # no current directors at all (then the fact says so).
    net = _val(facts, "Q8.network")
    per_director = [
        facts[f"Q8.director.{i}"].value.get("other_total")
        for i in range(1, 50)
        if f"Q8.director.{i}" in facts
    ]

    def q8get(v: dict[str, Any], k: str) -> Any:
        if k == "Q8.directors_checked":
            return v.get("directors_checked", 0)
        if k == "Q8.directors_current":
            return v.get("directors_current", 0)
        if k == "Q8.other_companies":
            return v.get("other_companies", 0)
        if k == "Q8.status_counts":
            return dict(sorted((v.get("status_counts") or {}).items()))
        return per_director

    put(FIELDS["Q8"], net, q8get)

    q9o = _val(facts, "Q9.officer_changes")
    q9a = _val(facts, "Q9.address_changes")
    for key, src, name in (
        ("Q9.appointed", q9o, "appointed"),
        ("Q9.resigned", q9o, "resigned"),
        ("Q9.address_changes", q9a, "count"),
    ):
        out[key] = MISSING if src is None else src.get(name)
    return out
