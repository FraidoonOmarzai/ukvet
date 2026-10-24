"""Independent oracle: expected field values computed from RAW Companies House JSON.

INDEPENDENCE RULE: this module must not import ukvet_mcp or ukvet_agent. It re-derives every
value from the raw API shape using the definitions in docs/02-users-and-questions.md, so a bug in
the project's mappers or fact builders cannot hide behind a shared mistake. (`tests/evals` has a
test that fails if this module ever imports either package.)

Definitions worth knowing (also documented in evals/README.md):
- a "current officer" has no `resigned_on`; a "director" is a current officer whose role contains
  "director"; only the first MAX_DIRECTORS current directors are checked for Q8.
- a "current PSC" is not ceased (`ceased` true or a `ceased_on` date means ceased).
- Q9 window: `as_of - WINDOW_DAYS` inclusive; counts use all officers (any role, including
  resigned) and filing type AD01 for registered-office changes.
- lists are truncated to the same caps the pipeline applies (constants.py).
"""

import re
from datetime import date, timedelta
from typing import Any

from ukvet_evals.constants import (
    MAX_APPOINTMENTS,
    MAX_DIRECTORS,
    MAX_LIST_ITEMS,
    WINDOW_DAYS,
)
from ukvet_evals.snapshot import Snapshot

Raw = dict[str, Any]
_OFFICER_PATH = re.compile(r"^/officers/([^/]+)/appointments$")


def _body(snap: Snapshot, key: str) -> Raw:
    ep = snap.endpoints.get(key)
    if ep is None or ep.status != 200 or not isinstance(ep.body, dict):
        return {}
    return ep.body


def _items(body: Raw, cap: int | None = None) -> list[Raw]:
    items = [i for i in body.get("items", []) if isinstance(i, dict)]
    return items if cap is None else items[:cap]


def _d(value: Any) -> date | None:
    try:
        return date.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        return None


def _is_director(officer: Raw) -> bool:
    return "director" in str(officer.get("officer_role") or "unknown")


def current_officers(snap: Snapshot) -> list[Raw]:
    return [o for o in _items(_body(snap, "officers"), MAX_LIST_ITEMS) if not o.get("resigned_on")]


def current_directors(snap: Snapshot) -> list[Raw]:
    return [o for o in current_officers(snap) if _is_director(o)]


def officer_id(officer: Raw) -> str | None:
    link = ((officer.get("links") or {}).get("officer") or {}).get("appointments")
    m = _OFFICER_PATH.match(link) if isinstance(link, str) else None
    return m.group(1) if m else None


def oracle_fields(snap: Snapshot, as_of: date) -> dict[str, Any]:
    out: dict[str, Any] = {}
    profile = _body(snap, "profile")

    # ---- Q1, Q2 -----------------------------------------------------------------------------
    out["Q1.status"] = profile.get("company_status")
    out["Q1.status_detail"] = profile.get("company_status_detail")
    ceased = _d(profile.get("date_of_cessation"))
    out["Q1.date_of_cessation"] = ceased.isoformat() if ceased else None
    created = _d(profile.get("date_of_creation"))
    out["Q2.date_of_creation"] = created.isoformat() if created else None
    out["Q2.age_days"] = max(0, ((ceased or as_of) - created).days) if created else None

    # ---- Q3 ---------------------------------------------------------------------------------
    current = current_officers(snap)
    directors = [o for o in current if _is_director(o)]
    out["Q3.current_total"] = len(current)
    out["Q3.director_count"] = len(directors)
    out["Q3.director_appointed_on"] = sorted(o.get("appointed_on") or "" for o in directors)
    out["Q3.other_officers"] = len(current) - len(directors)

    # ---- Q4 ---------------------------------------------------------------------------------
    acc = profile.get("accounts") or {}
    con = profile.get("confirmation_statement") or {}
    out["Q4.accounts.overdue"] = acc.get("overdue")
    out["Q4.accounts.next_due"] = acc.get("next_due")
    out["Q4.accounts.last_made_up_to"] = (acc.get("last_accounts") or {}).get("made_up_to")
    out["Q4.confirmation.overdue"] = con.get("overdue")
    out["Q4.confirmation.next_due"] = con.get("next_due")
    out["Q4.confirmation.last_made_up_to"] = con.get("last_made_up_to")

    # ---- Q5 ---------------------------------------------------------------------------------
    pscs = [
        p
        for p in _items(_body(snap, "psc"), MAX_LIST_ITEMS)
        if not (p.get("ceased") or p.get("ceased_on"))
    ]
    out["Q5.current_total"] = len(pscs)
    out["Q5.corporate_count"] = sum(
        1
        for p in pscs
        if "corporate-entity" in str(p.get("kind")) or "legal-person" in str(p.get("kind"))
    )

    # ---- Q6 ---------------------------------------------------------------------------------
    cbody = _body(snap, "charges")
    charges = _items(cbody, MAX_LIST_ITEMS)
    statuses = [c.get("status") for c in charges]
    out["Q6.outstanding"] = statuses.count("outstanding")
    out["Q6.part_satisfied"] = statuses.count("part-satisfied")
    out["Q6.satisfied"] = statuses.count("fully-satisfied") + statuses.count("satisfied")
    total = cbody.get("total_count")
    out["Q6.total"] = total if isinstance(total, int) else len(charges)

    # ---- Q7 ---------------------------------------------------------------------------------
    cases = [c for c in _body(snap, "insolvency").get("cases", []) if isinstance(c, dict)]
    out["Q7.case_count"] = len(cases)
    out["Q7.case_types"] = sorted(str(c.get("type") or "unknown") for c in cases)

    # ---- Q8 ---------------------------------------------------------------------------------
    checked_totals: list[int] = []
    merged: dict[str, str] = {}
    for director in directors[:MAX_DIRECTORS]:
        oid = officer_id(director)
        ep = snap.appointments.get(oid) if oid else None
        if ep is None or ep.status != 200 or not isinstance(ep.body, dict):
            continue  # lookup impossible: the pipeline records a gap, the oracle skips it
        own = str(snap.meta.company_number)
        appts = [
            a
            for a in _items(ep.body, MAX_APPOINTMENTS)
            if str((a.get("appointed_to") or {}).get("company_number")) != own
        ]
        checked_totals.append(len(appts))
        for a in appts:
            target = a.get("appointed_to") or {}
            merged.setdefault(
                str(target.get("company_number")), target.get("company_status") or "unknown"
            )
    counts: dict[str, int] = {}
    for status in merged.values():
        counts[status] = counts.get(status, 0) + 1
    out["Q8.directors_checked"] = len(checked_totals)
    out["Q8.directors_current"] = len(directors)
    out["Q8.other_companies"] = len(merged)
    out["Q8.status_counts"] = dict(sorted(counts.items()))
    out["Q8.per_director_other_totals"] = checked_totals

    # ---- Q9 ---------------------------------------------------------------------------------
    start = (as_of - timedelta(days=WINDOW_DAYS)).isoformat()
    everyone = _items(_body(snap, "officers"), MAX_LIST_ITEMS)
    out["Q9.appointed"] = sum(1 for o in everyone if (o.get("appointed_on") or "") >= start)
    out["Q9.resigned"] = sum(1 for o in everyone if (o.get("resigned_on") or "") >= start)
    out["Q9.address_changes"] = sum(
        1
        for f in _items(_body(snap, "filings"))
        if f.get("type") == "AD01" and (f.get("date") or "") >= start
    )
    return out
