#!/usr/bin/env python
"""Record ANONYMISED Companies House fixtures from the live API.

Usage (from repo root, with CH_API_KEY in .env):
    uv run python scripts/record_fixtures.py                 # spike test set from docs/05
    uv run python scripts/record_fixtures.py 00445790 12056899 --public 00445790

Writes tests/fixtures/ch/rec_<n>__<endpoint>.json. Raw responses are never written to disk.
Large public companies passed via --public keep their real identity; everything else and all
people are anonymised (see scripts/anonymise.py). Review the output before committing.
"""

import argparse
import json
import os
import sys
import time
from datetime import date
from pathlib import Path

import httpx
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))
from anonymise import Anonymiser  # noqa: E402

BASE = "https://api.company-information.service.gov.uk"
OUT = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "ch"
# Spike test set from docs/05-data-notes.md (large plc first; it is the only public one)
DEFAULT_COMPANIES = [
    "00445790",
    "17491796",
    "12115175",
    "01468547",
    "12056899",
    "17016019",
    "03977902",
]
DEFAULT_PUBLIC = {"00445790"}


def get(client: httpx.Client, path: str, params: dict | None = None) -> tuple[int, dict | None]:
    time.sleep(0.25)  # gentle: ~4 req/s, far under 600 per 5 min
    r = client.get(path, params=params)
    if r.status_code in (200,):
        return 200, r.json()
    if r.status_code == 404:
        return 404, None
    r.raise_for_status()
    raise RuntimeError(f"unexpected status {r.status_code}")


def save(name: str, path: str, status: int, body: dict | None) -> None:
    meta = {"synthetic": False, "anonymised": True, "recorded": date.today().isoformat()}
    (OUT / f"{name}.json").write_text(
        json.dumps(
            {"_meta": meta, "request": {"path": path}, "status": status, "body": body}, indent=2
        )
        + "\n"
    )
    print(f"  saved {name}.json ({status})")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("companies", nargs="*", default=DEFAULT_COMPANIES)
    ap.add_argument(
        "--public", nargs="*", default=sorted(DEFAULT_PUBLIC), help="numbers kept un-anonymised"
    )
    args = ap.parse_args()

    load_dotenv()
    key = os.getenv("CH_API_KEY")
    if not key:
        sys.exit("Set CH_API_KEY in .env")
    anon = Anonymiser(public_companies=set(args.public))
    OUT.mkdir(parents=True, exist_ok=True)

    with httpx.Client(base_url=BASE, auth=(key, ""), timeout=20) as client:
        for number in args.companies:
            print(f"== {number}")
            status, profile = get(client, f"/company/{number}")
            if status != 200 or profile is None:
                print("  not found, skipping")
                continue
            alias = anon.company_number(number)
            tag = f"rec_{alias}"
            save(f"{tag}__profile", f"/company/{alias}", 200, anon.profile(profile))

            officers_body = None
            for endpoint, scrub in (
                ("officers", lambda b: anon.officers(b)),
                ("persons-with-significant-control", lambda b: anon.psc(b)),
                ("charges", lambda b, n=number: anon.charges(b, n)),
                ("insolvency", lambda b: anon.insolvency(b)),
                ("filing-history", lambda b: anon.filings(b)),
            ):
                params = {"items_per_page": 100} if endpoint != "insolvency" else None
                st, body = get(client, f"/company/{number}/{endpoint}", params)
                if endpoint == "officers" and body:
                    officers_body = body
                save(
                    f"{tag}__{endpoint}",
                    f"/company/{alias}/{endpoint}",
                    st,
                    scrub(body) if body else None,
                )

            # Q8: appointments for up to 3 current officers
            seen = 0
            for item in (officers_body or {}).get("items", []):
                link = item.get("links", {}).get("officer", {}).get("appointments")
                if not link or item.get("resigned_on") or seen >= 3:
                    continue
                st, body = get(client, link, {"items_per_page": 50})
                if st == 200 and body:
                    anon_path = anon.officer_path(link)
                    oid = anon_path.split("/")[2].lower()
                    save(f"rec_{oid}__appointments", anon_path, 200, anon.appointments(body))
                    seen += 1

    # Safety net: re-read everything written and fail loudly on any leak.
    for file in sorted(OUT.glob("rec_*.json")):
        anon.leak_check(json.loads(file.read_text()))
    print("\nLeak check passed. Review tests/fixtures/ch/rec_*.json before committing.")


if __name__ == "__main__":
    main()
