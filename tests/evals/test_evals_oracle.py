"""The oracle is only worth having if it is independent of the code it checks."""

import ast
from datetime import date
from pathlib import Path

import ukvet_evals.oracle as oracle_module
from ukvet_evals.oracle import oracle_fields
from ukvet_evals.snapshot import Endpoint, Snapshot, SnapshotMeta

AS_OF = date(2026, 3, 4)


def snap(**eps: Endpoint) -> Snapshot:
    appts = eps.pop("appointments", None)  # type: ignore[arg-type]
    return Snapshot(
        meta=SnapshotMeta(company_number="91000001", as_of=AS_OF),
        endpoints=dict(eps),
        appointments={"OFFICERID01": appts} if appts else {},
    )


def ok(body: dict) -> Endpoint:  # type: ignore[type-arg]
    return Endpoint(status=200, body=body)


def test_oracle_does_not_import_the_code_it_checks() -> None:
    tree = ast.parse(Path(oracle_module.__file__).read_text())
    imported = {
        (n.module or "") if isinstance(n, ast.ImportFrom) else a.name
        for n in ast.walk(tree)
        if isinstance(n, ast.Import | ast.ImportFrom)
        for a in (n.names if isinstance(n, ast.Import) else [n])
    }
    bad = {m for m in imported if m.split(".")[0] in {"ukvet_mcp", "ukvet_agent"}}
    assert not bad, f"oracle must stay independent, but imports {bad}"


def test_profile_fields_and_age() -> None:
    f = oracle_fields(
        snap(profile=ok({
            "company_status": "dissolved", "date_of_creation": "2018-01-15",
            "date_of_cessation": "2022-06-01",
            "accounts": {"overdue": False, "next_due": "2027-01-01", "last_accounts": {"made_up_to": "2025-03-31"}},
            "confirmation_statement": {"overdue": True},
        })),
        AS_OF,
    )  # fmt: skip
    assert f["Q1.status"] == "dissolved" and f["Q1.date_of_cessation"] == "2022-06-01"
    assert f["Q2.age_days"] == (date(2022, 6, 1) - date(2018, 1, 15)).days  # age stops at cessation
    assert f["Q4.accounts.last_made_up_to"] == "2025-03-31"
    assert f["Q4.confirmation.overdue"] is True and f["Q4.confirmation.next_due"] is None


def test_officers_and_window() -> None:
    items = [
        {"name": "A", "officer_role": "director", "appointed_on": "2025-06-01", "links": {"officer": {"appointments": "/officers/OFFICERID01/appointments"}}},
        {"name": "B", "officer_role": "secretary", "appointed_on": "2010-01-01"},
        {"name": "C", "officer_role": "corporate-director", "appointed_on": "2010-01-01", "resigned_on": "2025-04-01"},
        {"name": "D", "officer_role": "director", "appointed_on": "2000-01-01", "resigned_on": "2024-01-01"},
    ]  # fmt: skip
    f = oracle_fields(snap(officers=ok({"items": items})), AS_OF)
    assert (
        f["Q3.current_total"] == 2 and f["Q3.director_count"] == 1 and f["Q3.other_officers"] == 1
    )
    # window starts 2025-03-04: A appointed (in), C resigned (in), D resigned 2024 (out)
    assert f["Q9.appointed"] == 1 and f["Q9.resigned"] == 1


def test_psc_charges_insolvency() -> None:
    f = oracle_fields(
        snap(
            psc=ok({"items": [
                {"kind": "individual-person-with-significant-control"},
                {"kind": "corporate-entity-person-with-significant-control"},
                {"kind": "individual-person-with-significant-control", "ceased": True},
                {"kind": "individual-person-with-significant-control", "ceased_on": "2020-01-01"},
            ]}),
            charges=ok({"total_count": 5, "items": [{"status": "outstanding"}, {"status": "fully-satisfied"}, {"status": "satisfied"}, {"status": "part-satisfied"}]}),
            insolvency=ok({"cases": [{"type": "members-voluntary-liquidation"}, {"type": "administration-order"}]}),
        ),
        AS_OF,
    )  # fmt: skip
    assert f["Q5.current_total"] == 2 and f["Q5.corporate_count"] == 1
    assert (f["Q6.outstanding"], f["Q6.part_satisfied"], f["Q6.satisfied"], f["Q6.total"]) == (
        1,
        1,
        2,
        5,
    )
    assert f["Q7.case_count"] == 2 and f["Q7.case_types"] == [
        "administration-order",
        "members-voluntary-liquidation",
    ]


def test_missing_endpoints_give_zero_values_not_crashes() -> None:
    f = oracle_fields(snap(), AS_OF)
    assert f["Q1.status"] is None and f["Q6.total"] == 0 and f["Q7.case_count"] == 0
    assert f["Q8.directors_checked"] == 0 and f["Q9.address_changes"] == 0


def test_network_excludes_own_company_and_counts_first_status() -> None:
    officers = ok(
        {
            "items": [
                {
                    "officer_role": "director",
                    "appointed_on": "2020-01-01",
                    "links": {"officer": {"appointments": "/officers/OFFICERID01/appointments"}},
                }
            ]
        }
    )
    appts = ok({"items": [
        {"appointed_to": {"company_number": "91000001", "company_status": "active"}},
        {"appointed_to": {"company_number": "90000002", "company_status": "liquidation"}},
        {"appointed_to": {"company_number": "90000002", "company_status": "dissolved"}},
        {"appointed_to": {"company_number": "90000003"}},
    ]})  # fmt: skip
    f = oracle_fields(snap(officers=officers, appointments=appts), AS_OF)
    assert f["Q8.per_director_other_totals"] == [3]
    assert f["Q8.other_companies"] == 2
    assert f["Q8.status_counts"] == {"liquidation": 1, "unknown": 1}
