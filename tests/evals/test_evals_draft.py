"""The synthetic v0.1-draft dataset must stay valid and cover every required tag."""

from pathlib import Path

from ukvet_evals.validate import validate

ROOT = Path(__file__).resolve().parents[2]


def test_draft_dataset_is_valid_and_covers_all_tags() -> None:
    rep = validate(ROOT, "v0.1-draft", strict=True)
    assert rep.ok, rep.errors
    assert rep.coverage["tags_missing"] == {}
    assert rep.coverage["companies"] >= 25
    assert rep.coverage["items"] >= 200
