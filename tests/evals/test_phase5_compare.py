"""Phase 5: the model-comparison table, its fairness checks and the self-hosted cost."""

import copy
import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest
from evals_helpers import REPO
from ukvet_agent.llm import NarrativeDraft
from ukvet_agent.schemas import Claim
from ukvet_evals import cli, compare, perf
from ukvet_evals.compare import ComparisonError


def rate(k: int, n: int) -> dict[str, Any]:
    return {"k": k, "n": n, "rate": round(k / n, 4) if n else None, "ci95": [0.5, 1.0]}


def results(model: str, *, llm_reports: int = 10, reports: int = 10, **meta: Any) -> dict[str, Any]:
    return {
        "meta": {
            "dataset": "v0.1",
            "dataset_version": "v0.1",
            "split": "test",
            "git_commit": "abc1234",
            "created_at": "2026-11-04T10:00:00+00:00",
            "companies": 10,
            "llm": {"mode": "replay", "model": model},
            **meta,
        },
        "m1": {
            "overall": {"fields": rate(90, 100), "items": rate(9, 10)},
            "by_question": {
                f"Q{i}": {"fields": rate(9, 10), "items": rate(9, 10)} for i in range(1, 10)
            },
        },
        "narrative": {
            "reports": reports,
            "llm_reports": llm_reports,
            "llm_errors": reports - llm_reports,
            "retries": 1,
            "claims": 50,
            "m2_unsupported": rate(0, 50),
            "m4_mechanical_valid": rate(50, 50),
        },
        "guardrails": {"reports": reports, "violations": 0},
        "m3": {"rate": 1.0},
        "m5": {"recall": {"rate": 0.9}},
    }


def live(
    n: int = 25, *, p95: float = 12_000.0, busy: float = 250_000.0, cost: float | None = 0.01
) -> dict[str, Any]:
    return {
        "reports": n,
        "busy_ms_total": busy,
        "m7_latency_ms": {
            "p50": 8000.0,
            "p95": p95,
            "worst": 20000.0,
            "weak": n < 20,
            "met": p95 < 30000,
        },
        "m8_cost_gbp": {"mean": cost, "max": cost, "met": None if cost is None else cost < 0.05},
        "m9_tool_calls": {"mean": 7.0, "median": 7, "max": 9},
        "llm_reports": n,
    }


def injection(rate_: float = 1.0, reached: int = 20) -> dict[str, Any]:
    return {
        "m6": rate(round(rate_ * reached), reached),
        "reached_prompt": reached,
        "runs": reached + 2,
    }


def write(tmp: Path, name: str, data: dict[str, Any]) -> str:
    p = tmp / name
    p.write_text(json.dumps(data), encoding="utf-8")
    return name


def manifest(tmp: Path, a: dict[str, Any], b: dict[str, Any], **open_extra: Any) -> Path:
    api = {
        "label": "API",
        "kind": "api",
        "model_id": "api-1",
        "results": write(tmp, "ra.json", a["results"]),
        "live": write(tmp, "la.json", a["live"]),
        "injection": write(tmp, "ia.json", a["injection"]),
    }
    open_ = {
        "label": "Open",
        "kind": "self-hosted",
        "model_id": "open-1",
        "hardware": "1x GPU",
        "gpu_gbp_per_hour": 1.2,
        "gpu_hours": 1.0,
        "results": write(tmp, "rb.json", b["results"]),
        "live": write(tmp, "lb.json", b["live"]),
        "injection": write(tmp, "ib.json", b["injection"]),
        **open_extra,
    }
    path = tmp / "m.json"
    path.write_text(json.dumps({"title": "T", "models": [api, open_]}), encoding="utf-8")
    return path


def bundle(model: str, **kw: Any) -> dict[str, Any]:
    return {"results": results(model, **kw), "live": live(), "injection": injection()}


# ---- cost ------------------------------------------------------------------------------------


def test_selfhost_cost_is_price_times_hours_over_reports() -> None:
    c = compare.selfhost_cost(1.5, 2.0, 30, busy_ms=1_800_000)
    assert c["gbp_per_report"] == pytest.approx(0.1)
    assert c["total_gbp"] == pytest.approx(3.0)
    assert c["utilisation"] == pytest.approx(0.25)  # 0.5 h busy of 2 h


def test_selfhost_cost_rejects_nonsense() -> None:
    for args in [(1.0, 0.0, 10), (1.0, 1.0, 0), (-1.0, 1.0, 10)]:
        with pytest.raises(ComparisonError):
            compare.selfhost_cost(*args, busy_ms=None)


def test_utilisation_is_capped_and_unknown_when_busy_time_missing() -> None:
    assert compare.selfhost_cost(1, 1, 5, busy_ms=10**12)["utilisation"] == 1.0
    assert compare.selfhost_cost(1, 1, 5, busy_ms=None)["utilisation"] is None


# ---- the happy path --------------------------------------------------------------------------


def test_table_has_both_models_and_the_numbers(tmp_path: Path) -> None:
    path = manifest(tmp_path, bundle("api-1"), bundle("open-1"))
    text, data = compare.build(path, tmp_path)
    assert "| API |" in text and "| Open |" in text
    assert "90.0%" in text and "12.0 s" in text and "£0.0100" in text  # API token cost
    assert "£1.2000" not in text  # self-hosted: 1.2 gbp/h * 1 h / 25 reports = 0.048
    assert "£0.0480 (self-hosted" in text
    assert "GPU busy 7% of the time" in text  # 250 s of 3600 s
    assert "Failure analysis" in text and "Recommendation" in text
    assert data["warnings"] == []


def test_every_question_row_is_present(tmp_path: Path) -> None:
    text, _ = compare.build(manifest(tmp_path, bundle("api-1"), bundle("open-1")), tmp_path)
    for q in compare.QUESTIONS:
        assert f"| {q} |" in text


# ---- refusals and warnings -------------------------------------------------------------------


def test_different_dataset_versions_are_refused(tmp_path: Path) -> None:
    b = bundle("open-1")
    b["results"]["meta"]["dataset_version"] = "v0.2"
    with pytest.raises(ComparisonError, match="different datasets"):
        compare.build(manifest(tmp_path, bundle("api-1"), b), tmp_path)


def test_different_splits_are_refused(tmp_path: Path) -> None:
    b = bundle("open-1")
    b["results"]["meta"]["split"] = "dev"
    with pytest.raises(ComparisonError, match="different splits"):
        compare.build(manifest(tmp_path, bundle("api-1"), b), tmp_path)


def test_a_template_run_is_not_a_model(tmp_path: Path) -> None:
    b = bundle("open-1")
    b["results"]["meta"]["llm"] = {"mode": "none", "model": None}
    with pytest.raises(ComparisonError, match="template"):
        compare.build(manifest(tmp_path, bundle("api-1"), b), tmp_path)


def test_a_wrong_model_label_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ComparisonError, match="used 'something-else'"):
        compare.build(manifest(tmp_path, bundle("api-1"), bundle("something-else")), tmp_path)


def test_one_model_is_not_a_comparison() -> None:
    errors, _ = compare.check([{}])
    assert errors == ["a comparison needs at least two models"]


def test_missing_file_gives_a_clear_error(tmp_path: Path) -> None:
    path = manifest(tmp_path, bundle("api-1"), bundle("open-1"))
    (tmp_path / "lb.json").unlink()
    with pytest.raises(ComparisonError, match="live metrics file not found"):
        compare.build(path, tmp_path)


def test_selfhosted_without_gpu_price_is_refused(tmp_path: Path) -> None:
    path = manifest(tmp_path, bundle("api-1"), bundle("open-1"), gpu_gbp_per_hour=None)
    with pytest.raises(ComparisonError, match="gpu_gbp_per_hour"):
        compare.build(path, tmp_path)


def test_warnings_are_printed_above_the_table(tmp_path: Path) -> None:
    weak = bundle("open-1", llm_reports=5, reports=10)  # 50% template fallback
    weak["results"]["meta"]["git_commit"] = "def5678"
    weak["results"]["meta"]["split"] = "test"
    weak["live"] = live(n=8)
    weak["injection"] = injection(reached=0)
    text, data = compare.build(manifest(tmp_path, bundle("api-1"), weak), tmp_path)
    joined = " ".join(data["warnings"])
    assert "different git commits" in joined
    assert "fell back to the template" in joined
    assert "only 8 live reports" in joined
    assert "no injection payload reached the prompt" in joined
    assert text.index("Read these before the table") < text.index("## Results")


def test_non_test_split_is_flagged_as_development_numbers(tmp_path: Path) -> None:
    a, b = bundle("api-1"), bundle("open-1")
    a["results"]["meta"]["split"] = b["results"]["meta"]["split"] = "dev"
    _, data = compare.build(manifest(tmp_path, a, b), tmp_path)
    assert any("development numbers" in w for w in data["warnings"])


def test_missing_optional_inputs_show_as_na(tmp_path: Path) -> None:
    path = manifest(tmp_path, bundle("api-1"), bundle("open-1"))
    raw = json.loads(path.read_text())
    for m in raw["models"]:
        m.pop("live"), m.pop("injection")
    path.write_text(json.dumps(raw))
    text, data = compare.build(path, tmp_path)
    assert "n/a" in text
    assert any("no live latency/cost run" in w for w in data["warnings"])


def test_bad_kind_is_rejected(tmp_path: Path) -> None:
    path = manifest(tmp_path, bundle("api-1"), bundle("open-1"))
    raw = json.loads(path.read_text())
    raw["models"][0]["kind"] = "magic"
    path.write_text(json.dumps(raw))
    with pytest.raises(ComparisonError, match="kind must be"):
        compare.build(path, tmp_path)


# ---- CLI -------------------------------------------------------------------------------------


def test_cli_init_then_compare_writes_markdown_and_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["--root", str(tmp_path), "compare", "--init"]) == 0
    assert (tmp_path / "evals" / "comparison.json").exists()
    assert cli.main(["--root", str(tmp_path), "compare", "--init"]) == 2  # never overwrites
    assert cli.main(["--root", str(tmp_path), "compare"]) == 2  # files in the example do not exist
    assert "REFUSED" in capsys.readouterr().err

    manifest(tmp_path, bundle("api-1"), bundle("open-1"))
    assert cli.main(["--root", str(tmp_path), "compare", "--manifest", "m.json"]) == 0
    assert (tmp_path / "docs" / "results.md").exists()
    assert (
        json.loads((tmp_path / "docs" / "results.json").read_text())["models"][0]["label"] == "API"
    )


def test_cli_without_a_manifest_says_what_to_do(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["--root", str(tmp_path), "compare"]) == 2
    assert "--init" in capsys.readouterr().err


# ---- perf addition ---------------------------------------------------------------------------


def test_perf_summary_reports_busy_time() -> None:
    from evals_helpers import report

    r = report()
    r.timings_ms = {"total": 4000}
    assert perf.summarise([r, copy.deepcopy(r)])["busy_ms_total"] == 8000


# ---- the endpoint check script ---------------------------------------------------------------


def load_script() -> Any:
    spec = importlib.util.spec_from_file_location(
        "p5check", REPO / "scripts" / "phase5_check_endpoint.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Writer:
    model_name = "m"

    def __init__(self, draft: NarrativeDraft | Exception) -> None:
        self.draft = draft

    async def write(self, system: str, user: str) -> NarrativeDraft:
        if isinstance(self.draft, Exception):
            raise self.draft
        return self.draft


@pytest.mark.parametrize(
    ("draft", "ok", "why"),
    [
        (NarrativeDraft(headline=Claim(text="Active.", fact_ids=["Q1.status"])), True, "ok"),
        (NarrativeDraft(headline=Claim(text="", fact_ids=["Q1.status"])), False, "empty headline"),
        (NarrativeDraft(headline=Claim(text="Active.", fact_ids=[])), False, "no fact ids"),
        (NarrativeDraft(headline=Claim(text="Active.", fact_ids=["Q9.nope"])), False, "not given"),
        (ValueError("bad json"), False, "ValueError"),
    ],
)
async def test_endpoint_round_judges_the_structured_answer(
    monkeypatch: pytest.MonkeyPatch, draft: Any, ok: bool, why: str
) -> None:
    mod = load_script()
    monkeypatch.setattr(mod, "build_writer", lambda s: Writer(draft))
    settings = mod.LlmSettings(
        provider="openai_compatible", model="m", base_url="http://x/v1", _env_file=None
    )
    got_ok, _, reason = await mod.one_round(settings)
    assert got_ok is ok and why in reason
