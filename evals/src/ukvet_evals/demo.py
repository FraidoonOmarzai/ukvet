"""Build the SYNTHETIC demo dataset (evals/datasets/demo) used by tests and the CI gate.

Everything here is made up. It exists so the harness, scorers and gate can be tested without
Companies House data; its scores say nothing about ukvet's real accuracy.
"""

import json
from datetime import date
from pathlib import Path
from typing import Any

from ukvet_evals.authoring import flag_template, gen_abstention, injection_cases
from ukvet_evals.items import build_items
from ukvet_evals.schema import (
    CompanyEntry,
    ExpectedFlag,
    FlagLabel,
    GoldenRow,
    Manifest,
    choose_salt,
    split_for,
    write_jsonl,
)  # fmt: skip
from ukvet_evals.snapshot import Endpoint, Snapshot, SnapshotMeta

AS_OF = date(2026, 3, 4)


def _fixture(root: Path, name: str) -> Endpoint:
    data = json.loads((root / "tests" / "fixtures" / "ch" / f"{name}.json").read_text())
    return Endpoint(status=data["status"], body=data["body"])


def _officers(*rows: tuple[str, str, str, str | None]) -> Endpoint:
    items = [
        {
            "name": f"PERSON {i + 1:03d}",
            "officer_role": role,
            "appointed_on": appointed,
            **({"resigned_on": resigned} if resigned else {}),
            "links": {"officer": {"appointments": f"/officers/{oid}/appointments"}},
        }
        for i, (oid, role, appointed, resigned) in enumerate(rows)
    ]
    return Endpoint(
        status=200, body={"total_results": len(items), "active_count": len(items), "items": items}
    )


def _profile(number: str, name: str, status: str, created: str, **extra: Any) -> Endpoint:
    body = {
        "company_number": number, "company_name": name, "company_status": status,
        "type": "ltd", "date_of_creation": created, "has_charges": False,
        "has_insolvency_history": False,
        "accounts": {"next_due": "2026-12-31", "overdue": False, "last_accounts": {"made_up_to": "2025-03-31"}},
        "confirmation_statement": {"next_due": "2026-09-01", "overdue": False, "last_made_up_to": "2025-08-18"},
    }  # fmt: skip
    body.update(extra)
    return Endpoint(status=200, body=body)


def _no_appointments(oid: str) -> Endpoint:
    return Endpoint(status=200, body={"name": "PERSON 001", "total_results": 0, "items": []})


def _snap(
    number: str, eps: dict[str, Endpoint], appts: dict[str, Endpoint] | None = None
) -> Snapshot:
    full = {"charges": Endpoint(status=404), "insolvency": Endpoint(status=404),
            "psc": Endpoint(status=404), "filings": Endpoint(status=404), "officers": Endpoint(status=404)}  # fmt: skip
    full.update(eps)
    return Snapshot(
        meta=SnapshotMeta(company_number=number, as_of=AS_OF, synthetic=True),
        endpoints=full,
        appointments=appts or {},
    )


def synthetic_snapshots(root: Path) -> dict[str, tuple[Snapshot, list[str]]]:
    """number -> (snapshot, tags)."""
    acme_eps = {
        "profile": _fixture(root, "12345678__profile"),
        "officers": _fixture(root, "12345678__officers"),
        "psc": _fixture(root, "12345678__psc"),
        "charges": _fixture(root, "12345678__charges"),
        "insolvency": _fixture(root, "12345678__insolvency"),
        "filings": _fixture(root, "12345678__filing-history"),
    }
    gone_eps = {
        "profile": _fixture(root, "87654321__profile"),
        "charges": _fixture(root, "87654321__charges"),
        "insolvency": _fixture(root, "87654321__insolvency"),
    }
    mvl = _profile("91000003", "TEST COMPANY 003", "liquidation", "2012-06-01")
    new = _profile("91000004", "TEST COMPANY 004", "active", "2026-01-10",
                   company_status_detail="active-proposal-to-strike-off")  # fmt: skip
    healthy = _profile("91000005", "TEST COMPANY 005", "active", "2012-05-01", has_charges=True)
    churn = _profile("91000006", "TEST COMPANY 006", "active", "2016-02-01")
    filings_churn = Endpoint(status=200, body={"total_count": 2, "items": [
        {"date": "2025-12-01", "type": "AD01", "category": "address"},
        {"date": "2025-06-10", "type": "AD01", "category": "address"},
    ]})  # fmt: skip
    return {
        "12345678": (_snap("12345678", acme_eps, {"OFFICERIDA1": _fixture(root, "officer_a__appointments"),
                                         "OFFICERIDB1": _no_appointments("OFFICERIDB1")}),
                     ["healthy-small", "overdue-filings", "charges-outstanding"]),
        "87654321": (_snap("87654321", gone_eps), ["dissolved", "liquidation-creditors"]),
        "91000003": (_snap("91000003", {
            "profile": mvl,
            "officers": _officers(("OFFICERID03", "director", "2012-06-01", None)),
            "insolvency": Endpoint(status=200, body={"status": ["voluntary-arrangement"], "cases": [
                {"number": 1, "type": "members-voluntary-liquidation", "dates": [{"type": "wound-up-on", "date": "2026-01-15"}]}]}),
        }, {"OFFICERID03": _no_appointments("OFFICERID03")}), ["liquidation-mvl"]),
        "91000004": (_snap("91000004", {
            "profile": new,
            "officers": _officers(("OFFICERID04", "director", "2026-01-10", None)),
        }, {"OFFICERID04": _no_appointments("OFFICERID04")}), ["under-1-year", "strike-off-proposal", "no-psc"]),
        "91000005": (_snap("91000005", {
            "profile": healthy,
            "officers": _officers(("OFFICERID05A", "director", "2012-05-01", None), ("OFFICERID05B", "director", "2014-02-01", None)),
            "psc": Endpoint(status=200, body={"total_results": 1, "active_count": 1, "items": [
                {"name": "CORPORATE CONTROLLER 001", "kind": "corporate-entity-person-with-significant-control",
                 "notified_on": "2016-04-06", "natures_of_control": ["ownership-of-shares-75-to-100-percent"]}]}),
            "charges": Endpoint(status=200, body={"total_count": 1, "items": [
                {"charge_number": 1, "status": "fully-satisfied", "created_on": "2013-01-01", "satisfied_on": "2018-01-01"}]}),
        }, {"OFFICERID05A": _no_appointments("OFFICERID05A"), "OFFICERID05B": _no_appointments("OFFICERID05B")}),
         ["healthy-small", "corporate-psc", "charges-all-satisfied"]),
        "91000006": (_snap("91000006", {
            "profile": churn,
            "officers": _officers(("OFFICERID06A", "director", "2025-04-01", None), ("OFFICERID06B", "director", "2025-09-01", None),
                                  ("OFFICERID06C", "director", "2016-02-01", "2025-10-01")),
            "filings": filings_churn,
        }, {"OFFICERID06A": _no_appointments("OFFICERID06A"), "OFFICERID06B": _no_appointments("OFFICERID06B")}),
         ["officer-changes-12m", "address-change-12m"]),
    }  # fmt: skip


def build_demo(root: Path) -> Path:
    snaps = synthetic_snapshots(root)
    ds_dir = root / "evals" / "datasets" / "demo"
    snap_dir = root / "evals" / "snapshots" / "demo"
    ids = [f"c{i:03d}" for i in range(1, len(snaps) + 1)]
    salt = choose_salt(ids)
    manifest = Manifest(name="demo", version="demo-1", split_salt=salt, synthetic=True,
                        description="Synthetic companies for testing the harness. Not real data.",
                        splits_locked=True)  # fmt: skip
    ds_dir.mkdir(parents=True, exist_ok=True)
    (ds_dir / "dataset.json").write_text(
        manifest.model_dump_json(indent=1) + "\n", encoding="utf-8"
    )

    companies: list[CompanyEntry] = []
    for cid, (number, (snap, tags)) in zip(ids, snaps.items(), strict=True):
        snap.save(snap_dir / f"{number}.json")
        companies.append(CompanyEntry(id=cid, company_number=number, as_of=AS_OF, tags=tags,
                                      split=split_for(cid, salt)))  # fmt: skip
    write_jsonl(ds_dir / "companies.jsonl", companies)

    golden = [GoldenRow(company="c001", checked_on=AS_OF, source="synthetic fixture (pretend website read)",
                        fields={"Q1.status": "active", "Q2.date_of_creation": "2019-03-04",
                                "Q4.accounts.overdue": True, "Q4.accounts.next_due": "2025-12-31",
                                "Q6.outstanding": 1}, checker="demo")]  # fmt: skip
    write_jsonl(ds_dir / "golden.jsonl", golden)

    def fl(company: str, *flags: tuple[str, str]) -> FlagLabel:
        return FlagLabel(company=company, labeller="demo", labelled_on=AS_OF,
                         expected=[ExpectedFlag(id=i, severity=s) for i, s in flags])  # type: ignore[arg-type]  # fmt: skip

    labels = [
        fl("c001", ("accounts_overdue", "medium"), ("charges", "low"), ("network", "low")),
        fl("c002", ("status", "high"), ("insolvency", "high")),
        fl("c003", ("status", "medium")),
        fl("c004", ("strike_off", "high"), ("age", "medium"), ("no_psc", "info")),
        fl("c005"),
        FlagLabel(company="c006"),  # deliberately unlabelled: exercises the "skipped" path
    ]
    write_jsonl(ds_dir / "flags.jsonl", flag_template(companies, labels))

    loaded = {c.company_number: snaps[c.company_number][0] for c in companies}
    write_jsonl(ds_dir / "abstention.jsonl", gen_abstention(companies, loaded, []))
    write_jsonl(ds_dir / "injection.jsonl", injection_cases())
    write_jsonl(ds_dir / "items.jsonl", build_items(companies, loaded, golden))
    return ds_dir
