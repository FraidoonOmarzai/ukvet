"""Output models.

Design rules:
- Every tool returns a `ToolResult` carrying a `Source`, so every fact can be cited.
- Models include ONLY the fields needed for questions Q1-Q10. Dates of birth, addresses,
  nationality and occupation are deliberately absent (UK GDPR data minimisation; see
  docs/06-legal-and-ethics.md).
- Counts and ages are computed here, not left for the LLM to work out.
"""

from datetime import date, datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class Source(BaseModel):
    endpoint: str = Field(
        description="Companies House API endpoint the data came from."
    )
    url: str = Field(
        description="Public Companies House page where anyone can verify the data."
    )
    retrieved_at: datetime = Field(
        description="When the data was fetched from Companies House (UTC). May be up to 24h old."
    )
    from_cache: bool = Field(description="True if served from the local cache.")


class ToolResult(BaseModel, Generic[T]):
    found: bool = Field(
        description="False means Companies House holds NO matching records. This is a valid "
        "answer (e.g. a company with no charges), not an error."
    )
    data: T
    source: Source
    notes: list[str] = Field(
        default_factory=list,
        description="Caveats the reader must respect, e.g. truncated results.",
    )


class Listing(BaseModel):
    """Common fields for list results."""

    total: int | None = Field(
        description="Total records Companies House reports, if known."
    )
    returned: int = Field(description="Number of records in `items`.")
    truncated: bool = Field(
        description="True if more records exist than were returned."
    )


# ---- search -------------------------------------------------------------------------------


class SearchHit(BaseModel):
    company_number: str
    name: str
    status: str | None
    company_type: str | None
    date_of_creation: date | None
    address_snippet: str | None = Field(
        description="Short registered-office snippet, to tell apart companies with similar names."
    )


class SearchData(Listing):
    query: str
    items: list[SearchHit]


# ---- profile (Q1, Q2, Q4) -------------------------------------------------------------------


class AccountsInfo(BaseModel):
    next_due: date | None
    overdue: bool | None
    last_made_up_to: date | None


class ConfirmationStatementInfo(BaseModel):
    next_due: date | None
    overdue: bool | None
    last_made_up_to: date | None


class CompanyProfile(BaseModel):
    company_number: str
    company_name: str
    status: str | None = Field(
        description="e.g. active, dissolved, liquidation, administration."
    )
    status_detail: str | None
    company_type: str | None
    date_of_creation: date | None
    date_of_cessation: date | None
    age_days: int | None = Field(
        description="Days from incorporation to today (or to cessation if dissolved). Computed."
    )
    age_years: float | None = Field(
        description="age_days / 365.25, one decimal. Computed."
    )
    sic_codes: list[str]
    accounts: AccountsInfo
    confirmation_statement: ConfirmationStatementInfo
    has_charges: bool | None
    has_insolvency_history: bool | None


# ---- officers (Q3, Q9) ----------------------------------------------------------------------


class Officer(BaseModel):
    officer_id: str | None = Field(
        description="Pass to get_officer_appointments. The same real person can appear under "
        "several IDs."
    )
    name: str
    role: str
    appointed_on: date | None
    resigned_on: date | None
    is_active: bool = Field(
        description="True if the officer has not resigned. Computed."
    )


class OfficersData(Listing):
    active_count: int | None
    resigned_count: int | None
    items: list[Officer]


# ---- appointments (Q8) ------------------------------------------------------------------------


class Appointment(BaseModel):
    company_number: str
    company_name: str
    company_status: str | None
    role: str | None
    appointed_on: date | None
    resigned_on: date | None
    is_active: bool


class AppointmentsData(Listing):
    officer_id: str
    officer_name: str | None
    status_counts: dict[str, int] = Field(
        description="Count of listed companies by status. Computed; use these, do not recount."
    )
    items: list[Appointment]


# ---- persons with significant control (Q5) ----------------------------------------------------


class PersonWithSignificantControl(BaseModel):
    name: str
    kind: str
    is_corporate: bool = Field(
        description="True if the controller is a company/legal entity."
    )
    natures_of_control: list[str]
    notified_on: date | None
    ceased_on: date | None
    ceased: bool


class PscData(Listing):
    active_count: int | None
    ceased_count: int | None
    items: list[PersonWithSignificantControl]


# ---- charges (Q6) -------------------------------------------------------------------------------


class Charge(BaseModel):
    charge_number: int | None
    charge_code: str | None
    status: str | None
    classification: str | None
    created_on: date | None
    satisfied_on: date | None
    persons_entitled: list[str]


class ChargesData(Listing):
    outstanding_count: int = Field(
        description="Charges with status 'outstanding'. Computed."
    )
    part_satisfied_count: int = Field(
        description="Charges with status 'part-satisfied'. Computed."
    )
    satisfied_count: int = Field(description="Fully satisfied charges. Computed.")
    items: list[Charge]


# ---- insolvency (Q7) ----------------------------------------------------------------------------


class InsolvencyDate(BaseModel):
    type: str
    date: date | None


class InsolvencyCase(BaseModel):
    case_number: int | None
    type: str
    dates: list[InsolvencyDate]


class InsolvencyData(BaseModel):
    case_count: int
    statuses: list[str]
    cases: list[InsolvencyCase]


# ---- filing history (Q9) -------------------------------------------------------------------------


class Filing(BaseModel):
    date: date | None
    type: str | None = Field(description="Companies House form code, e.g. AD01.")
    category: str | None
    description: str = Field(description="Plain-English description.")
    raw_description: str | None
    paper_filed: bool
    is_address_change: bool = Field(
        description="True for registered-office changes (AD01)."
    )
    transaction_id: str | None


class FilingsData(Listing):
    since: date | None
    category: str | None
    items: list[Filing]
