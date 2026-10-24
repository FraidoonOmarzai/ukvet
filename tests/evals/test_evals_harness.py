"""End-to-end: replay the demo dataset through the REAL MCP server and agent graph."""

from pathlib import Path

import pytest
from evals_helpers import REPO
from ukvet_evals.gate import compare
from ukvet_evals.run import RunOptions, evaluate

ROOT = REPO


async def run(split: str = "all", **kw: object) -> dict:  # type: ignore[type-arg]
    return await evaluate(RunOptions(root=ROOT, dataset="demo", split=split, **kw))  # type: ignore[arg-type]


async def test_demo_dataset_scores_perfectly_and_reports_everything() -> None:
    res = await run()
    assert res["meta"]["companies"] == 6 and res["meta"]["items"] == 54
    assert res["m1"]["overall"]["fields"]["rate"] == 1.0, res["m1"]["failures"]
    assert res["m3"]["rate"] == 1.0, [c for c in res["m3"]["cases"] if not c["passed"]]
    assert res["m5"]["recall"]["rate"] == 1.0 and res["m5"]["precision"]["rate"] == 1.0
    assert res["m5"]["unlabelled_companies"] == 1  # c006 is deliberately unlabelled
    assert res["narrative"]["m4_mechanical_valid"]["rate"] == 1.0
    assert res["narrative"]["llm_reports"] == 0


async def test_splits_partition_the_companies() -> None:
    dev, test = await run("dev"), await run("test")
    assert dev["meta"]["companies"] + test["meta"]["companies"] == 6
    assert dev["meta"]["companies"] > test["meta"]["companies"] > 0


async def test_a_broken_mapper_is_caught_by_m1_and_blocked_by_the_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The proof that the scorer can fail: corrupt charge statuses and watch Q6 drop."""
    baseline = await run("dev")
    import ukvet_mcp.service as service
    from ukvet_mcp.mappers import map_charge

    def broken(item: dict) -> object:  # type: ignore[type-arg]
        return map_charge({**item, "status": "satisfied"})  # every charge looks satisfied

    monkeypatch.setattr(service, "map_charge", broken)
    now = await run("dev")
    assert now["m1"]["by_question"]["Q6"]["fields"]["rate"] < 1.0
    assert any(f["field"] == "Q6.outstanding" for f in now["m1"]["failures"])
    gate = compare(baseline, now)
    assert not gate.passed and any("Q6.outstanding" in p for p in gate.problems)


async def test_a_broken_rule_is_caught_by_m5(monkeypatch: pytest.MonkeyPatch) -> None:
    import ukvet_agent.nodes.reporter as reporter

    monkeypatch.setattr(reporter, "evaluate_red_flags", lambda facts: [])
    res = await run("all")
    assert res["m5"]["recall"]["rate"] < 0.5
    assert res["m5"]["missed"]


async def test_a_pipeline_that_ignores_failures_is_caught_by_m3(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the agent swallowed a failed tool and invented 'no data', abstention must fail."""
    import ukvet_agent.nodes.researcher as researcher
    from ukvet_agent.mcp_client import ToolOutcome

    original = researcher._fetch

    async def lying_fetch(*a: object, **k: object) -> dict[str, ToolOutcome]:
        out = await original(*a, **k)  # type: ignore[arg-type]
        return {
            key: (
                ToolOutcome(ok=True, found=False, data={"outstanding_count": 0})
                if not o.ok and key == "charges"
                else o
            )
            for key, o in out.items()
        }

    monkeypatch.setattr(researcher, "_fetch", lying_fetch)
    res = await run("all")
    assert res["m3"]["rate"] < 1.0
    failing = [c for c in res["m3"]["cases"] if not c["passed"]]
    assert any(
        "charges" in " ".join(c["failed_checks"]).lower() or "Q6" in " ".join(c["failed_checks"])
        for c in failing
    )


async def test_stale_items_file_stops_the_run(tmp_path: Path) -> None:
    import shutil

    from ukvet_evals.run import DatasetDriftError

    root = tmp_path
    shutil.copytree(REPO / "evals" / "datasets" / "demo", root / "evals" / "datasets" / "demo")
    shutil.copytree(REPO / "evals" / "snapshots" / "demo", root / "evals" / "snapshots" / "demo")
    items = root / "evals" / "datasets" / "demo" / "items.jsonl"
    items.write_text(items.read_text().replace('"Q1.status": "active"', '"Q1.status": "closed"', 1))
    with pytest.raises(DatasetDriftError):
        await evaluate(RunOptions(root=root, dataset="demo"))


async def test_replay_with_missing_recording_fails_loudly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ukvet_evals.run import ReplayMissError

    monkeypatch.setenv("LLM_MODEL", "some-model")
    with pytest.raises(ReplayMissError):
        await evaluate(
            RunOptions(root=_tmp_root_with_empty_cache(tmp_path), dataset="demo", llm="replay")
        )


def _tmp_root_with_empty_cache(tmp_path: Path) -> Path:
    import shutil

    shutil.copytree(REPO / "evals" / "datasets" / "demo", tmp_path / "evals" / "datasets" / "demo")
    shutil.copytree(
        REPO / "evals" / "snapshots" / "demo", tmp_path / "evals" / "snapshots" / "demo"
    )
    return tmp_path


async def test_llm_replay_scores_recorded_answers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Record with a fake writer, then replay offline and score M2/M4 on the LLM text."""
    import ukvet_evals.run as run_module
    from ukvet_agent.llm import NarrativeDraft
    from ukvet_agent.schemas import Claim

    class Smart:
        model_name = "fake-1"

        async def write(self, system: str, user: str) -> NarrativeDraft:
            return NarrativeDraft(
                headline=Claim(text="The company status is recorded.", fact_ids=["Q1.status"]),
                findings=[
                    Claim(text="Director Zed Zebra resigned.", fact_ids=["Q1.status"])
                ],  # invented name
            )

    root = _tmp_root_with_empty_cache(tmp_path)
    monkeypatch.setenv("LLM_MODEL", "fake-1")
    monkeypatch.setattr(run_module, "build_writer", lambda settings: Smart())
    recorded = await evaluate(RunOptions(root=root, dataset="demo", llm="record", split="dev"))
    assert recorded["narrative"]["llm_reports"] > 0
    # production's checker accepts the invented name (no date/number); the independent one does not
    assert recorded["narrative"]["m2_unsupported"]["k"] > 0
    assert recorded["narrative"]["m4_mechanical_valid"]["rate"] < 1.0
    replayed = await evaluate(RunOptions(root=root, dataset="demo", llm="replay", split="dev"))
    assert replayed["narrative"]["m2_unsupported"] == recorded["narrative"]["m2_unsupported"]
    assert replayed["meta"]["llm"]["live_calls"] == 0
