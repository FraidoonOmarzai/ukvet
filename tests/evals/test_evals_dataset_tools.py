import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from evals_helpers import REPO, make_root
from ukvet_evals.authoring import gen_abstention, injection_cases
from ukvet_evals.demo import build_demo
from ukvet_evals.record import make_anonymiser, record_company
from ukvet_evals.schema import CompanyEntry, Dataset, split_for
from ukvet_evals.snapshot import Endpoint, Snapshot, SnapshotMeta
from ukvet_evals.validate import leak_problems, validate


def test_committed_demo_dataset_is_up_to_date(tmp_path: Path) -> None:
    """Rebuilding the demo from fixtures must reproduce the committed files exactly."""
    root = make_root(tmp_path)
    build_demo(root)
    for rel in [*(p.relative_to(REPO) for p in (REPO / "evals" / "datasets" / "demo").iterdir()),
                *(p.relative_to(REPO) for p in (REPO / "evals" / "snapshots" / "demo").iterdir())]:  # fmt: skip
        assert (root / rel).read_text() == (REPO / rel).read_text(), (
            f"{rel} is stale: run `ukvet-evals demo-build`"
        )


def test_demo_validates_and_strict_only_complains_for_real_datasets() -> None:
    rep = validate(REPO, "demo", strict=True)
    assert rep.ok, rep.errors
    assert any("coverage" in w for w in rep.warnings)  # synthetic data is exempt from the minimums


def test_validate_reports_missing_snapshot_and_unknown_company(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    build_demo(root)
    (root / "evals" / "snapshots" / "demo" / "91000003.json").unlink()
    ab = root / "evals" / "datasets" / "demo" / "flags.jsonl"
    ab.write_text(ab.read_text() + json.dumps({"company": "c999", "expected": None}) + "\n")
    errors = validate(root, "demo").errors
    assert any("snapshot 91000003.json is missing" in e for e in errors)
    assert any("unknown company 'c999'" in e for e in errors)


def test_hand_edited_split_is_rejected(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    build_demo(root)
    path = root / "evals" / "datasets" / "demo" / "companies.jsonl"
    path.write_text(path.read_text().replace('"split": "dev"', '"split": "test"', 1))
    with pytest.raises(ValueError, match="split must be"):
        Dataset(root / "evals", "demo")


def test_golden_conflict_is_an_error(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    build_demo(root)
    g = root / "evals" / "datasets" / "demo" / "golden.jsonl"
    g.write_text(g.read_text().replace('"Q1.status": "active"', '"Q1.status": "dissolved"'))
    assert any("golden conflict" in e for e in validate(root, "demo").errors)


# ---- leak check ------------------------------------------------------------------------------
def snapshot_with(body: dict[str, Any], key: str = "officers", public: bool = False) -> Snapshot:
    return Snapshot(
        meta=SnapshotMeta(company_number="91000001", as_of=date(2026, 1, 1), public=public),
        endpoints={key: Endpoint(status=200, body=body)},
    )


def test_leak_check_flags_real_names_and_forbidden_keys() -> None:
    bad = snapshot_with({"items": [{"name": "SMITH, John", "date_of_birth": {"year": 1980}}]})
    problems = leak_problems(bad)
    assert any("not anonymised" in p for p in problems) and any(
        "date_of_birth" in p for p in problems
    )
    assert leak_problems(snapshot_with({"items": [{"name": "PERSON 001"}]})) == []
    assert any(
        "company_name" in p
        for p in leak_problems(snapshot_with({"company_name": "REAL LTD"}, "profile"))
    )
    assert leak_problems(snapshot_with({"company_name": "TEST COMPANY 004"}, "profile")) == []


def test_public_companies_keep_real_names_but_never_personal_fields() -> None:
    pub = snapshot_with(
        {"company_name": "BIG PLC", "items": [{"name": "SMITH, John", "address": {}}]},
        "officers",
        True,
    )
    problems = leak_problems(pub)
    assert problems and all("address" in p for p in problems)


# ---- recorder --------------------------------------------------------------------------------
def fake_api() -> dict[str, Any]:
    director = {
        "name": "SMITH, John William", "officer_role": "director", "appointed_on": "2020-01-01",
        "date_of_birth": {"month": 1, "year": 1970}, "address": {"postal_code": "AB1 2CD"},
        "links": {"officer": {"appointments": "/officers/REALOFFICERID0001/appointments"}},
    }  # fmt: skip
    return {
        "/company/01234567": {"company_number": "01234567", "company_name": "REAL SECRET LTD", "company_status": "active",
                              "date_of_creation": "2015-05-05", "registered_office_address": {"postal_code": "AB1 2CD"}},
        "/company/01234567/officers": {"total_results": 1, "items": [director]},
        "/company/01234567/persons-with-significant-control": {"total_results": 1, "items": [
            {"name": "SMITH, John William", "kind": "individual-person-with-significant-control", "natures_of_control": []}]},
        "/company/01234567/charges": {"total_count": 1, "items": [
            {"status": "outstanding", "persons_entitled": [{"name": "SECRET BANK PLC"}]}]},
        "/company/01234567/filing-history": {"total_count": 1, "items": [{"date": "2025-12-01", "type": "AD01"}]},
        "/officers/REALOFFICERID0001/appointments": {"name": "SMITH, John William", "total_results": 1, "items": [
            {"appointed_to": {"company_number": "01234567", "company_name": "REAL SECRET LTD", "company_status": "active"}}]},
    }  # fmt: skip


def fetcher(api: dict[str, Any]) -> Any:
    def fetch(path: str, params: dict[str, Any] | None) -> tuple[int, dict[str, Any] | None]:
        body = api.get(path)
        return (200, body) if body is not None else (404, None)

    return fetch


def test_recorder_anonymises_and_survives_its_own_leak_check(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    anon = make_anonymiser(root, set())
    snap = record_company(fetcher(fake_api()), "01234567", date(2026, 3, 4), anon)
    assert snap is not None
    text = snap.model_dump_json()
    for secret in (
        "SMITH",
        "REAL SECRET",
        "SECRET BANK",
        "REALOFFICERID0001",
        "01234567",
        "AB1 2CD",
        "1970",
    ):
        assert secret not in text, secret
    assert snap.meta.company_number.startswith("91")
    assert leak_problems(snap) == []
    assert len(snap.appointments) == 1 and next(iter(snap.appointments)).startswith("OFFICERID")
    assert snap.endpoints["insolvency"].status == 404


def test_recorder_aliases_are_stable_across_sessions(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    a1 = make_anonymiser(root, set())
    first = record_company(fetcher(fake_api()), "01234567", date(2026, 3, 4), a1)
    a1.save()
    a2 = make_anonymiser(root, set())  # a new session reads the private mapping file
    second = record_company(fetcher(fake_api()), "01234567", date(2026, 3, 4), a2)
    assert first and second and first.meta.company_number == second.meta.company_number
    assert (root / "data" / "raw" / "eval_mapping.json").exists()


def test_recorder_refuses_to_write_a_leaky_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_root(tmp_path)
    anon = make_anonymiser(root, set())
    monkeypatch.setattr(anon, "officers", lambda body: body)  # a scrubber that forgets to scrub
    with pytest.raises(AssertionError, match="leak"):
        record_company(fetcher(fake_api()), "01234567", date(2026, 3, 4), anon)


def test_recorder_returns_none_for_unknown_company(tmp_path: Path) -> None:
    anon = make_anonymiser(make_root(tmp_path), set())
    assert record_company(fetcher({}), "99999999", date(2026, 3, 4), anon) is None


def test_recorder_pages_through_long_lists(tmp_path: Path) -> None:
    api = fake_api()
    items = [{"status": "outstanding"} for _ in range(130)]

    def fetch(path: str, params: dict[str, Any] | None) -> tuple[int, dict[str, Any] | None]:
        if path.endswith("/charges"):
            start = int((params or {}).get("start_index", 0))
            return 200, {"total_count": 130, "items": items[start : start + 100]}
        return fetcher(api)(path, params)

    snap = record_company(
        fetch, "01234567", date(2026, 3, 4), make_anonymiser(make_root(tmp_path), set())
    )
    assert snap is not None and len(snap.endpoints["charges"].body["items"]) == 100  # type: ignore[index]
    assert "charges" in snap.meta.truncated  # the cap was hit and the snapshot says so


# ---- authoring -------------------------------------------------------------------------------
def test_generated_abstention_cases_are_valid_and_cover_many_fault_types() -> None:
    ds = Dataset(REPO / "evals", "demo")
    snaps = {
        c.company_number: Snapshot.load(ds.snapshot_dir / f"{c.company_number}.json")
        for c in ds.companies
    }
    cases = gen_abstention(ds.companies, snaps, [])
    assert len(cases) == len(ds.companies)
    assert len({tuple(f.tool for f in c.faults) for c in cases}) > 3
    again = gen_abstention(ds.companies, snaps, cases)
    assert [c.id for c in again] == [c.id for c in cases]  # idempotent: existing cases are kept


def test_injection_seeds_are_complete() -> None:
    cases = injection_cases()
    assert len(cases) >= 15 and len({c.id for c in cases}) == len(cases)
    assert {c.kind for c in cases} == {
        "company_name",
        "officer_name",
        "charge_holder",
        "registry_text",
    }


def test_company_entry_roundtrip() -> None:
    c = CompanyEntry(
        id="c001", company_number="91000001", as_of=date(2026, 1, 1), split=split_for("c001")
    )
    assert CompanyEntry.model_validate_json(c.model_dump_json()) == c
