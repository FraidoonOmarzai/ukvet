import json
from datetime import date

import httpx
import pytest
import respx
from conftest import TODAY, FakeClock, make_client
from ukvet_mcp.config import Settings
from ukvet_mcp.errors import (
    CompanyNotFound,
    InvalidInput,
    OfficerNotFound,
    UpstreamError,
)
from ukvet_mcp.service import CompaniesHouseService

pytestmark = pytest.mark.usefixtures("ch_api")

PUBLIC = "https://find-and-update.company-information.service.gov.uk"


# ---- profile (Q1, Q2, Q4) -------------------------------------------------------------------


async def test_profile(service: CompaniesHouseService) -> None:
    r = await service.get_company_profile("12345678")
    assert r.found is True
    assert r.data.company_name == "ACME TEST LTD"
    assert r.data.age_days == 2557
    assert r.data.accounts.overdue is True
    assert r.source.endpoint == "/company/12345678"
    assert r.source.url == f"{PUBLIC}/company/12345678"
    assert r.source.from_cache is False


async def test_profile_pads_short_numbers(service: CompaniesHouseService) -> None:
    r = await service.get_company_profile(" 12345678 ")
    assert r.data.company_number == "12345678"


async def test_profile_unknown_company_raises_not_found(service: CompaniesHouseService) -> None:
    with pytest.raises(CompanyNotFound) as err:
        await service.get_company_profile("404")
    assert "00000404" in str(err.value)
    assert "search_company" in str(err.value)


async def test_profile_invalid_number(service: CompaniesHouseService) -> None:
    with pytest.raises(InvalidInput):
        await service.get_company_profile("not a number")


async def test_unexpected_response_shape_is_a_clean_upstream_error(
    router: respx.MockRouter, service: CompaniesHouseService
) -> None:
    router.routes.clear()
    router.get("/company/12345678").mock(
        return_value=httpx.Response(200, json={"company_number": "12345678"})  # no company_name
    )
    with pytest.raises(UpstreamError) as err:
        await service.get_company_profile("12345678")
    assert "unexpected shape" in str(err.value)


# ---- officers (Q3, Q9) ----------------------------------------------------------------------


async def test_officers_default_to_current_only(service: CompaniesHouseService) -> None:
    r = await service.get_officers("12345678")
    assert r.found is True
    assert [o.name for o in r.data.items] == ["DIRECTOR A", "DIRECTOR B", "SECRETARY C"]
    assert (r.data.active_count, r.data.resigned_count, r.data.total) == (3, 1, 4)
    assert all(o.officer_id for o in r.data.items)
    assert r.notes == []


async def test_officers_include_resigned(service: CompaniesHouseService) -> None:
    r = await service.get_officers("12345678", include_resigned=True)
    assert len(r.data.items) == 4
    assert r.data.items[3].is_active is False


async def test_officers_output_has_no_personal_data(service: CompaniesHouseService) -> None:
    blob = (await service.get_officers("12345678", include_resigned=True)).model_dump_json()
    for leaked in ("1980", "British", "Engineer", "TEST STREET", "England"):
        assert leaked not in blob


async def test_officers_truncation_is_flagged(settings: Settings, clock: FakeClock) -> None:
    small = CompaniesHouseService(make_client(settings, clock), max_items=2, today=lambda: TODAY)
    r = await small.get_officers("12345678", include_resigned=True)
    assert r.data.truncated is True
    assert r.data.returned == 2
    assert any("may be missing" in n for n in r.notes)


async def test_officers_unknown_company(service: CompaniesHouseService) -> None:
    with pytest.raises(CompanyNotFound):
        await service.get_officers("404")


async def test_officers_all_resigned_note(
    router: respx.MockRouter, service: CompaniesHouseService
) -> None:
    router.routes.clear()
    router.get("/company/12345678/officers").mock(
        return_value=httpx.Response(
            200,
            json={
                "total_results": 1,
                "active_count": 0,
                "resigned_count": 1,
                "items": [{"name": "X", "officer_role": "director", "resigned_on": "2020-01-01"}],
            },
        )
    )
    r = await service.get_officers("12345678")
    assert r.found is False
    assert any("all of them have resigned" in n for n in r.notes)


# ---- appointments (Q8) ----------------------------------------------------------------------


async def test_appointments_with_computed_status_counts(service: CompaniesHouseService) -> None:
    r = await service.get_officer_appointments("OFFICERIDA1")
    assert r.found is True
    assert r.data.officer_name == "DIRECTOR A"
    assert r.data.returned == 4
    assert r.data.status_counts == {"active": 2, "dissolved": 1, "liquidation": 1}
    assert r.source.url == f"{PUBLIC}/officers/OFFICERIDA1/appointments"


async def test_appointments_can_exclude_the_company_being_checked(
    service: CompaniesHouseService,
) -> None:
    r = await service.get_officer_appointments("OFFICERIDA1", exclude_company_number="12345678")
    assert r.data.returned == 3
    assert "12345678" not in {a.company_number for a in r.data.items}
    assert r.data.status_counts == {"active": 1, "dissolved": 1, "liquidation": 1}
    assert any("Excluded the company being checked" in n for n in r.notes)


async def test_appointments_unknown_officer(service: CompaniesHouseService) -> None:
    with pytest.raises(OfficerNotFound) as err:
        await service.get_officer_appointments("NOSUCHOFFICER")
    assert "get_officers" in str(err.value)


@pytest.mark.parametrize("bad", ["", "x", "has space", "../../etc"])
async def test_appointments_invalid_officer_id(service: CompaniesHouseService, bad: str) -> None:
    with pytest.raises(InvalidInput):
        await service.get_officer_appointments(bad)


async def test_appointments_invalid_max_items(service: CompaniesHouseService) -> None:
    with pytest.raises(InvalidInput):
        await service.get_officer_appointments("OFFICERIDA1", max_items=0)


async def test_appointments_truncation_note(settings: Settings, clock: FakeClock) -> None:
    svc = CompaniesHouseService(make_client(settings, clock), today=lambda: TODAY)
    r = await svc.get_officer_appointments("OFFICERIDA1", max_items=2)
    assert r.data.truncated is True
    assert r.data.returned == 2
    assert any("status_counts cover only the listed" in n for n in r.notes)


# ---- PSC (Q5) -------------------------------------------------------------------------------


async def test_psc_current_only_by_default(service: CompaniesHouseService) -> None:
    r = await service.get_persons_with_significant_control("12345678")
    assert [p.name for p in r.data.items] == ["PERSON A", "HOLDCO TEST LTD"]
    assert [p.is_corporate for p in r.data.items] == [False, True]
    assert (r.data.active_count, r.data.ceased_count) == (2, 1)


async def test_psc_include_ceased(service: CompaniesHouseService) -> None:
    r = await service.get_persons_with_significant_control("12345678", include_ceased=True)
    assert len(r.data.items) == 3


async def test_psc_none_found_warns_against_concluding_no_owner(
    service: CompaniesHouseService,
) -> None:
    r = await service.get_persons_with_significant_control("87654321")  # 404 -> company exists
    assert r.found is False
    assert any("does NOT prove" in n for n in r.notes)


# ---- charges (Q6) ---------------------------------------------------------------------------


async def test_charges_with_computed_counts(service: CompaniesHouseService) -> None:
    r = await service.get_charges("12345678")
    assert r.found is True
    assert (r.data.outstanding_count, r.data.satisfied_count, r.data.part_satisfied_count) == (
        1,
        1,
        0,
    )
    assert r.data.total == 2


async def test_charges_200_empty_means_no_charges(service: CompaniesHouseService) -> None:
    r = await service.get_charges("87654321")
    assert r.found is False
    assert r.data.items == []
    assert r.data.outstanding_count == 0


async def test_charges_unknown_company(service: CompaniesHouseService) -> None:
    with pytest.raises(CompanyNotFound):
        await service.get_charges("404")


# ---- insolvency (Q7) ------------------------------------------------------------------------


async def test_insolvency_404_for_existing_company_means_no_record(
    service: CompaniesHouseService,
) -> None:
    r = await service.get_insolvency("12345678")
    assert r.found is False
    assert r.data.case_count == 0
    assert any("no insolvency record" in n for n in r.notes)


async def test_insolvency_404_for_missing_company_is_not_found_not_no_data(
    service: CompaniesHouseService,
) -> None:
    """The ambiguous-404 trap: 'no insolvency record' must not be reported for a company that
    does not exist."""
    with pytest.raises(CompanyNotFound):
        await service.get_insolvency("404")


async def test_insolvency_case_present(service: CompaniesHouseService) -> None:
    r = await service.get_insolvency("87654321")
    assert r.found is True
    assert r.data.case_count == 1
    assert r.data.statuses == ["liquidation-in-progress"]
    assert r.data.cases[0].type == "creditors-voluntary-liquidation"


# ---- filing history (Q9) --------------------------------------------------------------------


async def test_filing_history_all(service: CompaniesHouseService) -> None:
    r = await service.get_filing_history("12345678")
    assert r.data.returned == 5
    assert [f for f in r.data.items if f.is_address_change][0].date == date(2025, 9, 15)
    assert r.data.truncated is False


async def test_filing_history_since_filters_and_stops_early(
    ch_api: respx.MockRouter, service: CompaniesHouseService
) -> None:
    r = await service.get_filing_history("12345678", since="2025-06-01")
    assert [f.type for f in r.data.items] == ["CS01", "AD01"]
    assert r.data.since == date(2025, 6, 1)
    assert r.data.truncated is False
    assert any("on or after 2025-06-01" in n for n in r.notes)


async def test_filing_history_category_is_sent_to_the_api(
    ch_api: respx.MockRouter, service: CompaniesHouseService
) -> None:
    await service.get_filing_history("12345678", category="Address")
    request = [c.request for c in ch_api.calls if "filing-history" in c.request.url.path][-1]
    assert request.url.params["category"] == "address"


async def test_filing_history_validation(service: CompaniesHouseService) -> None:
    with pytest.raises(InvalidInput, match="YYYY-MM-DD"):
        await service.get_filing_history("12345678", since="last week")
    with pytest.raises(InvalidInput):
        await service.get_filing_history("12345678", category="x; drop")
    with pytest.raises(InvalidInput):
        await service.get_filing_history("12345678", max_items=0)


async def test_filing_history_truncation_note(settings: Settings, clock: FakeClock) -> None:
    svc = CompaniesHouseService(make_client(settings, clock), max_items=100, today=lambda: TODAY)
    r = await svc.get_filing_history("12345678", max_items=2)
    assert r.data.truncated is True
    assert any("older filings exist" in n for n in r.notes)


# ---- search ---------------------------------------------------------------------------------


async def test_search_found(service: CompaniesHouseService) -> None:
    r = await service.search_company("Acme")
    assert r.found is True
    assert [h.company_number for h in r.data.items] == ["12345678", "11111111"]
    assert r.source.url == f"{PUBLIC}/search/companies?q=Acme"


async def test_search_no_results_is_not_an_error(service: CompaniesHouseService) -> None:
    r = await service.search_company("zzzzzz")
    assert r.found is False
    assert r.data.items == []


async def test_search_truncation_note(
    router: respx.MockRouter, service: CompaniesHouseService
) -> None:
    router.routes.clear()
    router.get("/search/companies").mock(
        return_value=httpx.Response(
            200,
            json={
                "total_results": 57,
                "items": [{"title": "A LTD", "company_number": "00000001"}],
            },
        )
    )
    r = await service.search_company("a", limit=1)
    assert r.data.truncated is True
    assert any("57 matches" in n for n in r.notes)


@pytest.mark.parametrize(
    ("query", "limit"), [("", 10), ("   ", 10), ("x" * 201, 10), ("acme", 0), ("acme", 21)]
)
async def test_search_validation(service: CompaniesHouseService, query: str, limit: int) -> None:
    with pytest.raises(InvalidInput):
        await service.search_company(query, limit)


async def test_search_query_is_url_encoded_in_source(service: CompaniesHouseService) -> None:
    r = await service.search_company("acme & sons")
    assert "acme%20%26%20sons" in r.source.url


async def test_results_serialise_to_json(service: CompaniesHouseService) -> None:
    """Every tool result must be JSON-serialisable (dates, datetimes) for MCP."""
    for result in (
        await service.get_company_profile("12345678"),
        await service.get_officers("12345678"),
        await service.get_filing_history("12345678"),
    ):
        json.loads(result.model_dump_json())
