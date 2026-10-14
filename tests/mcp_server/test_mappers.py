"""Mappers against fixture data, including the data-minimisation guarantee."""

import json
from datetime import date

from conftest import TODAY, load_fixture
from ukvet_mcp.mappers import (
    map_appointment,
    map_charge,
    map_filing,
    map_insolvency_case,
    map_officer,
    map_profile,
    map_psc,
    map_search_hit,
)
from ukvet_mcp.models import Appointment, CompanyProfile, Officer, PersonWithSignificantControl

PERSONAL_FIELDS = {"date_of_birth", "address", "nationality", "occupation", "country_of_residence"}


def test_profile_fields_and_computed_age() -> None:
    p = map_profile(load_fixture("12345678__profile"), TODAY)
    assert p.company_name == "ACME TEST LTD"
    assert p.status == "active"
    assert p.date_of_creation == date(2019, 3, 4)
    assert p.age_days == 2557
    assert p.age_years == 7.0
    assert p.accounts.overdue is True
    assert p.accounts.last_made_up_to == date(2023, 3, 31)
    assert p.confirmation_statement.overdue is False
    assert p.has_charges is True
    assert p.has_insolvency_history is False


def test_dissolved_company_age_stops_at_cessation() -> None:
    p = map_profile(load_fixture("87654321__profile"), TODAY)
    assert p.status == "dissolved"
    assert p.date_of_cessation == date(2022, 6, 1)
    assert p.age_days == (date(2022, 6, 1) - date(2018, 1, 15)).days
    assert p.accounts.overdue is None  # missing in source -> None, never guessed


def test_profile_tolerates_missing_optional_sections() -> None:
    p = map_profile({"company_number": "00000001", "company_name": "X"}, TODAY)
    assert p.age_days is None
    assert p.sic_codes == []
    assert p.accounts.next_due is None


def test_profile_drops_registered_office_address() -> None:
    p = map_profile(load_fixture("12345678__profile"), TODAY)
    assert "registered_office_address" not in CompanyProfile.model_fields
    assert "TEST STREET" not in p.model_dump_json()


def test_officers_extract_ids_and_drop_personal_data() -> None:
    items = load_fixture("12345678__officers")["items"]
    officers = [map_officer(i) for i in items]
    assert [o.officer_id for o in officers] == [
        "OFFICERIDA1",
        "OFFICERIDB1",
        "OFFICERIDC1",
        "OFFICERIDD1",
    ]
    assert [o.is_active for o in officers] == [True, True, True, False]
    assert officers[3].resigned_on == date(2024, 10, 1)
    assert not PERSONAL_FIELDS & set(Officer.model_fields)
    blob = json.dumps([o.model_dump(mode="json") for o in officers])
    for leaked in ("1980", "British", "Engineer", "TEST STREET"):
        assert leaked not in blob


def test_appointments_drop_personal_data() -> None:
    items = load_fixture("officer_a__appointments")["items"]
    appts = [map_appointment(i) for i in items]
    assert appts[1].company_status == "dissolved"
    assert appts[1].is_active is False
    assert not PERSONAL_FIELDS & set(Appointment.model_fields)
    assert "1980" not in json.dumps([a.model_dump(mode="json") for a in appts])


def test_psc_individual_corporate_and_ceased() -> None:
    items = load_fixture("12345678__psc")["items"]
    pscs = [map_psc(i) for i in items]
    assert [p.is_corporate for p in pscs] == [False, True, False]
    assert [p.ceased for p in pscs] == [False, False, True]
    assert pscs[0].natures_of_control == ["ownership-of-shares-25-to-50-percent"]
    assert not PERSONAL_FIELDS & set(PersonWithSignificantControl.model_fields)


def test_psc_super_secure_has_no_name() -> None:
    p = map_psc({"kind": "super-secure-person-with-significant-control"})
    assert p.name == "Not disclosed"


def test_charges() -> None:
    items = load_fixture("12345678__charges")["items"]
    charges = [map_charge(i) for i in items]
    assert charges[0].status == "outstanding"
    assert charges[0].classification == "A registered charge"
    assert charges[0].persons_entitled == ["TEST BANK PLC"]
    assert charges[1].satisfied_on == date(2022, 8, 9)


def test_insolvency_case() -> None:
    case = map_insolvency_case(load_fixture("87654321__insolvency")["cases"][0])
    assert case.type == "creditors-voluntary-liquidation"
    assert case.dates[0].date == date(2021, 11, 2)
    assert "PRACTITIONER" not in case.model_dump_json()


def test_filings_have_plain_english_and_address_flag() -> None:
    items = load_fixture("12345678__filing-history")["items"]
    filings = [map_filing(i) for i in items]
    assert filings[1].type == "AD01"
    assert filings[1].is_address_change is True
    assert filings[1].description == "Registered office address changed"
    assert filings[1].raw_description.startswith("change-registered-office")  # type: ignore[union-attr]
    assert [f.is_address_change for f in filings].count(True) == 1


def test_search_hit() -> None:
    hit = map_search_hit(load_fixture("search__acme")["items"][0])
    assert (hit.company_number, hit.name, hit.status) == ("12345678", "ACME TEST LTD", "active")
