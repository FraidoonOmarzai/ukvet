"""Build the SYNTHETIC `v0.1-draft` dataset: 28 made-up companies that cover every required tag.

It exists so the whole pipeline (run, gate, report, CI) can be exercised end to end while the real
`v0.1` dataset is still being recorded. Everything is invented: no real company, no real person.
Its scores say nothing about ukvet's accuracy on real registry data and must never be quoted as
results.

Labels are produced by a small labeller written from evals/LABELLING.md (not from ukvet's rules).
Golden values are copied from the specs below, standing in for "read on the website".
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
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

AS_OF = date(2026, 10, 24)
NAME = "v0.1-draft"
FAILED = {"liquidation", "administration", "receivership", "voluntary-arrangement",
          "insolvency-proceedings"}  # fmt: skip
INDIVIDUAL = "individual-person-with-significant-control"
CORPORATE = "corporate-entity-person-with-significant-control"


@dataclass
class Spec:
    tags: list[str]
    created: str
    number: str = ""
    status: str = "active"
    kind: str = "ltd"
    detail: str | None = None
    ceased: str | None = None
    acc_overdue: bool = False
    con_overdue: bool = False
    # (role, appointed, resigned, corporate)
    officers: list[tuple[str, str, str | None, bool]] = field(default_factory=list)
    psc: list[tuple[str, bool]] | None = None  # (kind, ceased); None = endpoint returns 404
    charges: list[str] = field(default_factory=list)  # charge statuses
    cases: list[str] = field(default_factory=list)  # insolvency case types
    ad01: list[str] = field(default_factory=list)  # registered-office change dates
    others: dict[int, list[tuple[str, str]]] = field(
        default_factory=dict
    )  # director idx -> [(status, role)]
    bare: bool = False  # dissolved: only profile, charges, insolvency exist


def _d(*appointed: str) -> list[tuple[str, str, str | None, bool]]:
    return [("director", a, None, False) for a in appointed]


SPECS: list[Spec] = [
    # --- large plcs -----------------------------------------------------------------------------
    Spec(
        ["large-plc", "charges-all-satisfied", "officer-changes-12m"],
        "1989-06-01",
        kind="plc",
        officers=_d(
            "2004-02-01", "2008-05-01", "2011-09-01", "2014-01-01", "2016-03-01", "2019-07-01"
        )
        + [
            ("director", "2015-01-01", "2026-02-10", False),
            ("director", "2013-01-01", "2026-05-02", False),
            ("director", "2026-06-20", None, False),
        ],
        psc=[(INDIVIDUAL, False)],
        charges=["fully-satisfied", "fully-satisfied"],
    ),
    Spec(
        ["large-plc", "corporate-psc"],
        "1996-03-15",
        kind="plc",
        officers=_d("2010-01-01", "2012-04-01", "2018-08-01"),
        psc=[(CORPORATE, False)],
    ),
    Spec(
        ["large-plc", "no-psc"],
        "1971-11-20",
        kind="plc",
        officers=_d("2001-01-01", "2009-06-01", "2015-02-01", "2017-10-01", "2020-01-01"),
        psc=[],
    ),
    # --- healthy small ----------------------------------------------------------------------------
    Spec(
        ["healthy-small"],
        "2016-04-12",
        officers=_d("2016-04-12", "2018-09-01"),
        psc=[(INDIVIDUAL, False)],
    ),
    Spec(
        ["healthy-small", "charges-all-satisfied"],
        "2014-08-01",
        officers=_d("2014-08-01"),
        psc=[(INDIVIDUAL, False)],
        charges=["fully-satisfied"],
    ),
    Spec(
        ["healthy-small", "corporate-psc"],
        "2019-01-22",
        officers=_d("2019-01-22", "2021-03-01"),
        psc=[(CORPORATE, False)],
    ),
    Spec(
        ["healthy-small"],
        "2012-10-05",
        officers=_d("2012-10-05"),
        psc=[(INDIVIDUAL, False)],
        ad01=["2026-03-14"],
    ),
    # --- young companies ----------------------------------------------------------------------------
    Spec(["under-1-year", "no-psc"], "2026-03-02", officers=_d("2026-03-02"), psc=[]),
    Spec(["under-1-year", "no-psc"], "2026-06-15", officers=_d("2026-06-15", "2026-06-20"), psc=[]),
    Spec(["under-1-year"], "2026-08-20", officers=_d("2026-08-20"), psc=[(INDIVIDUAL, False)]),
    Spec(["1-to-2-years"], "2025-05-12", officers=_d("2025-05-12"), psc=[(INDIVIDUAL, False)]),
    Spec(
        ["1-to-2-years", "officer-changes-12m"],
        "2025-02-03",
        officers=[
            ("director", "2025-02-03", None, False),
            ("director", "2026-01-10", None, False),
            ("director", "2025-02-03", "2026-05-02", False),
        ],
        psc=[(INDIVIDUAL, False)],
    ),
    # --- dissolved -----------------------------------------------------------------------------------
    Spec(["dissolved"], "2015-02-02", status="dissolved", ceased="2025-11-20", bare=True),
    Spec(["dissolved"], "2017-07-07", status="dissolved", ceased="2024-04-09", bare=True),
    Spec(
        ["dissolved"],
        "2013-09-30",
        status="dissolved",
        ceased="2023-01-17",
        bare=True,
        cases=["creditors-voluntary-liquidation"],
    ),
    # --- liquidation -----------------------------------------------------------------------------------
    Spec(
        ["liquidation-mvl"],
        "2010-05-05",
        status="liquidation",
        officers=_d("2010-05-05"),
        psc=[(INDIVIDUAL, False)],
        cases=["members-voluntary-liquidation"],
    ),
    Spec(
        ["liquidation-mvl"],
        "2008-01-18",
        status="liquidation",
        officers=_d("2008-01-18", "2012-02-02"),
        psc=[(INDIVIDUAL, False)],
        cases=["members-voluntary-liquidation"],
    ),
    Spec(
        ["liquidation-creditors"],
        "2018-06-06",
        status="liquidation",
        officers=_d("2018-06-06"),
        psc=[(INDIVIDUAL, False)],
        cases=["creditors-voluntary-liquidation"],
        charges=["outstanding"],
    ),
    Spec(
        ["liquidation-creditors", "overdue-filings"],
        "2016-12-12",
        status="liquidation",
        officers=_d("2016-12-12"),
        psc=[(INDIVIDUAL, False)],
        cases=["creditors-voluntary-liquidation"],
        acc_overdue=True,
    ),
    # --- administration / receivership -------------------------------------------------------------------
    Spec(
        ["administration-or-receivership"],
        "2011-03-03",
        status="administration",
        officers=_d("2011-03-03", "2013-07-07"),
        psc=[(INDIVIDUAL, False)],
        cases=["in-administration"],
    ),
    Spec(
        ["administration-or-receivership"],
        "2014-04-14",
        status="receivership",
        officers=_d("2014-04-14"),
        psc=[(INDIVIDUAL, False)],
        cases=["receiver-manager"],
        charges=["outstanding"],
    ),
    # --- strike-off ------------------------------------------------------------------------------------------
    Spec(
        ["strike-off-proposal", "overdue-filings"],
        "2018-09-09",
        detail="active-proposal-to-strike-off",
        officers=_d("2018-09-09"),
        psc=[(INDIVIDUAL, False)],
        con_overdue=True,
    ),
    Spec(
        ["strike-off-proposal"],
        "2021-02-20",
        detail="active-proposal-to-strike-off",
        officers=_d("2021-02-20"),
        psc=[(INDIVIDUAL, False)],
    ),
    # --- overdue / charges / address ----------------------------------------------------------------------------
    Spec(
        ["overdue-filings", "charges-outstanding"],
        "2017-05-25",
        acc_overdue=True,
        con_overdue=True,
        officers=_d("2017-05-25", "2019-11-11"),
        psc=[(INDIVIDUAL, False)],
        charges=["outstanding", "fully-satisfied"],
    ),
    Spec(
        ["charges-outstanding", "address-change-12m", "corporate-officer"],
        "2015-11-30",
        officers=[("director", "2015-11-30", None, False), ("director", "2020-02-02", None, True)],
        psc=[(INDIVIDUAL, False)],
        charges=["outstanding"],
        ad01=["2026-01-12", "2026-04-02", "2026-08-30"],
    ),
    # --- LLP / Scottish / Northern Irish -------------------------------------------------------------------------
    Spec(
        ["llp-or-sc-or-ni", "address-change-12m"],
        "2013-04-01",
        kind="llp",
        number="OC900026",
        officers=[
            ("llp-designated-member", "2013-04-01", None, False),
            ("llp-member", "2013-04-01", None, False),
        ],
        psc=[(INDIVIDUAL, False)],
        ad01=["2026-02-02", "2026-07-07"],
    ),
    Spec(
        ["llp-or-sc-or-ni", "many-appointments-director", "corporate-officer"],
        "2009-08-08",
        number="SC900027",
        officers=[("director", "2009-08-08", None, False), ("director", "2022-05-05", None, True)],
        psc=[(INDIVIDUAL, False)],
        others={
            0: [("active", "director")] * 5
            + [
                ("liquidation", "director"),
                ("dissolved", "director"),
                ("administration", "director"),
            ]
        },
    ),
    Spec(
        ["llp-or-sc-or-ni", "many-appointments-director", "officer-changes-12m"],
        "2005-02-14",
        number="NI900028",
        officers=[
            ("director", "2005-02-14", None, False),
            ("director", "2026-02-02", None, False),
            ("director", "2026-03-03", None, False),
            ("director", "2010-10-10", "2026-07-07", False),
        ],
        psc=[(INDIVIDUAL, False)],
        others={
            0: [("active", "director")] * 6
            + [("liquidation", "director")] * 3
            + [("dissolved", "director")] * 3
        },
    ),
]


def _number(i: int, spec: Spec) -> str:
    return spec.number or f"92{i:06d}"


def _endpoint(body: Any, status: int = 200) -> Endpoint:
    return Endpoint(status=status, body=body)


def build_snapshot(i: int, spec: Spec) -> Snapshot:
    num = _number(i, spec)
    name = f"TEST COMPANY {i:03d}"
    profile: dict[str, Any] = {
        "company_number": num, "company_name": name, "company_status": spec.status, "type": spec.kind,
        "date_of_creation": spec.created, "has_charges": bool(spec.charges),
        "has_insolvency_history": bool(spec.cases),
    }  # fmt: skip
    if spec.detail:
        profile["company_status_detail"] = spec.detail
    if spec.ceased:
        profile["date_of_cessation"] = spec.ceased
    if spec.status != "dissolved":
        profile["accounts"] = {"next_due": "2026-12-31" if not spec.acc_overdue else "2026-06-30",
                               "overdue": spec.acc_overdue,
                               "last_accounts": {"made_up_to": "2025-12-31" if not spec.acc_overdue else "2024-12-31"}}  # fmt: skip
        profile["confirmation_statement"] = {"next_due": "2027-02-01" if not spec.con_overdue else "2026-07-01",
                                             "overdue": spec.con_overdue, "last_made_up_to": "2026-01-18" if not spec.con_overdue else "2025-06-17"}  # fmt: skip
    eps: dict[str, Endpoint] = {
        k: Endpoint(status=404) for k in ("charges", "insolvency", "psc", "filings", "officers")
    }
    eps["profile"] = _endpoint(profile)
    if spec.charges:
        eps["charges"] = _endpoint({"total_count": len(spec.charges), "items": [
            {"charge_number": n + 1, "status": s, "created_on": "2018-01-01",
             **({"satisfied_on": "2022-01-01"} if s == "fully-satisfied" else {})}
            for n, s in enumerate(spec.charges)]})  # fmt: skip
    if spec.cases:
        eps["insolvency"] = _endpoint({"status": ["x"], "cases": [
            {"number": n + 1, "type": t, "dates": [{"type": "wound-up-on", "date": "2025-09-01"}]}
            for n, t in enumerate(spec.cases)]})  # fmt: skip
    appts: dict[str, Endpoint] = {}
    if not spec.bare:
        items: list[dict[str, Any]] = []
        for n, (role, appointed, resigned, corporate) in enumerate(spec.officers):
            oid = f"OFFICERID{i:02d}{chr(65 + n)}"
            items.append({
                "name": f"CORPORATE OFFICER {n + 1:03d}" if corporate else f"PERSON {n + 1:03d}",
                "officer_role": role, "appointed_on": appointed,
                **({"resigned_on": resigned} if resigned else {}),
                "links": {"officer": {"appointments": f"/officers/{oid}/appointments"}},
            })  # fmt: skip
        eps["officers"] = _endpoint({"total_results": len(items), "active_count": sum(1 for o in items if "resigned_on" not in o), "items": items})  # fmt: skip
        if spec.psc is not None:
            eps["psc"] = _endpoint({"total_results": len(spec.psc), "active_count": sum(1 for _, c in spec.psc if not c), "items": [
                {"name": f"CORPORATE CONTROLLER {n + 1:03d}" if k == CORPORATE else f"PERSON CONTROL {n + 1:03d}",
                 "kind": k, "notified_on": "2016-04-06",
                 "natures_of_control": ["ownership-of-shares-75-to-100-percent"],
                 **({"ceased_on": "2024-01-01"} if c else {})}
                for n, (k, c) in enumerate(spec.psc)]})  # fmt: skip
        if spec.ad01:
            eps["filings"] = _endpoint({"total_count": len(spec.ad01), "items": [
                {"date": d, "type": "AD01", "category": "address"} for d in spec.ad01]})  # fmt: skip
        for n, item in enumerate(items):
            if item.get("resigned_on") or "director" not in item["officer_role"]:
                continue
            oid = item["links"]["officer"]["appointments"].split("/")[2]
            apps = [{"appointed_to": {"company_name": name, "company_number": num, "company_status": spec.status},
                     "officer_role": item["officer_role"], "appointed_on": item["appointed_on"]}]  # fmt: skip
            for m, (st, role) in enumerate(spec.others.get(n, [])):
                apps.append({"appointed_to": {"company_name": f"LINKED TEST {i:03d}-{n}-{m} LTD",
                                              "company_number": f"93{i:03d}{n}{m:03d}", "company_status": st},
                             "officer_role": role, "appointed_on": "2012-01-01"})  # fmt: skip
            appts[oid] = _endpoint({"name": item["name"], "total_results": len(apps), "items_per_page": 50, "start_index": 0, "kind": "personal-appointment", "items": apps})  # fmt: skip
    return Snapshot(
        meta=SnapshotMeta(company_number=num, as_of=AS_OF, synthetic=True),
        endpoints=eps,
        appointments=appts,
    )


# --- an independent labeller, written from evals/LABELLING.md ---------------------------------------------------


def label_flags(spec: Spec) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    start = (AS_OF - timedelta(days=365)).isoformat()
    created = date.fromisoformat(spec.created)
    age_days = (AS_OF - created).days
    mvl_only = bool(spec.cases) and all(c == "members-voluntary-liquidation" for c in spec.cases)
    active = spec.status == "active"
    if spec.status == "dissolved" or spec.status in FAILED:
        out.append(("status", "medium" if spec.status == "liquidation" and mvl_only else "high"))
    elif not active:
        out.append(("status", "medium"))
    if spec.detail == "active-proposal-to-strike-off":
        out.append(("strike_off", "high"))
    if spec.cases and not (spec.status == "liquidation" and mvl_only):
        out.append(("insolvency", "medium" if mvl_only else "high"))
    if active and age_days < 365:
        out.append(("age", "medium"))
    elif active and age_days < 730:
        out.append(("age", "low"))
    if spec.acc_overdue:
        out.append(("accounts_overdue", "medium"))
    if spec.con_overdue:
        out.append(("confirmation_overdue", "medium"))
    if "outstanding" in spec.charges:
        out.append(("charges", "low"))
    # network: first five current directors' other appointments
    current = [(n, o) for n, o in enumerate(spec.officers) if o[2] is None and "director" in o[0]][
        :5
    ]
    failed: set[str] = set()
    dissolved = 0
    for n, _ in current:
        for m, (st, _) in enumerate(spec.others.get(n, [])):
            if st in FAILED:
                failed.add(f"{n}-{m}")
            elif st == "dissolved":
                dissolved += 1
    if len(failed) >= 3:
        out.append(("network", "high"))
    elif len(failed) == 2:
        out.append(("network", "medium"))
    elif len(failed) == 1 or dissolved >= 5:
        out.append(("network", "low"))
    events = 0
    for _, appointed, resigned, _ in spec.officers:
        if appointed >= start and (created + timedelta(days=30)) < date.fromisoformat(appointed):
            events += 1
        if resigned and resigned >= start:
            events += 1
    if events >= 3:
        out.append(("officer_turnover", "medium"))
    elif events == 2:
        out.append(("officer_turnover", "low"))
    if sum(1 for d in spec.ad01 if d >= start) >= 2:
        out.append(("address_changes", "medium"))
    if active and not current:
        out.append(("no_directors", "medium"))
    if active and spec.psc is not None and not any(not c for _, c in spec.psc) and not spec.bare:
        out.append(("no_psc", "info"))
    return out


def _golden(cid: str, spec: Spec) -> GoldenRow:
    fields: dict[str, Any] = {"Q1.status": spec.status, "Q2.date_of_creation": spec.created}
    if spec.status != "dissolved":
        fields["Q4.accounts.overdue"] = spec.acc_overdue
        fields["Q4.confirmation.overdue"] = spec.con_overdue
        fields["Q6.outstanding"] = sum(1 for c in spec.charges if c == "outstanding")
    return GoldenRow(company=cid, checked_on=AS_OF, checker="draft",
                     source="SYNTHETIC: copied from the generator spec, not read on the website", fields=fields)  # fmt: skip


def build_draft(root: Path) -> Path:
    ds_dir = root / "evals" / "datasets" / NAME
    snap_dir = root / "evals" / "snapshots" / NAME
    ids = [f"c{i:03d}" for i in range(1, len(SPECS) + 1)]
    salt = choose_salt(ids)
    manifest = Manifest(name=NAME, version="draft-1", split_salt=salt, synthetic=True, splits_locked=True,
                        description="SYNTHETIC placeholder for v0.1: 28 invented companies covering every "
                        "required tag. Not real data; scores are not results.")  # fmt: skip
    ds_dir.mkdir(parents=True, exist_ok=True)
    (ds_dir / "dataset.json").write_text(
        manifest.model_dump_json(indent=1) + "\n", encoding="utf-8"
    )
    companies: list[CompanyEntry] = []
    snaps: dict[str, Snapshot] = {}
    labels: list[FlagLabel] = []
    golden: list[GoldenRow] = []
    for i, (cid, spec) in enumerate(zip(ids, SPECS, strict=True), start=1):
        snap = build_snapshot(i, spec)
        num = _number(i, spec)
        snap.save(snap_dir / f"{num}.json")
        snaps[num] = snap
        companies.append(CompanyEntry(id=cid, company_number=num, as_of=AS_OF, tags=spec.tags,
                                      split=split_for(cid, salt)))  # fmt: skip
        labels.append(FlagLabel(company=cid, labeller="draft", labelled_on=AS_OF,
                                expected=[ExpectedFlag(id=f, severity=s) for f, s in label_flags(spec)],  # type: ignore[arg-type]
                                notes="LLP members are not directors, so no_directors applies by definition" if spec.kind == "llp" else ""))  # fmt: skip
        if i % 8 != 0:  # ~25 of 28 golden rows
            golden.append(_golden(cid, spec))
    write_jsonl(ds_dir / "companies.jsonl", companies)
    write_jsonl(ds_dir / "golden.jsonl", golden)
    write_jsonl(ds_dir / "flags.jsonl", flag_template(companies, labels))
    write_jsonl(ds_dir / "abstention.jsonl", gen_abstention(companies, snaps, []))
    write_jsonl(ds_dir / "injection.jsonl", injection_cases())
    write_jsonl(ds_dir / "items.jsonl", build_items(companies, snaps, golden))
    return ds_dir
