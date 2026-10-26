"""Turn your 21 Oct manual website check (docs/accuracy-check.md) into golden rows.

These values are NOT taken from the snapshots. They are the values ukvet printed on 21 Oct that
you then compared with the Companies House website and found matching (0 errors), so they are
website-verified values. Only fields listed as checked in accuracy-check.md are included.

Usage (repo root, after recording the companies into the dataset):
    uv run python scripts/golden_from_manual.py --dataset v0.1 --checker FO
It adds or replaces golden rows only for these 10 companies. Other rows are left alone.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

SOURCE = "find-and-update.company-information.service.gov.uk (manual check, accuracy-check.md)"
CHECKED_ON = "2026-10-21"
NUM = re.compile(r"^(?:[0-9]{8}|[A-Z]{2}[0-9]{6}|[A-Z]{2}[0-9]{5}[A-Z0-9])$")

# real company number -> {field: value}. Dates ISO. None = the website showed nothing.
MANUAL: dict[str, dict[str, Any]] = {
    "00445790": {  # large plc
        "Q1.status": "active",
        "Q2.date_of_creation": "1947-11-27",
        "Q4.accounts.next_due": "2027-08-26",
        "Q4.accounts.last_made_up_to": "2026-02-28",
        "Q4.confirmation.next_due": "2027-07-02",
        "Q4.confirmation.last_made_up_to": "2026-06-18",
        "Q6.total": 9,
        "Q6.outstanding": 2,
        "Q6.satisfied": 7,
        "Q3.current_total": 11,
    },
    "17491796": {  # new Ltd, 21 days old at check
        "Q1.status": "active",
        "Q2.date_of_creation": "2026-09-30",
        "Q4.accounts.next_due": "2028-06-30",
        "Q4.accounts.last_made_up_to": None,
        "Q4.confirmation.next_due": "2027-10-13",
        "Q4.confirmation.last_made_up_to": None,
    },
    "12115175": {  # dissolved
        "Q1.status": "dissolved",
        "Q1.date_of_cessation": "2026-09-29",
        "Q2.date_of_creation": "2019-07-22",
        "Q4.accounts.last_made_up_to": "2026-07-04",
        "Q4.confirmation.last_made_up_to": "2025-07-21",
    },
    "01468547": {  # members' voluntary liquidation
        "Q1.status": "liquidation",
        "Q2.date_of_creation": "1979-12-24",
        "Q4.accounts.overdue": True,
        "Q4.accounts.next_due": "2025-09-30",
        "Q4.accounts.last_made_up_to": "2023-12-31",
        "Q4.confirmation.overdue": True,
        "Q4.confirmation.next_due": "2024-12-01",
        "Q4.confirmation.last_made_up_to": "2023-11-17",
        "Q7.case_count": 1,
    },
    "12056899": {  # active, proposal to strike off
        "Q1.status": "active",
        "Q1.status_detail": "active-proposal-to-strike-off",
        "Q2.date_of_creation": "2019-06-18",
        "Q4.accounts.overdue": True,
        "Q4.accounts.next_due": "2023-12-31",
        "Q4.accounts.last_made_up_to": "2022-03-31",
        "Q4.confirmation.overdue": True,
        "Q4.confirmation.next_due": "2024-07-29",
        "Q4.confirmation.last_made_up_to": "2023-07-15",
    },
    "17016019": {  # new Ltd with a charge
        "Q1.status": "active",
        "Q2.date_of_creation": "2026-02-06",
        "Q4.accounts.next_due": "2027-11-06",
        "Q4.confirmation.next_due": "2027-02-19",
        "Q6.outstanding": 1,
        "Q6.total": 1,
    },
    "03977902": {  # corporate PSC
        "Q1.status": "active",
        "Q2.date_of_creation": "2000-04-20",
        "Q4.accounts.next_due": "2027-09-30",
        "Q4.accounts.last_made_up_to": "2025-12-31",
        "Q4.confirmation.next_due": "2027-05-04",
        "Q4.confirmation.last_made_up_to": "2026-04-20",
        "Q6.outstanding": 1,
        "Q6.total": 1,
        "Q3.current_total": 3,
    },
    "17313434": {  # new Ltd
        "Q1.status": "active",
        "Q2.date_of_creation": "2026-07-01",
        "Q4.accounts.next_due": "2028-04-01",
        "Q4.confirmation.next_due": "2027-07-14",
    },
    "14189917": {  # 3 charges
        "Q1.status": "active",
        "Q2.date_of_creation": "2022-06-22",
        "Q4.accounts.next_due": "2026-12-31",
        "Q4.accounts.last_made_up_to": "2025-03-31",
        "Q4.confirmation.next_due": "2027-09-18",
        "Q4.confirmation.last_made_up_to": "2026-09-04",
        "Q6.outstanding": 3,
        "Q6.total": 3,
        "Q3.current_total": 2,
    },
    "12204233": {  # active Ltd
        "Q1.status": "active",
        "Q2.date_of_creation": "2019-09-12",
        "Q4.accounts.next_due": "2027-06-30",
        "Q4.accounts.last_made_up_to": "2025-09-30",
        "Q4.confirmation.next_due": "2027-09-25",
        "Q4.confirmation.last_made_up_to": "2026-09-11",
    },
}

# Suggested tags for recording the ones that are not yet in your dataset.
TAGS = {
    "00445790": "large-plc",
    "17491796": "under-1-year,no-psc",
    "12115175": "dissolved",
    "01468547": "liquidation-mvl,overdue-filings",
    "12056899": "strike-off-proposal,overdue-filings",
    "17016019": "under-1-year,charges-outstanding",
    "03977902": "corporate-psc,charges-outstanding",
    "17313434": "under-1-year",
    "14189917": "charges-outstanding",
    "12204233": "healthy-small",
}


def walk(node: Any, found: dict[str, str]) -> None:
    if isinstance(node, dict):
        for k, v in node.items():
            if isinstance(k, str) and NUM.match(k) and isinstance(v, str):
                found[k] = v
            else:
                walk(v, found)
    elif isinstance(node, list):
        for item in node:
            walk(item, found)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="v0.1")
    ap.add_argument("--checker", default="")
    args = ap.parse_args()

    ds = Path(f"evals/datasets/{args.dataset}")
    companies = [
        json.loads(x)
        for x in (ds / "companies.jsonl").read_text(encoding="utf-8").splitlines()
        if x.strip()
    ]
    by_number = {c["company_number"]: c["id"] for c in companies}
    pairs: dict[str, str] = {}
    mp = Path("data/raw/eval_mapping.json")
    if mp.exists():
        walk(json.loads(mp.read_text(encoding="utf-8")), pairs)

    gpath = ds / "golden.jsonl"
    golden: dict[str, dict[str, Any]] = {}
    if gpath.exists():
        for line in gpath.read_text(encoding="utf-8").splitlines():
            if line.strip() and not line.lstrip().startswith("//"):
                row = json.loads(line)
                golden[row["company"]] = row

    added, missing = [], []
    for real, fields in MANUAL.items():
        alias = by_number.get(real) or by_number.get(pairs.get(real, ""))
        if alias is None:
            missing.append(real)
            continue
        golden[alias] = {
            "company": alias,
            "checked_on": CHECKED_ON,
            "source": SOURCE,
            "checker": args.checker,
            "fields": fields,
        }
        added.append(alias)

    gpath.write_text("\n".join(json.dumps(r) for r in golden.values()) + "\n", encoding="utf-8")
    print(f"wrote {len(added)} golden rows ({', '.join(added) or 'none'}); {len(golden)} in total")
    if missing:
        print("\nNot in your dataset yet. Record them, then run this script again:")
        for real in missing:
            print(
                f"  uv run ukvet-evals record {real} --dataset {args.dataset} --tags {TAGS[real]}"
                + (f" --public {real}" if real == "00445790" else "")
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
