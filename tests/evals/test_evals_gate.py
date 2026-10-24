import copy
from typing import Any

from ukvet_evals.gate import compare


def rate(k: int, n: int) -> dict[str, Any]:
    return {"k": k, "n": n, "rate": k / n if n else None, "ci95": None}


def results(m1: tuple[int, int] = (100, 100), q6: tuple[int, int] = (10, 10), m3: tuple[int, int] = (20, 20),
            m5: tuple[int, int] = (17, 20), m4: tuple[int, int] = (50, 50), failures: list[dict[str, Any]] | None = None,
            llm: int = 0, m2: tuple[int, int] = (0, 50)) -> dict[str, Any]:  # fmt: skip
    return {
        "meta": {"dataset": "d", "dataset_version": "1", "split": "dev"},
        "m1": {
            "overall": {"fields": rate(*m1), "items": rate(1, 1)},
            "by_question": {"Q1": {"fields": rate(10, 10)}, "Q6": {"fields": rate(*q6)}},
            "failures": failures or [],
        },
        "m3": {**rate(*m3), "cases": [{"id": "abs-1", "passed": True, "failed_checks": []}]},
        "m5": {"recall": rate(*m5), "precision": rate(5, 5)},
        "narrative": {
            "m4_mechanical_valid": rate(*m4),
            "m2_unsupported": rate(*m2),
            "llm_reports": llm,
        },
    }


def test_identical_results_pass() -> None:
    assert compare(results(), results()).passed


def test_overall_drop_over_one_point_fails_but_small_drop_passes() -> None:
    assert compare(results(), results(m1=(99, 100))).passed  # exactly 1 pp: allowed
    g = compare(results(), results(m1=(98, 100)))
    assert not g.passed and "M1 overall fell" in g.problems[0]


def test_category_falling_through_the_floor_fails() -> None:
    g = compare(results(), results(q6=(7, 10)))
    assert any("below the 80% floor" in p for p in g.problems)


def test_category_already_below_floor_only_fails_on_new_failures() -> None:
    base = results(q6=(7, 10))
    assert compare(base, copy.deepcopy(base)).passed


def test_new_field_failure_fails_even_if_percentages_hold() -> None:
    fail = {"item": "c001-Q6", "field": "Q6.total", "expected": 2, "actual": 3}
    g = compare(results(), results(failures=[fail]))
    assert not g.passed and "new field failure c001-Q6" in g.problems[0]


def test_known_failures_do_not_fail_again() -> None:
    fail = {"item": "c001-Q6", "field": "Q6.total", "expected": 2, "actual": 3}
    assert compare(results(failures=[fail]), results(failures=[fail])).passed


def test_abstention_regression_and_m5_drop() -> None:
    now = results(m3=(18, 20), m5=(15, 20))
    now["m3"]["cases"] = [{"id": "abs-1", "passed": False, "failed_checks": ["x"]}]
    g = compare(results(), now)
    text = " ".join(g.problems)
    assert "M3 fell" in text and "abs-1 used to pass" in text and "M5 recall fell" in text


def test_m4_must_stay_100_percent() -> None:
    g = compare(results(), results(m4=(49, 50)))
    assert any("must be 100%" in p for p in g.problems)


def test_m2_only_compared_when_both_have_llm_reports() -> None:
    assert compare(results(), results(llm=3, m2=(5, 50))).passed  # baseline had no LLM reports
    g = compare(results(llm=3, m2=(0, 50)), results(llm=3, m2=(2, 50)))
    assert any("M2 rose" in p for p in g.problems)


def test_dataset_mismatch_fails_with_instructions() -> None:
    other = results()
    other["meta"]["dataset_version"] = "2"
    g = compare(results(), other)
    assert not g.passed and "regenerate the baseline" in g.problems[0]


def test_markdown_has_verdict_and_table() -> None:
    md = compare(results(), results()).markdown()
    assert md.startswith("## ukvet eval gate: PASS") and "| M1 accuracy" in md
