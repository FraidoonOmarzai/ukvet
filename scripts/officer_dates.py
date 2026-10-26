"""Show officer appointment/resignation dates (no names) for one company, to debug flag counts.

Usage: uv run python scripts/officer_dates.py c032 --dataset v0.1
Prints the incorporation date, as_of, the 12-month window and every officer event inside it.
"""

from __future__ import annotations

import argparse
import json
from datetime import date, timedelta
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("alias")
    ap.add_argument("--dataset", default="v0.1")
    a = ap.parse_args()
    comps = [
        json.loads(x)
        for x in Path(f"evals/datasets/{a.dataset}/companies.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if x.strip()
    ]
    c = next((x for x in comps if x["id"] == a.alias), None)
    if c is None:
        raise SystemExit(f"{a.alias} not found")
    snap = json.loads(
        Path(f"evals/snapshots/{a.dataset}/{c['company_number']}.json").read_text(encoding="utf-8")
    )
    as_of = date.fromisoformat(snap["meta"]["as_of"])
    start = (as_of - timedelta(days=365)).isoformat()
    prof = (snap["endpoints"].get("profile") or {}).get("body") or {}
    created = prof.get("date_of_creation")
    ep = snap["endpoints"].get("officers") or {}
    items = (ep.get("body") or {}).get("items", [])
    print(
        f"{a.alias}: created {created}, as_of {as_of}, window starts {start}, officers listed {len(items)}, truncated={snap['meta'].get('truncated')}"
    )
    rows = []
    for o in items:
        role = o.get("officer_role")
        if (o.get("appointed_on") or "") >= start:
            rows.append((o["appointed_on"], "appointed", role))
        if (o.get("resigned_on") or "") >= start:
            rows.append((o["resigned_on"], "resigned", role))
    for r in sorted(rows):
        print(f"  {r[0]}  {r[1]:9}  {r[2]}")
    print(f"{len(rows)} events in the window (before any formation-appointment exclusion)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
