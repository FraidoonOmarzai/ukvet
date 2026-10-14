"""Pure functions: raw Companies House JSON -> our minimal output models.

Only fields needed for Q1-Q10 are copied (data minimisation). Counts and ages are computed here.
"""

from datetime import date
from typing import Any

from ukvet_mcp.filing_codes import describe_filing, is_address_change
from ukvet_mcp.models import (
    AccountsInfo,
    Appointment,
    Charge,
    CompanyProfile,
    ConfirmationStatementInfo,
    Filing,
    InsolvencyCase,
    InsolvencyDate,
    Officer,
    PersonWithSignificantControl,
    SearchHit,
)
from ukvet_mcp.normalise import officer_id_from_link

Raw = dict[str, Any]


def _date(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _obj(value: Any) -> Raw:
    return value if isinstance(value, dict) else {}


def map_search_hit(item: Raw) -> SearchHit:
    return SearchHit(
        company_number=item["company_number"],
        name=item.get("title") or "",
        status=item.get("company_status"),
        company_type=item.get("company_type"),
        date_of_creation=_date(item.get("date_of_creation")),
        address_snippet=item.get("address_snippet"),
    )


def map_profile(body: Raw, today: date) -> CompanyProfile:
    accounts = _obj(body.get("accounts"))
    confirmation = _obj(body.get("confirmation_statement"))
    created = _date(body.get("date_of_creation"))
    ceased = _date(body.get("date_of_cessation"))

    age_days: int | None = None
    age_years: float | None = None
    if created is not None:
        end = ceased or today
        age_days = max(0, (end - created).days)
        age_years = round(age_days / 365.25, 1)

    return CompanyProfile(
        company_number=body["company_number"],
        company_name=body["company_name"],
        status=body.get("company_status"),
        status_detail=body.get("company_status_detail"),
        company_type=body.get("type"),
        date_of_creation=created,
        date_of_cessation=ceased,
        age_days=age_days,
        age_years=age_years,
        sic_codes=[str(c) for c in body.get("sic_codes", [])],
        accounts=AccountsInfo(
            next_due=_date(accounts.get("next_due")),
            overdue=accounts.get("overdue"),
            last_made_up_to=_date(_obj(accounts.get("last_accounts")).get("made_up_to")),
        ),
        confirmation_statement=ConfirmationStatementInfo(
            next_due=_date(confirmation.get("next_due")),
            overdue=confirmation.get("overdue"),
            last_made_up_to=_date(confirmation.get("last_made_up_to")),
        ),
        has_charges=body.get("has_charges"),
        has_insolvency_history=body.get("has_insolvency_history"),
    )


def map_officer(item: Raw) -> Officer:
    links = _obj(_obj(item.get("links")).get("officer"))
    resigned = _date(item.get("resigned_on"))
    return Officer(
        officer_id=officer_id_from_link(links.get("appointments")),
        name=item.get("name") or "Not disclosed",
        role=item.get("officer_role") or "unknown",
        appointed_on=_date(item.get("appointed_on")),
        resigned_on=resigned,
        is_active=resigned is None,
    )


def map_appointment(item: Raw) -> Appointment:
    target = _obj(item.get("appointed_to"))
    resigned = _date(item.get("resigned_on"))
    return Appointment(
        company_number=target["company_number"],
        company_name=target.get("company_name") or "",
        company_status=target.get("company_status"),
        role=item.get("officer_role"),
        appointed_on=_date(item.get("appointed_on")),
        resigned_on=resigned,
        is_active=resigned is None,
    )


def map_psc(item: Raw) -> PersonWithSignificantControl:
    kind = item.get("kind") or "unknown"
    ceased_on = _date(item.get("ceased_on"))
    return PersonWithSignificantControl(
        name=item.get("name") or "Not disclosed",
        kind=kind,
        is_corporate="corporate-entity" in kind or "legal-person" in kind,
        natures_of_control=[str(n) for n in item.get("natures_of_control", [])],
        notified_on=_date(item.get("notified_on")),
        ceased_on=ceased_on,
        ceased=bool(item.get("ceased")) or ceased_on is not None,
    )


def map_charge(item: Raw) -> Charge:
    return Charge(
        charge_number=item.get("charge_number"),
        charge_code=item.get("charge_code"),
        status=item.get("status"),
        classification=_obj(item.get("classification")).get("description"),
        created_on=_date(item.get("created_on")),
        satisfied_on=_date(item.get("satisfied_on")),
        persons_entitled=[
            str(p["name"]) for p in item.get("persons_entitled", []) if _obj(p).get("name")
        ],
    )


def map_insolvency_case(item: Raw) -> InsolvencyCase:
    return InsolvencyCase(
        case_number=item.get("number"),
        type=item.get("type") or "unknown",
        dates=[
            InsolvencyDate(type=d.get("type") or "unknown", date=_date(d.get("date")))
            for d in item.get("dates", [])
            if isinstance(d, dict)
        ],
    )


def map_filing(item: Raw) -> Filing:
    code = item.get("type")
    slug = item.get("description")
    return Filing(
        date=_date(item.get("date")),
        type=code,
        category=item.get("category"),
        description=describe_filing(code, slug),
        raw_description=slug,
        paper_filed=bool(item.get("paper_filed")),
        is_address_change=is_address_change(code),
        transaction_id=item.get("transaction_id"),
    )
