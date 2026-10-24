"""Tool outcomes -> tagged `Fact`s (Q1-Q9) and explicit `Gap`s.

Everything the report may say is a Fact built here, deterministically. Each fact has a stable ID,
a canonical statement, a structured value and a source. "No data" results become facts ("No
charges are registered"); failures become gaps. Nothing is ever guessed.
"""

from collections import Counter
from datetime import date, timedelta
from typing import Any

from ukvet_agent.mcp_client import ToolOutcome
from ukvet_agent.schemas import Fact, Gap, SourceRef
from ukvet_agent.text import fact_tokens, fmt_date, plural, sanitise_registry_text

FAILED_STATUSES = frozenset(
    {
        "liquidation",
        "administration",
        "receivership",
        "voluntary-arrangement",
        "insolvency-proceedings",
    }
)
MAX_LISTED = 8

# Which tool outcomes each question depends on.
QUESTION_TOOLS: dict[str, tuple[str, ...]] = {
    "Q1": ("profile",),
    "Q2": ("profile",),
    "Q3": ("officers",),
    "Q4": ("profile",),
    "Q5": ("psc",),
    "Q6": ("charges",),
    "Q7": ("insolvency",),
    "Q8": ("officers", "appointments"),
    "Q9": ("officers", "filings"),
}
_SAME_PERSON_CAVEAT = (
    "Appointments are matched by officer ID; the same person can have several IDs, "
    "so this may be incomplete."
)


def needed_tools(plan: list[str]) -> list[str]:
    """Tool keys (excluding per-director appointments) required by the planned questions."""
    keys: list[str] = []
    for q in plan:
        for tool in QUESTION_TOOLS.get(q, ()):
            if tool != "appointments" and tool not in keys:
                keys.append(tool)
    return keys


def _sources(outcome: ToolOutcome | None) -> list[SourceRef]:
    if outcome is None or not outcome.source:
        return []
    keys = ("endpoint", "url", "retrieved_at")
    return [SourceRef(**{k: outcome.source[k] for k in keys})]


def _make(
    fact_id: str,
    question_id: str,
    statement: str,
    value: dict[str, Any],
    outcomes: list[ToolOutcome | None],
    *,
    extra_numbers: tuple[object, ...] = (),
    extra_dates: tuple[str, ...] = (),
) -> Fact:
    tokens = fact_tokens(statement, extra_numbers, extra_dates)
    sources: list[SourceRef] = []
    caveats: list[str] = []
    for o in outcomes:
        sources.extend(_sources(o))
        if o is not None:
            caveats.extend(o.notes)
    return Fact(
        id=fact_id,
        question_id=question_id,
        statement=statement,
        value=value,
        caveats=list(dict.fromkeys(caveats)),
        sources=sources,
        dates=sorted(tokens.dates),
        numbers=sorted(tokens.numbers),
    )


def _s(value: object) -> str:
    return sanitise_registry_text(value)


def _humanise(slug: object) -> str:
    return str(slug).replace("-", " ").replace("_", " ")


def current_directors(officers: ToolOutcome | None) -> list[dict[str, Any]]:
    """Current officers whose role is a director, in the order the API returned them."""
    if officers is None or not officers.ok:
        return []
    items = officers.data.get("items", [])
    return [o for o in items if o.get("is_active") and "director" in str(o.get("role", ""))]


def _ok(outcome: ToolOutcome | None) -> bool:
    return outcome is not None and outcome.ok


def _gap(question_id: str, tool: str, outcome: ToolOutcome | None) -> Gap:
    if outcome is None:
        return Gap(
            question_id=question_id,
            tool=tool,
            reason="Data was not retrieved.",
            retryable=True,
        )
    return Gap(
        question_id=question_id,
        tool=tool,
        reason=sanitise_registry_text(outcome.error or "Tool call failed.", 300),
        retryable=outcome.retryable,
    )


# ---- per-question builders ---------------------------------------------------------------------


def _q1(profile: ToolOutcome) -> Fact:
    p = profile.data
    name, number = _s(p.get("company_name")), _s(p.get("company_number"))
    status, detail, ceased = (
        p.get("status"),
        p.get("status_detail"),
        p.get("date_of_cessation"),
    )
    stmt = (
        f"{name} ({number}) has status '{status}'"
        if status
        else f"{name} ({number}) has no status recorded"
    )
    if detail:
        stmt += f" (detail: {_s(detail)})"
    if ceased:
        stmt += f"; it ceased on {fmt_date(ceased)}"
    return _make(
        "Q1.status",
        "Q1",
        stmt,
        {
            "status": status,
            "status_detail": detail,
            "date_of_cessation": ceased,
            "company_number": number,
        },
        [profile],
        extra_numbers=(number,),
        extra_dates=(ceased,) if ceased else (),
    )


def _q2(profile: ToolOutcome) -> Fact:
    p = profile.data
    created, days, years = (
        p.get("date_of_creation"),
        p.get("age_days"),
        p.get("age_years"),
    )
    if not (created and days is not None and years is not None):
        return _make(
            "Q2.age",
            "Q2",
            "The incorporation date is not recorded",
            {"date_of_creation": None},
            [profile],
        )
    whole = int(days // 365.25)
    months = int((days - whole * 365.25) // 30.4375)
    ceased_note = " at cessation" if p.get("date_of_cessation") else ""
    stmt = f"Incorporated on {fmt_date(created)}; age{ceased_note} {years} years ({days} days)"
    return _make(
        "Q2.age",
        "Q2",
        stmt,
        {"date_of_creation": created, "age_days": days, "age_years": years},
        [profile],
        extra_numbers=(whole, months, round(years)),
        extra_dates=(created,),
    )


def _q4(profile: ToolOutcome) -> list[Fact]:
    p = profile.data
    facts: list[Fact] = []
    for fid, label, block in (
        ("Q4.accounts", "Accounts", p.get("accounts") or {}),
        (
            "Q4.confirmation_statement",
            "The confirmation statement",
            p.get("confirmation_statement") or {},
        ),
    ):
        overdue = block.get("overdue")
        state = (
            "overdue"
            if overdue is True
            else "not overdue"
            if overdue is False
            else "of unknown overdue status"
        )
        verb = "are" if label == "Accounts" else "is"
        stmt = (
            f"{label} {verb} {state}; next due {fmt_date(block.get('next_due'))}; "
            f"last made up to {fmt_date(block.get('last_made_up_to'))}"
        )
        dates = tuple(d for d in (block.get("next_due"), block.get("last_made_up_to")) if d)
        facts.append(_make(fid, "Q4", stmt, {**block}, [profile], extra_dates=dates))
    return facts


def _q3(officers: ToolOutcome) -> Fact:
    items = officers.data.get("items", [])
    current = [o for o in items if o.get("is_active")]
    directors = [o for o in current if "director" in str(o.get("role", ""))]
    others = len(current) - len(directors)
    if not current:
        stmt = "No current officers are recorded"
    else:
        listed = [
            _s(o.get("name"))
            + (f" (appointed {fmt_date(o['appointed_on'])})" if o.get("appointed_on") else "")
            for o in directors[:MAX_LISTED]
        ]
        extra = f" and {len(directors) - MAX_LISTED} more" if len(directors) > MAX_LISTED else ""
        names = f" ({'; '.join(listed)}{extra})" if listed else ""
        stmt = (
            f"{plural(len(current), 'current officer')}: "
            f"{plural(len(directors), 'director')}{names} "
            f"and {plural(others, 'other officer')}"
        )
    dates = tuple(o["appointed_on"] for o in directors[:MAX_LISTED] if o.get("appointed_on"))
    return _make(
        "Q3.officers_current",
        "Q3",
        stmt,
        {
            "current_total": len(current),
            "directors": [
                {"name": _s(o.get("name")), "appointed_on": o.get("appointed_on")}
                for o in directors
            ],
            "other_officers": others,
        },
        [officers],
        extra_dates=dates,
    )


def _q5(psc: ToolOutcome) -> Fact:
    items = psc.data.get("items", [])
    if not items:
        stmt = (
            "No current person with significant control is on record "
            "(this does not prove the company has no owner)"
        )
        value: dict[str, Any] = {"current_total": 0, "controllers": []}
    else:
        parts = []
        for c in items[:6]:
            kind = "company" if c.get("is_corporate") else "individual"
            natures = (
                ", ".join(_humanise(n) for n in c.get("natures_of_control", []))
                or "nature not stated"
            )
            parts.append(f"{_s(c.get('name'))} ({kind}; {natures})")
        more = f" and {len(items) - 6} more" if len(items) > 6 else ""
        stmt = (
            f"{plural(len(items), 'current person')} with significant control: "
            f"{'; '.join(parts)}{more}"
        )
        value = {
            "current_total": len(items),
            "controllers": [
                {"name": _s(c.get("name")), "is_corporate": bool(c.get("is_corporate"))}
                for c in items
            ],
        }
    return _make("Q5.control", "Q5", stmt, value, [psc])


def _q6(charges: ToolOutcome) -> Fact:
    d = charges.data
    out = d.get("outstanding_count", 0)
    part = d.get("part_satisfied_count", 0)
    sat = d.get("satisfied_count", 0)
    total = d.get("total") if d.get("total") is not None else d.get("returned", 0)
    if not charges.found:
        stmt = "No charges are registered against the company"
    else:
        stmt = (
            f"{out} outstanding, {part} part-satisfied and {sat} satisfied charges are "
            f"registered ({total} in total)"
        )
    return _make(
        "Q6.charges",
        "Q6",
        stmt,
        {"outstanding": out, "part_satisfied": part, "satisfied": sat, "total": total},
        [charges],
    )


def _q7(insolvency: ToolOutcome) -> Fact:
    d = insolvency.data
    cases = d.get("cases", [])
    if not insolvency.found or not cases:
        return _make(
            "Q7.insolvency",
            "Q7",
            "No insolvency record is held for the company",
            {"case_count": 0, "statuses": [], "case_types": []},
            [insolvency],
        )
    types = [_humanise(c.get("type")) for c in cases]
    dates: list[str] = []
    detail = []
    for c in cases[:4]:
        for dt in c.get("dates", []):
            if dt.get("date"):
                dates.append(dt["date"])
                detail.append(f"{_humanise(dt.get('type'))} {fmt_date(dt['date'])}")
    stmt = f"{plural(len(cases), 'insolvency case')} on record: {', '.join(types)}"
    if d.get("statuses"):
        stmt += f"; status: {', '.join(_humanise(s) for s in d['statuses'])}"
    if detail:
        stmt += f"; dates: {'; '.join(detail[:6])}"
    return _make(
        "Q7.insolvency",
        "Q7",
        stmt,
        {
            "case_count": len(cases),
            "statuses": d.get("statuses", []),
            "case_types": [c.get("type") for c in cases],
        },
        [insolvency],
        extra_dates=tuple(dates),
    )


def _q8(
    officers: ToolOutcome, appointments: dict[int, ToolOutcome], max_directors: int
) -> tuple[list[Fact], list[Gap]]:
    directors = current_directors(officers)
    facts: list[Fact] = []
    gaps: list[Gap] = []
    checked = directors[:max_directors]

    if not directors:
        facts.append(
            _make(
                "Q8.network",
                "Q8",
                "There are no current directors to check for other appointments",
                {"directors_checked": 0, "directors_current": 0},
                [officers],
            )
        )
        return facts, gaps

    merged: dict[str, str] = {}
    ok_outcomes: list[ToolOutcome | None] = []
    for i, director in enumerate(checked, start=1):
        outcome = appointments.get(i)
        if outcome is None or not outcome.ok:
            gaps.append(_gap("Q8", f"appointments.{i}", outcome))
            continue
        ok_outcomes.append(outcome)
        items = outcome.data.get("items", [])
        counts = Counter((a.get("company_status") or "unknown") for a in items)
        name = _s(director.get("name"))
        if not items:
            stmt = f"{name} has no other appointments on record"
        else:
            breakdown = ", ".join(f"{n} {_humanise(s)}" for s, n in counts.most_common())
            stmt = f"{name} has {plural(len(items), 'other appointment')}: {breakdown}"
        for a in items:
            merged.setdefault(a["company_number"], a.get("company_status") or "unknown")
        fact = _make(
            f"Q8.director.{i}",
            "Q8",
            stmt,
            {
                "director": name,
                "other_total": len(items),
                "status_counts": dict(counts),
                "companies": [
                    {
                        "company_number": a["company_number"],
                        "status": a.get("company_status"),
                    }
                    for a in items
                ],
            },
            [outcome],
        )
        fact.caveats = list(dict.fromkeys([*fact.caveats, _SAME_PERSON_CAVEAT]))
        facts.append(fact)

    if ok_outcomes:
        net_counts = Counter(merged.values())
        breakdown = ", ".join(f"{n} {_humanise(s)}" for s, n in net_counts.most_common()) or "none"
        stmt = (
            f"Across {plural(len(ok_outcomes), 'current director')} checked, "
            f"{plural(len(merged), 'other company', 'other companies')} were found ({breakdown})"
        )
        net = _make(
            "Q8.network",
            "Q8",
            stmt,
            {
                "directors_checked": len(ok_outcomes),
                "directors_current": len(directors),
                "other_companies": len(merged),
                "status_counts": dict(net_counts),
            },
            list(ok_outcomes),
            extra_numbers=(len(directors),),
        )
        extra = [_SAME_PERSON_CAVEAT]
        if len(directors) > len(checked):
            extra.append(
                f"Only the first {len(checked)} of {len(directors)} current directors were checked."
            )
        if len(ok_outcomes) < len(checked):
            extra.append(
                f"Appointments could not be retrieved for {len(checked) - len(ok_outcomes)} of "
                f"{len(checked)} directors checked, so this is incomplete."
            )
        net.caveats = list(dict.fromkeys([*net.caveats, *extra]))
        facts.append(net)
    return facts, gaps


def _q9_officers(officers: ToolOutcome, cutoff: date) -> Fact:
    iso = cutoff.isoformat()
    items = officers.data.get("items", [])
    counted = [o for o in items if "secretary" not in str(o.get("role", ""))]
    counted_appointed = [o for o in counted if (o.get("appointed_on") or "") >= iso]
    counted_resigned = [o for o in counted if (o.get("resigned_on") or "") >= iso]
    appointed = [o for o in items if (o.get("appointed_on") or "") >= iso]
    resigned = [o for o in items if (o.get("resigned_on") or "") >= iso]
    if not appointed and not resigned:
        stmt = f"No officer appointments or resignations since {fmt_date(iso)}"
    else:
        bits = [
            f"{plural(len(appointed), 'officer appointment')} and "
            f"{plural(len(resigned), 'resignation')} since {fmt_date(iso)}"
        ]
        for o in appointed[:MAX_LISTED]:
            bits.append(
                f"appointed: {_s(o.get('name'))} "
                f"({o.get('role')}, {fmt_date(o.get('appointed_on'))})"
            )
        for o in resigned[:MAX_LISTED]:
            bits.append(
                f"resigned: {_s(o.get('name'))} ({o.get('role')}, {fmt_date(o.get('resigned_on'))})"
            )
        stmt = "; ".join(bits)
    dates = tuple(
        d
        for o in [*appointed, *resigned][: MAX_LISTED * 2]
        for d in (o.get("appointed_on"), o.get("resigned_on"))
        if d and d >= iso
    )
    return _make(
        "Q9.officer_changes",
        "Q9",
        stmt,
        {
            "appointed": len(appointed),
            "resigned": len(resigned),
            "window_start": iso,
            "appointed_dates": [o.get("appointed_on") for o in appointed if o.get("appointed_on")],
            "turnover_appointed_dates": [
                o["appointed_on"] for o in counted_appointed if o.get("appointed_on")
            ],
            "turnover_resigned": len(counted_resigned),
        },
        [officers],
        extra_dates=(iso, *dates),
    )


def _q9_address(filings: ToolOutcome, cutoff: date) -> Fact:
    iso = cutoff.isoformat()
    changes = [
        f
        for f in filings.data.get("items", [])
        if f.get("is_address_change") and (f.get("date") or "") >= iso
    ]
    if not changes:
        stmt = f"No registered office address changes were filed since {fmt_date(iso)}"
    else:
        dates = [fmt_date(f["date"]) for f in changes[:MAX_LISTED]]
        stmt = (
            f"{plural(len(changes), 'registered office address change')} filed since "
            f"{fmt_date(iso)}: {', '.join(dates)}"
        )
    return _make(
        "Q9.address_changes",
        "Q9",
        stmt,
        {
            "count": len(changes),
            "dates": [f["date"] for f in changes],
            "window_start": iso,
        },
        [filings],
        extra_dates=(iso, *[f["date"] for f in changes[:MAX_LISTED]]),
    )


# ---- entry point ---------------------------------------------------------------------------------


def build_facts(
    raw: dict[str, ToolOutcome],
    plan: list[str],
    *,
    today: date,
    window_days: int,
    max_directors: int,
) -> tuple[list[Fact], list[Gap]]:
    """Build every fact the planned questions allow, and a gap for everything else."""
    facts: list[Fact] = []
    gaps: list[Gap] = []
    cutoff = today - timedelta(days=window_days)

    profile = raw.get("profile")
    profile_qs = [q for q in ("Q1", "Q2", "Q4") if q in plan]
    if profile_qs:
        if profile is not None and profile.ok:
            if "Q1" in plan:
                facts.append(_q1(profile))
            if "Q2" in plan:
                facts.append(_q2(profile))
            if "Q4" in plan:
                facts.extend(_q4(profile))
        else:
            gaps.extend(_gap(q, "profile", profile) for q in profile_qs)

    officers = raw.get("officers")
    officers_ok = officers is not None and officers.ok
    if "Q3" in plan:
        if officers is not None and officers.ok:
            facts.append(_q3(officers))
        else:
            gaps.append(_gap("Q3", "officers", officers))

    for q, tool, builder in (
        ("Q5", "psc", _q5),
        ("Q6", "charges", _q6),
        ("Q7", "insolvency", _q7),
    ):
        if q in plan:
            outcome = raw.get(tool)
            if outcome is not None and outcome.ok:
                facts.append(builder(outcome))
            else:
                gaps.append(_gap(q, tool, outcome))

    if "Q8" in plan:
        if officers is not None and officers_ok:
            appts = {
                int(k.split(".")[1]): v for k, v in raw.items() if k.startswith("appointments.")
            }
            q8_facts, q8_gaps = _q8(officers, appts, max_directors)
            facts.extend(q8_facts)
            gaps.extend(q8_gaps)
        else:
            gaps.append(_gap("Q8", "officers", officers))

    if "Q9" in plan:
        if officers is not None and officers_ok:
            facts.append(_q9_officers(officers, cutoff))
        else:
            gaps.append(_gap("Q9", "officers", officers))
        filings = raw.get("filings")
        if filings is not None and filings.ok:
            facts.append(_q9_address(filings, cutoff))
        else:
            gaps.append(_gap("Q9", "filings", filings))

    order = {q: i for i, q in enumerate(["Q1", "Q2", "Q3", "Q4", "Q5", "Q6", "Q7", "Q8", "Q9"])}
    facts.sort(key=lambda f: (order.get(f.question_id, 99), f.id))
    return facts, gaps
