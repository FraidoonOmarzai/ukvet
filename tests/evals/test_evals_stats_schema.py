import pytest
from pydantic import ValidationError
from ukvet_evals.schema import (
    AbstentionCase,
    CompanyEntry,
    ExpectedFlag,
    FaultSpec,
    choose_salt,
    split_for,
)
from ukvet_evals.stats import Rate, cohens_kappa, wilson


def test_wilson_known_values() -> None:
    lo, hi = wilson(50, 100) or (0, 0)
    assert 0.40 < lo < 0.41 and 0.59 < hi < 0.60
    assert wilson(0, 0) is None
    lo, hi = wilson(10, 10) or (0, 0)
    assert abs(hi - 1.0) < 1e-9 and 0.70 < lo < 0.73  # perfect score on 10 items is still wide


def test_wilson_rejects_bad_counts() -> None:
    with pytest.raises(ValueError):
        wilson(5, 3)


def test_rate_formatting() -> None:
    r = Rate(9, 10)
    assert r.pct() == "90.0%" and "[" in r.pct_ci()
    assert Rate(0, 0).pct() == "n/a" and Rate(0, 0).to_dict()["rate"] is None


def test_kappa() -> None:
    assert cohens_kappa(["y", "n", "y", "n"], ["y", "n", "y", "n"]) == 1.0
    k = cohens_kappa(["y", "y", "n", "n"], ["y", "n", "y", "n"])
    assert k is not None and abs(k) < 1e-9  # chance-level agreement
    assert cohens_kappa([], []) is None
    assert cohens_kappa(["y", "y"], ["y", "y"]) is None  # no variation: undefined
    with pytest.raises(ValueError):
        cohens_kappa(["y"], [])


def test_split_is_stable_and_salted() -> None:
    assert split_for("c001", "s0") == split_for("c001", "s0")
    assert {split_for(f"c{i:03d}", "a") for i in range(50)} == {"dev", "test"}
    different = [split_for(f"c{i:03d}", "a") != split_for(f"c{i:03d}", "b") for i in range(60)]
    assert any(different)  # salt really changes assignments


def test_choose_salt_balances_a_small_dataset() -> None:
    ids = [f"c{i:03d}" for i in range(1, 29)]
    salt = choose_salt(ids)
    dev = sum(split_for(i, salt) == "dev" for i in ids)
    assert abs(dev - 28 * 0.6) < 1  # 17 of 28 (16.8 is the target)


def test_models_forbid_unknown_fields_and_validate_ids() -> None:
    with pytest.raises(ValidationError):
        CompanyEntry(id="x1", company_number="1", as_of="2026-01-01", split="dev")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        CompanyEntry(id="c001", company_number="1", as_of="2026-01-01", split="dev", typo=1)  # type: ignore[call-arg, arg-type]
    with pytest.raises(ValidationError):
        ExpectedFlag(id="not_a_flag")
    with pytest.raises(ValidationError):
        AbstentionCase(
            id="a", company="c001", faults=[FaultSpec(tool="get_charges", mode="timeout")],
            expected_gap_questions=["Q99"],
        )  # fmt: skip
