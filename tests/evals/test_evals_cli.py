import json
import logging
from pathlib import Path

import pytest
from evals_helpers import make_root
from ukvet_evals.cli import main
from ukvet_evals.demo import build_demo


@pytest.fixture
def root(tmp_path: Path) -> Path:
    r = make_root(tmp_path)
    build_demo(r)
    return r


def cli(root: Path, *args: str) -> int:
    return main(["--root", str(root), *args])


def test_validate_run_gate_roundtrip(root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli(root, "validate", "--dataset", "demo") == 0
    assert cli(root, "gate", "--dataset", "demo") == 1  # no baseline yet
    assert cli(root, "gate", "--dataset", "demo", "--update-baseline") == 0
    baseline = json.loads((root / "evals" / "baselines" / "demo.json").read_text())
    assert "created_at" not in baseline["meta"] and "perf" not in baseline
    capsys.readouterr()
    assert cli(root, "gate", "--dataset", "demo", "--markdown", str(root / "pr.md")) == 0
    assert "ukvet eval gate: PASS" in (root / "pr.md").read_text()


def test_gate_fails_when_the_data_regresses(root: Path) -> None:
    assert cli(root, "gate", "--dataset", "demo", "--update-baseline") == 0
    path = root / "evals" / "baselines" / "demo.json"
    data = json.loads(path.read_text())
    data["m1"]["overall"]["fields"] = {"k": 1, "n": 1, "rate": 1.0}
    data["m1"]["failures"] = []
    # simulate "now" being worse by writing a worse results file
    worse = json.loads(path.read_text())
    worse["m1"]["overall"]["fields"]["rate"] = 0.5
    results = root / "worse.json"
    results.write_text(json.dumps(worse))
    assert cli(root, "gate", "--dataset", "demo", "--results", str(results)) == 1


def test_run_writes_results_and_restores_logging(root: Path) -> None:
    before = logging.root.manager.disable
    assert cli(root, "run", "--dataset", "demo", "--split", "dev") == 0
    assert logging.root.manager.disable == before  # the CLI must not leave logging switched off
    out = root / "evals" / "results" / "demo-dev"
    assert json.loads((out / "results.json").read_text())["meta"]["split"] == "dev"
    assert "Synthetic demo data" in (out / "results.md").read_text()


def test_test_split_needs_a_reason_and_is_logged(root: Path) -> None:
    with pytest.raises(SystemExit):
        cli(root, "run", "--dataset", "demo", "--split", "test")
    assert (
        cli(
            root,
            "run",
            "--dataset",
            "demo",
            "--split",
            "test",
            "--confirm-test-split",
            "milestone check",
        )
        == 0
    )
    log = (root / "evals" / "results" / "TEST_SPLIT_LOG.md").read_text()
    assert "milestone check" in log and "demo" in log


def test_run_reports_stale_items_with_exit_code_2(root: Path) -> None:
    items = root / "evals" / "datasets" / "demo" / "items.jsonl"
    items.write_text(items.read_text().replace('"Q1.status": "active"', '"Q1.status": "closed"', 1))
    assert cli(root, "run", "--dataset", "demo") == 2
    assert cli(root, "build-items", "--dataset", "demo") == 0  # regenerate from the oracle
    assert cli(root, "run", "--dataset", "demo") == 0


def test_build_items_refuses_when_golden_disagrees(root: Path) -> None:
    g = root / "evals" / "datasets" / "demo" / "golden.jsonl"
    g.write_text(g.read_text().replace('"Q1.status": "active"', '"Q1.status": "dissolved"'))
    assert cli(root, "build-items", "--dataset", "demo") == 1


def test_authoring_commands(root: Path) -> None:
    assert cli(root, "gen-abstention", "--dataset", "demo") == 0
    assert cli(root, "label-template", "--dataset", "demo") == 0
    assert cli(root, "seed-injection", "--dataset", "demo") == 0  # already seeded: no-op
    assert cli(root, "demo-build") == 0


def test_splits_can_be_locked_and_then_not_changed(tmp_path: Path) -> None:
    r = make_root(tmp_path)
    build_demo(r)
    manifest = r / "evals" / "datasets" / "demo" / "dataset.json"
    unlocked = json.loads(manifest.read_text()) | {"splits_locked": False}
    manifest.write_text(json.dumps(unlocked))
    assert cli(r, "choose-salt", "--dataset", "demo") == 0
    assert cli(r, "set-splits", "--dataset", "demo", "--lock") == 0
    assert json.loads(manifest.read_text())["splits_locked"] is True
    assert cli(r, "choose-salt", "--dataset", "demo") == 1
    assert cli(r, "set-splits", "--dataset", "demo") == 1


def test_report_and_judge_agreement_commands(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli(root, "run", "--dataset", "demo", "--split", "dev") == 0
    results = root / "evals" / "results" / "demo-dev" / "results.json"
    assert cli(root, "report", "--results", str(results)) == 0
    data = json.loads(results.read_text())
    data["judge_rows"] = [{"key": "c001:0", "supported": True, "reason": ""}]
    results.write_text(json.dumps(data))
    hand = root / "hand.jsonl"
    hand.write_text(json.dumps({"key": "c001:0", "supported": True}) + "\n")
    capsys.readouterr()
    assert cli(root, "judge-agreement", "--results", str(results), "--hand", str(hand)) == 0
    assert '"n": 1' in capsys.readouterr().out
