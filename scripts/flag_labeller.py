"""Draft red-flag labels from the WRITTEN definitions in evals/LABELLING.md, then you review.

Independent of ukvet: this file imports nothing from ukvet_agent or ukvet_mcp and reads the raw
snapshots directly, so the labels do not come from the rules they grade. It is still one person's
(and one script's) reading of the definitions, so the final report must say "labels drafted by
script from the written definitions and reviewed by one person".

Usage (repo root):
    uv run python scripts/flag_labeller.py --dataset v0.1 --labeller FO          # review each company
    uv run python scripts/flag_labeller.py --dataset v0.1 --labeller FO --auto   # accept every draft
At each company: Enter = accept, `none` = expect no flags, `s` = skip, or type flags such as
`status:high,charges:low` to replace the draft. Do NOT run the evals until this is finished.
"""

from __future__ import annotations

import argparse
import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

FAILED = {
    "liquidation",
    "administration",
    "receivership",
    "voluntary-arrangement",
    "insolvency-proceedings",
}
OK_STATUS = {"active", "open", "registered"}
IDS = [
    "status",
    "strike_off",
    "insolvency",
    "age",
    "accounts_overdue",
    "confirmation_overdue",
    "charges",
    "network",
    "officer_turnover",
    "address_changes",
    "no_directors",
    "no_psc",
]
CAP = 100  # same list cap as the pipeline (constants.py), written out again on purpose


def body(snap: dict[str, Any], key: str) -> dict[str, Any]:
    ep = snap.get("endpoints", {}).get(key) or {}
    return ep["body"] if ep.get("status") == 200 and isinstance(ep.get("body"), dict) else {}


def d(value: Any) -> date | None:
    try:
        return date.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        return None


def is_mvl(case: dict[str, Any]) -> bool:
    return str(case.get("type") or "").startswith("members-voluntary")


def draft(snap: dict[str, Any]) -> tuple[list[tuple[str, str]], dict[str, Any]]:
    as_of = date.fromisoformat(snap["meta"]["as_of"])
    own = str(snap["meta"]["company_number"])
    prof = body(snap, "profile")
    status = prof.get("company_status") or "unknown"
    detail = prof.get("company_status_detail")
    created = d(prof.get("date_of_creation"))
    cases = [c for c in body(snap, "insolvency").get("cases", []) if isinstance(c, dict)]
    all_mvl = bool(cases) and all(is_mvl(c) for c in cases)
    officers = [o for o in body(snap, "officers").get("items", [])[:CAP] if isinstance(o, dict)]
    current = [o for o in officers if not o.get("resigned_on")]
    directors = [o for o in current if "director" in str(o.get("officer_role") or "unknown")]
    pscs = [
        p
        for p in body(snap, "psc").get("items", [])[:CAP]
        if isinstance(p, dict) and not (p.get("ceased") or p.get("ceased_on"))
    ]
    charges = [c for c in body(snap, "charges").get("items", [])[:CAP] if isinstance(c, dict)]
    outstanding = sum(1 for c in charges if c.get("status") == "outstanding")
    start = (as_of - timedelta(days=365)).isoformat()

    out: list[tuple[str, str]] = []
    # status
    if status == "dissolved":
        out.append(("status", "high"))
    elif status in FAILED:
        out.append(("status", "medium" if (status == "liquidation" and all_mvl) else "high"))
    elif status not in OK_STATUS:
        out.append(("status", "medium"))
    # strike_off
    if detail == "active-proposal-to-strike-off":
        out.append(("strike_off", "high"))
    # insolvency
    if cases and not (status == "liquidation" and all_mvl):
        out.append(("insolvency", "medium" if all_mvl else "high"))
    # age
    if status == "active" and created:
        age = (as_of - created).days
        if age < 365:
            out.append(("age", "medium"))
        elif age < 730:
            out.append(("age", "low"))
    # overdue
    if (prof.get("accounts") or {}).get("overdue") is True:
        out.append(("accounts_overdue", "medium"))
    if (prof.get("confirmation_statement") or {}).get("overdue") is True:
        out.append(("confirmation_overdue", "medium"))
    # charges
    if outstanding >= 1:
        out.append(("charges", "low"))
    # network
    merged: dict[str, str] = {}
    for director in directors[:5]:
        link = ((director.get("links") or {}).get("officer") or {}).get("appointments") or ""
        parts = link.split("/")
        oid = parts[2] if len(parts) > 2 else None
        ep = (snap.get("appointments") or {}).get(oid) if oid else None
        if not ep or ep.get("status") != 200 or not isinstance(ep.get("body"), dict):
            continue
        for a in ep["body"].get("items", []):
            target = (a or {}).get("appointed_to") or {}
            num = str(target.get("company_number"))
            if num != own:
                merged.setdefault(num, target.get("company_status") or "unknown")
    failed_n = sum(1 for s in merged.values() if s in FAILED)
    dissolved_n = sum(1 for s in merged.values() if s == "dissolved")
    if failed_n >= 3:
        out.append(("network", "high"))
    elif failed_n == 2:
        out.append(("network", "medium"))
    elif failed_n == 1:
        out.append(("network", "low"))
    elif dissolved_n >= 5:
        out.append(("network", "low"))

    # officer turnover (appointments within 30 days of incorporation do not count)
    def formation(o: dict[str, Any]) -> bool:
        a = d(o.get("appointed_on"))
        return bool(created and a and a <= created + timedelta(days=30))

    appointed = sum(
        1 for o in officers if (o.get("appointed_on") or "") >= start and not formation(o)
    )
    resigned = sum(1 for o in officers if (o.get("resigned_on") or "") >= start)
    turnover = appointed + resigned
    if turnover >= 3:
        out.append(("officer_turnover", "medium"))
    elif turnover == 2:
        out.append(("officer_turnover", "low"))
    # address changes
    ad01 = sum(
        1
        for f in body(snap, "filings").get("items", [])
        if isinstance(f, dict) and f.get("type") == "AD01" and (f.get("date") or "") >= start
    )
    if ad01 >= 2:
        out.append(("address_changes", "medium"))
    # directors and PSC
    if status == "active" and not directors:
        out.append(("no_directors", "medium"))
    if status == "active" and not pscs:
        out.append(("no_psc", "info"))

    facts = {
        "status": status,
        "detail": detail,
        "outstanding_charges": outstanding,
        "insolvency_cases": len(cases),
        "linked_failed": failed_n,
        "linked_dissolved": dissolved_n,
        "turnover_12m": turnover,
        "AD01_12m": ad01,
        "directors": len(directors),
        "psc": len(pscs),
    }
    return out, facts


def parse_override(text: str) -> list[tuple[str, str | None]] | None:
    out: list[tuple[str, str | None]] = []
    for part in text.split(","):
        fid, _, sev = part.strip().partition(":")
        if fid not in IDS:
            print(f"    unknown flag id {fid!r}; valid: {', '.join(IDS)}")
            return None
        out.append((fid, sev or None))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="v0.1")
    ap.add_argument("--labeller", default="")
    ap.add_argument("--auto", action="store_true", help="accept every draft without asking")
    ap.add_argument("--only", nargs="*", help="limit to these aliases")
    args = ap.parse_args()

    ds = Path(f"evals/datasets/{args.dataset}")
    companies = [
        json.loads(x)
        for x in (ds / "companies.jsonl").read_text(encoding="utf-8").splitlines()
        if x.strip()
    ]
    fpath = ds / "flags.jsonl"
    rows: dict[str, dict[str, Any]] = {}
    if fpath.exists():
        for line in fpath.read_text(encoding="utf-8").splitlines():
            if line.strip() and not line.lstrip().startswith("//"):
                r = json.loads(line)
                rows[r["company"]] = r

    for c in companies:
        alias = c["id"]
        if args.only and alias not in args.only:
            continue
        snap_path = Path(f"evals/snapshots/{args.dataset}/{c['company_number']}.json")
        if not snap_path.exists():
            print(f"{alias}: snapshot missing, skipped")
            continue
        proposed, facts = draft(json.loads(snap_path.read_text(encoding="utf-8")))
        shown = ", ".join(f"{i}:{s}" for i, s in proposed) or "(no flags)"
        print(f"\n{alias} {','.join(c.get('tags', []))}\n  facts: {facts}\n  draft: {shown}")
        expected: list[tuple[str, str | None]] | None = list(proposed)
        note = "drafted by scripts/flag_labeller.py from LABELLING.md definitions"
        if not args.auto:
            while True:
                ans = input("  Enter=accept, none, s=skip, or flags (id:severity,...) > ").strip()
                if ans == "":
                    break
                if ans.lower() == "s":
                    expected = None
                    break
                if ans.lower() == "none":
                    expected, note = [], note + "; reviewer expects none"
                    break
                parsed = parse_override(ans)
                if parsed is not None:
                    expected, note = parsed, note + "; overridden by reviewer"
                    break
        if expected is None:
            continue
        old = rows.get(alias, {})
        rows[alias] = {
            "company": alias,
            "expected": [{"id": i, **({"severity": s} if s else {})} for i, s in expected],
            "labeller": args.labeller,
            "labelled_on": date.today().isoformat(),
            "second_labeller_expected": old.get("second_labeller_expected"),
            "notes": note,
        }
        fpath.write_text("\n".join(json.dumps(r) for r in rows.values()) + "\n", encoding="utf-8")

    done = sum(1 for r in rows.values() if r.get("expected") is not None)
    print(f"\n{done} companies labelled in {fpath}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
