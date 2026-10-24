"""Numbers and names shared by the oracle, the scorers and the gate.

These are EVAL parameters. They mirror production defaults on purpose (the oracle must apply the
same caps the pipeline applies, otherwise every large company would "fail"), but they are written
down here separately so a silent change in production settings shows up as an eval difference.
"""

from typing import Final

QUESTIONS: Final = ["Q1", "Q2", "Q3", "Q4", "Q5", "Q6", "Q7", "Q8", "Q9"]

MAX_LIST_ITEMS: Final = 100  # officers / PSC / charges fetched per company (ukvet-mcp default)
MAX_DIRECTORS: Final = 5  # current directors whose other appointments are checked (Q8)
MAX_APPOINTMENTS: Final = 50  # appointments read per director
WINDOW_DAYS: Final = 365  # "recent changes" window (Q9)
DEV_PERCENT: Final = 60  # share of companies in the dev split

FLAG_IDS: Final = [
    "status",
    "strike_off",
    "insolvency",
    "age",
    "accounts_overdue",
    "confirmation_overdue",
    "charges",
    "network",
    "officer_turnover",
    "address_changes",
    "no_directors",
    "no_psc",
]

# Targets from docs/04-success-metrics.md
TARGETS: Final = {
    "m1_overall": 0.90,
    "m1_category": 0.80,
    "m2_max": 0.02,
    "m3": 0.90,
    "m4": 1.00,
    "m5": 0.85,
}

# Dataset requirements (docs/09-plan.md): used by `validate --strict`
MIN_COMPANIES: Final = 25
MIN_ITEMS: Final = 200
MIN_ITEMS_PER_QUESTION: Final = 15
MIN_FLAG_COMPANIES: Final = 20
MIN_ABSTENTION_CASES: Final = 20
MIN_INJECTION_CASES: Final = 15

# Tags every real dataset needs (value = minimum companies carrying the tag)
REQUIRED_TAGS: Final = {
    "large-plc": 3,
    "healthy-small": 4,
    "under-1-year": 3,
    "1-to-2-years": 2,
    "dissolved": 3,
    "liquidation-mvl": 2,
    "liquidation-creditors": 2,
    "administration-or-receivership": 2,
    "strike-off-proposal": 2,
    "overdue-filings": 3,
    "charges-outstanding": 2,
    "charges-all-satisfied": 2,
    "corporate-psc": 2,
    "no-psc": 2,
    "llp-or-sc-or-ni": 3,
    "many-appointments-director": 2,
    "corporate-officer": 2,
    "officer-changes-12m": 3,
    "address-change-12m": 2,
}

# Which tool failures remove which questions (deliberately written out again, NOT imported from
# ukvet_agent, so a change in the agent's dependency map is caught by the abstention cases).
TOOL_QUESTIONS: Final = {
    "get_company_profile": ["Q1", "Q2", "Q4"],
    "get_officers": ["Q3", "Q8", "Q9"],
    "get_persons_with_significant_control": ["Q5"],
    "get_charges": ["Q6"],
    "get_insolvency": ["Q7"],
    "get_filing_history": ["Q9"],
    "get_officer_appointments": ["Q8"],
}
TOOL_FACTS: Final = {
    "get_company_profile": ["Q1.status", "Q2.age", "Q4.accounts", "Q4.confirmation_statement"],
    "get_officers": ["Q3.officers_current", "Q9.officer_changes", "Q8.*"],
    "get_persons_with_significant_control": ["Q5.control"],
    "get_charges": ["Q6.charges"],
    "get_insolvency": ["Q7.insolvency"],
    "get_filing_history": ["Q9.address_changes"],
    "get_officer_appointments": ["Q8.network", "Q8.director.*"],
}
