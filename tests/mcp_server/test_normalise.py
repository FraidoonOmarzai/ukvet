import pytest
from ukvet_mcp.errors import InvalidInput
from ukvet_mcp.filing_codes import describe_filing, is_address_change
from ukvet_mcp.normalise import (
    normalise_company_number,
    officer_id_from_link,
    validate_category,
    validate_officer_id,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("00445790", "00445790"),
        ("445790", "00445790"),
        ("1234", "00001234"),
        ("  00445790  ", "00445790"),
        ("sc123456", "SC123456"),
        ("SC12345", "SC012345"),  # numeric part padded, prefix kept
        ("NI 012345", "NI012345"),
        ("R0000001", "R0000001"),
        ("oc301234", "OC301234"),
    ],
)
def test_valid_company_numbers(raw: str, expected: str) -> None:
    assert normalise_company_number(raw) == expected


@pytest.mark.parametrize(
    "raw", ["", "   ", "abc", "123456789", "SCX12345", "12-345", "ABC12345", "1234567A", "tesco"]
)
def test_invalid_company_numbers(raw: str) -> None:
    with pytest.raises(InvalidInput) as err:
        normalise_company_number(raw)
    assert "search_company" in str(err.value)


def test_non_string_company_number() -> None:
    with pytest.raises(InvalidInput):
        normalise_company_number(12345678)  # type: ignore[arg-type]


def test_officer_id_from_link() -> None:
    assert officer_id_from_link("/officers/AbC123_x-y/appointments") == "AbC123_x-y"
    assert officer_id_from_link("/officers/AbC123/appointments/") == "AbC123"
    assert officer_id_from_link(None) is None
    assert officer_id_from_link("/company/123/officers") is None


@pytest.mark.parametrize("bad", ["", "ab", "has space", "../etc/passwd", "a" * 65, "x/y/z12345"])
def test_invalid_officer_ids(bad: str) -> None:
    with pytest.raises(InvalidInput):
        validate_officer_id(bad)


def test_valid_officer_id() -> None:
    assert validate_officer_id(" OFFICERIDA1 ") == "OFFICERIDA1"


def test_category_validation() -> None:
    assert validate_category(None) is None
    assert validate_category("") is None
    assert validate_category(" Address ") == "address"
    assert validate_category("officers,accounts") == "officers,accounts"
    with pytest.raises(InvalidInput):
        validate_category("address; drop table")


def test_filing_code_mapping_and_fallbacks() -> None:
    assert describe_filing("AD01", "whatever") == "Registered office address changed"
    assert describe_filing("ZZ99", "some-new-filing-type") == "Some new filing type"
    assert describe_filing("ZZ99", None) == "ZZ99"
    assert describe_filing(None, None) == "Unknown filing"
    assert is_address_change("AD01") is True
    assert is_address_change("CS01") is False
    assert is_address_change(None) is False
