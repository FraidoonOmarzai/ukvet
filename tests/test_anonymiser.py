"""The anonymiser is a UK GDPR control, so it gets real tests, including an end-to-end run of the
recorder against a mocked API with realistic-looking personal data."""

import importlib.util
import json
import sys
from pathlib import Path

import httpx
import pytest
import respx

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def load(name: str):  # type: ignore[no-untyped-def]
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


anonymise = load("anonymise")
record_fixtures = load("record_fixtures")

REAL_PERSON = "SMITHERS, Jonathan Quentin"
REAL_PERSON_2 = "OKAFOR, Amara"
REAL_COMPANY = "SMITHERS PLUMBING & HEATING LTD"
REAL_OFFICER_ID = "xYz9Qk2LmNoPqRsTuVwAbCdEfGh"
REAL_NUMBER = "09876543"
LINKED_NUMBER = "11223344"
LINKED_NAME = "JONATHAN SMITHERS CONSULTING LTD"
REAL_BANK = "HIGH STREET BANK PLC"

PROFILE = {
    "company_number": REAL_NUMBER,
    "company_name": REAL_COMPANY,
    "company_status": "active",
    "type": "ltd",
    "date_of_creation": "2020-01-02",
    "has_charges": True,
    "registered_office_address": {"address_line_1": "14 Acacia Avenue", "postal_code": "S1 2AB"},
    "accounts": {"overdue": False},
    "etag": "abc123",
}
OFFICERS = {
    "total_results": 2,
    "active_count": 2,
    "resigned_count": 0,
    "items": [
        {
            "name": REAL_PERSON,
            "officer_role": "director",
            "appointed_on": "2020-01-02",
            "date_of_birth": {"month": 4, "year": 1975},
            "nationality": "British",
            "occupation": "Plumber",
            "address": {"address_line_1": "14 Acacia Avenue"},
            "links": {"officer": {"appointments": f"/officers/{REAL_OFFICER_ID}/appointments"}},
        },
        {
            "name": REAL_PERSON_2,
            "officer_role": "secretary",
            "appointed_on": "2020-01-02",
            "links": {"officer": {"appointments": "/officers/AnotherOfficerId0001/appointments"}},
        },
    ],
}
APPOINTMENTS = {
    "name": REAL_PERSON,
    "total_results": 2,
    "items": [
        {
            "name": REAL_PERSON,
            "officer_role": "director",
            "appointed_on": "2020-01-02",
            "address": {"address_line_1": "14 Acacia Avenue"},
            "appointed_to": {
                "company_number": REAL_NUMBER,
                "company_name": REAL_COMPANY,
                "company_status": "active",
            },
        },
        {
            "name": REAL_PERSON,
            "officer_role": "director",
            "appointed_on": "2015-05-05",
            "resigned_on": "2018-01-01",
            "appointed_to": {
                "company_number": LINKED_NUMBER,
                "company_name": LINKED_NAME,
                "company_status": "dissolved",
            },
        },
    ],
}
CHARGES = {
    "total_count": 1,
    "items": [
        {
            "status": "outstanding",
            "charge_number": 1,
            "particulars": {"description": "all assets of J Smithers"},
            "persons_entitled": [{"name": REAL_BANK}],
        }
    ],
}
PSC = {
    "total_results": 2,
    "items": [
        {
            "name": REAL_PERSON,
            "kind": "individual-person-with-significant-control",
            "nationality": "British",
            "date_of_birth": {"month": 4, "year": 1975},
            "address": {"address_line_1": "14 Acacia Avenue"},
        },
        {
            "name": "PARENT HOLDINGS LTD",
            "kind": "corporate-entity-person-with-significant-control",
            "identification": {"registration_number": "00998877"},
        },
    ],
}
FILINGS = {
    "total_count": 1,
    "items": [
        {
            "date": "2024-01-01",
            "type": "AD01",
            "category": "address",
            "description": (
                "change-registered-office-address-company-with-date-old-address-new-address"
            ),
            "description_values": {
                "old_address": "14 Acacia Avenue",
                "new_address": "2 Other Road",
            },
            "links": {"document_metadata": "https://x/doc/1"},
        }
    ],
}


def everything(*bodies: object) -> str:
    return json.dumps(bodies)


def test_all_endpoints_are_scrubbed() -> None:
    anon = anonymise.Anonymiser()
    out = everything(
        anon.profile(PROFILE),
        anon.officers(OFFICERS),
        anon.appointments(APPOINTMENTS),
        anon.charges(CHARGES, REAL_NUMBER),
        anon.psc(PSC),
        anon.filings(FILINGS),
    )
    for secret in (
        REAL_PERSON,
        REAL_PERSON_2,
        REAL_COMPANY,
        REAL_OFFICER_ID,
        REAL_NUMBER,
        LINKED_NUMBER,
        LINKED_NAME,
        REAL_BANK,
        "Acacia",
        "Plumber",
        "British",
        "1975",
        "00998877",
        "Smithers",
        "SMITHERS",
    ):
        assert secret not in out, f"leaked: {secret}"
    anon.leak_check([anon.profile(PROFILE), anon.officers(OFFICERS)])


def test_mappings_are_consistent_across_endpoints() -> None:
    anon = anonymise.Anonymiser()
    officers = anon.officers(OFFICERS)
    appts = anon.appointments(APPOINTMENTS)
    link = officers["items"][0]["links"]["officer"]["appointments"]
    assert link == "/officers/OFFICERID001/appointments"
    assert officers["items"][0]["name"] == appts["name"] == "PERSON 001"  # same person, same alias
    assert appts["items"][0]["appointed_to"]["company_number"] == anon.company_number(REAL_NUMBER)
    assert appts["items"][1]["appointed_to"]["company_status"] == "dissolved"  # structure preserved


def test_public_company_keeps_identity_but_its_people_do_not() -> None:
    anon = anonymise.Anonymiser(public_companies={REAL_NUMBER})
    profile = anon.profile(PROFILE)
    assert profile["company_number"] == REAL_NUMBER
    assert profile["company_name"] == REAL_COMPANY
    assert (
        anon.charges(CHARGES, REAL_NUMBER)["items"][0]["persons_entitled"][0]["name"] == REAL_BANK
    )
    assert REAL_PERSON not in json.dumps(anon.officers(OFFICERS))


def test_leak_check_catches_a_surviving_value() -> None:
    anon = anonymise.Anonymiser()
    anon.person(REAL_PERSON)
    with pytest.raises(AssertionError, match="leak"):
        anon.leak_check({"name": f"x {REAL_PERSON} y"})
    with pytest.raises(AssertionError, match="forbidden keys"):
        anon.leak_check({"date_of_birth": {"year": 1990}})


def test_recorder_end_to_end_with_mocked_api(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(record_fixtures, "OUT", tmp_path)
    monkeypatch.setattr(record_fixtures.time, "sleep", lambda _s: None)
    monkeypatch.setenv("CH_API_KEY", "test-key")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["record_fixtures.py", REAL_NUMBER, "--public"])
    with respx.mock(base_url=record_fixtures.BASE, assert_all_called=False) as r:
        r.get(f"/company/{REAL_NUMBER}").mock(return_value=httpx.Response(200, json=PROFILE))
        r.get(f"/company/{REAL_NUMBER}/officers").mock(
            return_value=httpx.Response(200, json=OFFICERS)
        )
        r.get(f"/company/{REAL_NUMBER}/persons-with-significant-control").mock(
            return_value=httpx.Response(200, json=PSC)
        )
        r.get(f"/company/{REAL_NUMBER}/charges").mock(
            return_value=httpx.Response(200, json=CHARGES)
        )
        r.get(f"/company/{REAL_NUMBER}/insolvency").mock(return_value=httpx.Response(404))
        r.get(f"/company/{REAL_NUMBER}/filing-history").mock(
            return_value=httpx.Response(200, json=FILINGS)
        )
        r.get(f"/officers/{REAL_OFFICER_ID}/appointments").mock(
            return_value=httpx.Response(200, json=APPOINTMENTS)
        )
        r.get("/officers/AnotherOfficerId0001/appointments").mock(return_value=httpx.Response(404))
        record_fixtures.main()

    files = sorted(tmp_path.glob("rec_*.json"))
    names = {f.name for f in files}
    assert "rec_91000001__profile.json" in names
    assert any("__appointments" in n for n in names)
    blob = "".join(f.read_text() for f in files)
    for secret in (
        REAL_PERSON,
        REAL_COMPANY,
        REAL_OFFICER_ID,
        REAL_NUMBER,
        LINKED_NAME,
        "Acacia",
        "Plumber",
    ):
        assert secret not in blob, f"leaked to disk: {secret}"
    for f in files:
        data = json.loads(f.read_text())
        assert data["_meta"]["synthetic"] is False
        assert data["_meta"]["anonymised"] is True
