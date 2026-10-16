"""Input normalisation and validation."""

import re

from ukvet_mcp.errors import InvalidInput

_NUMBER_RE = re.compile(r"^([A-Z]{0,2})(\d+)$")
_OFFICER_ID_RE = re.compile(r"^[A-Za-z0-9_-]{5,64}$")
_OFFICER_PATH_RE = re.compile(r"^/officers/([^/]+)/appointments/?$")
_CATEGORY_RE = re.compile(r"^[a-z-]+(,[a-z-]+)*$")


def normalise_company_number(raw: str) -> str:
    """Trim, uppercase and zero-pad a company number to 8 characters.

    `1234` -> `00001234`; `sc12345` -> `SC012345`; `R0000001` stays as is.
    Raises `InvalidInput` with a helpful message otherwise.
    """
    if not isinstance(raw, str):
        raise InvalidInput("company_number must be a string such as '00445790' or 'SC123456'.")
    cleaned = re.sub(r"\s+", "", raw).upper()
    match = _NUMBER_RE.match(cleaned)
    if not cleaned or not match or len(cleaned) > 8:
        raise InvalidInput(
            f"'{raw.strip()[:20]}' is not a valid company number. Company numbers are up to 8 "
            "characters: digits (e.g. 00445790) optionally with a 1-2 letter prefix "
            "(e.g. SC123456, NI012345). If you only have a name, use search_company."
        )
    prefix, digits = match.groups()
    return prefix + digits.zfill(8 - len(prefix))


def validate_officer_id(raw: str) -> str:
    if not isinstance(raw, str) or not _OFFICER_ID_RE.match(raw.strip()):
        raise InvalidInput(
            "officer_id is not valid. Use the officer_id value returned by get_officers; "
            "do not invent or edit it."
        )
    return raw.strip()


def officer_id_from_link(path: str | None) -> str | None:
    """Extract the officer ID from `/officers/{id}/appointments`."""
    if not path:
        return None
    match = _OFFICER_PATH_RE.match(path)
    return match.group(1) if match else None


def validate_category(raw: str | None) -> str | None:
    if raw is None or raw == "":
        return None
    cleaned = raw.strip().lower()
    if not _CATEGORY_RE.match(cleaned):
        raise InvalidInput(
            "category must be lowercase words joined by hyphens, optionally comma-separated, "
            "e.g. 'address' or 'officers,accounts'."
        )
    return cleaned


if __name__ == "__main__":
    print("Testing input validation...\n")

    # 1. Test company number normalisation
    print("1. Company number normalisation")
    for company_value in ["1234", "sc12345", "R0000001", "00445790"]:
        try:
            company_result = normalise_company_number(company_value)
            print(f"  {company_value!r} -> {company_result!r}")
        except InvalidInput as exc:
            print(f"  {company_value!r} -> ERROR: {exc}")

    # 2. Test officer ID validation
    print("\n2. Officer ID validation")
    for officer_value in ["abc123", " ABC123 ", "abc", "abc/123"]:
        try:
            officer_result = validate_officer_id(officer_value)
            print(f"  {officer_value!r} -> {officer_result!r}")
        except InvalidInput as exc:
            print(f"  {officer_value!r} -> ERROR: {exc}")

    # 3. Test officer ID extraction from a link
    print("\n3. Officer ID extraction")
    officer_links: list[str | None] = [
        "/officers/ABC12345/appointments",
        "/officers/ABC12345/appointments/",
        "/invalid/path",
        None,
    ]
    for link_value in officer_links:
        link_result = officer_id_from_link(link_value)
        print(f"  {link_value!r} -> {link_result!r}")

    # 4. Test category validation
    print("\n4. Category validation")
    categories: list[str | None] = [
        "address",
        " Officers,Accounts ",
        "officers, accounts",
        "",
        None,
    ]
    for category_value in categories:
        try:
            category_result = validate_category(category_value)
            print(f"  {category_value!r} -> {category_result!r}")
        except InvalidInput as exc:
            print(f"  {category_value!r} -> ERROR: {exc}")

    print("\nTesting complete.")
