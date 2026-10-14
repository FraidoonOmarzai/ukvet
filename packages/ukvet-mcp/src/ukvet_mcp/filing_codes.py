"""Filing form codes -> plain English.

Best effort. Companies House filing history has a machine-readable `type` (form code, e.g. AD01)
and a `description` slug (e.g. 'change-registered-office-address-company-with-date-...').
Unknown codes fall back to the humanised slug, then to the code itself.

If your fixtures show codes missing from this table, add them (and a test).
"""

ADDRESS_CHANGE_CODES = frozenset({"AD01"})

FILING_CODES: dict[str, str] = {
    "NEWINC": "Incorporation",
    "AD01": "Registered office address changed",
    "AD02": "Single alternative inspection location (SAIL) address notified or changed",
    "AD03": "Company records moved to the single alternative inspection location (SAIL)",
    "AD04": "Company records moved back to the registered office",
    "AA": "Annual accounts",
    "AP01": "Appointment of a director",
    "AP02": "Appointment of a corporate director",
    "AP03": "Appointment of a secretary",
    "AP04": "Appointment of a corporate secretary",
    "TM01": "Termination of appointment of a director",
    "TM02": "Termination of appointment of a secretary",
    "CH01": "Change of a director's details",
    "CH02": "Change of a corporate director's details",
    "CH03": "Change of a secretary's details",
    "CH04": "Change of a corporate secretary's details",
    "CS01": "Confirmation statement",
    "AR01": "Annual return",
    "SH01": "Allotment of shares",
    "MR01": "Registration of a charge",
    "MR04": "Statement of satisfaction of a charge",
    "MR05": "Statement that property charged has been released",
    "NM01": "Change of name by resolution",
    "CERTNM": "Certificate of change of name",
    "CONNOT": "Change of name notice",
    "DS01": "Application to strike the company off the register",
    "DS02": "Withdrawal of application for strike-off",
    "GAZ1": "First Gazette notice for compulsory strike-off",
    "GAZ2": "Final Gazette notice: company dissolved",
    "GAZ1(A)": "First Gazette notice for voluntary strike-off",
    "GAZ2(A)": "Final Gazette notice: dissolved via voluntary strike-off",
    "PSC01": "Notification of a person with significant control (individual)",
    "PSC02": "Notification of a person with significant control (legal entity)",
    "PSC04": "Change of details of a person with significant control",
    "PSC07": "Cessation of a person with significant control",
    "LIQ01": "Declaration of solvency",
    "AM01": "Appointment of an administrator",
    "COCOMP": "Order of court to wind up",
    "RT01": "Application for administrative restoration to the register",
    "RESOLUTIONS": "Resolutions",
}


def describe_filing(code: str | None, slug: str | None) -> str:
    """Plain-English description for a filing."""
    if code and code in FILING_CODES:
        return FILING_CODES[code]
    if slug:
        return slug.replace("-", " ").replace("_", " ").strip().capitalize()
    return code or "Unknown filing"


def is_address_change(code: str | None) -> bool:
    return bool(code) and code in ADDRESS_CHANGE_CODES
