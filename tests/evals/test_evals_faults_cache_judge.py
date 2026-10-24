import json
from pathlib import Path

import pytest
from evals_helpers import report
from ukvet_agent.llm import NarrativeDraft
from ukvet_agent.mcp_client import ToolOutcome
from ukvet_agent.schemas import Claim
from ukvet_evals.faults import FaultyTools
from ukvet_evals.judge import (
    ClaimVerdict,
    JudgeVerdict,
    agreement,
    judge_report,
    load_hand_labels,
    render_user,
)
from ukvet_evals.llmcache import CacheMiss, CachingWriter, JsonCache, cache_key
from ukvet_evals.schema import FaultSpec


class Inner:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def call(self, name: str, arguments: dict[str, object]) -> ToolOutcome:
        self.calls.append(name)
        return ToolOutcome(ok=True, found=True, data={"who": str(arguments.get("officer_id", ""))})

    async def ping(self) -> int:
        return 8


async def test_permanent_and_timeout_faults_hit_only_the_named_tool() -> None:
    tools = FaultyTools(Inner(), [FaultSpec(tool="get_charges", mode="timeout"),
                                  FaultSpec(tool="get_insolvency", mode="permanent")])  # fmt: skip
    t = await tools.call("get_charges", {})
    assert not t.ok and t.retryable and "timed out" in (t.error or "")
    p = await tools.call("get_insolvency", {})
    assert not p.ok and not p.retryable
    assert (await tools.call("get_officers", {})).ok


async def test_transient_fault_recovers_after_n_calls() -> None:
    tools = FaultyTools(Inner(), [FaultSpec(tool="get_officers", mode="transient", times=2)])
    outcomes = [await tools.call("get_officers", {}) for _ in range(4)]
    assert [o.ok for o in outcomes] == [False, False, True, True]
    assert outcomes[0].retryable


async def test_director_index_targets_the_nth_distinct_officer() -> None:
    tools = FaultyTools(
        Inner(), [FaultSpec(tool="get_officer_appointments", mode="timeout", director_index=2)]
    )
    a = await tools.call("get_officer_appointments", {"officer_id": "AAA"})
    b = await tools.call("get_officer_appointments", {"officer_id": "BBB"})
    again = await tools.call("get_officer_appointments", {"officer_id": "AAA"})
    assert a.ok and not b.ok and again.ok


# ---- LLM cache -------------------------------------------------------------------------------
class Writer:
    model_name = "m"

    def __init__(self) -> None:
        self.n = 0

    async def write(self, system: str, user: str) -> NarrativeDraft:
        self.n += 1
        return NarrativeDraft(headline=Claim(text=f"call {self.n}", fact_ids=["Q1.status"]))


async def test_cache_records_then_replays_without_calling_the_model(tmp_path: Path) -> None:
    inner = Writer()
    rec = CachingWriter(tmp_path, "record", "m", inner)
    first = await rec.write("sys", "user")
    assert inner.n == 1 and rec.live_calls == 1
    rep = CachingWriter(tmp_path, "replay", "m", None)
    assert (await rep.write("sys", "user")).headline.text == first.headline.text
    assert rep.hits == 1 and inner.n == 1


async def test_replay_miss_is_recorded_not_hidden(tmp_path: Path) -> None:
    rep = CachingWriter(tmp_path, "replay", "m", None)
    with pytest.raises(CacheMiss):
        await rep.write("sys", "changed prompt")
    assert len(rep.misses) == 1


def test_cache_key_changes_with_model_or_prompt() -> None:
    assert len({cache_key("a", "s", "u"), cache_key("b", "s", "u"), cache_key("a", "s", "u2")}) == 3


def test_record_mode_needs_a_writer(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        CachingWriter(tmp_path, "record", "m", None)


# ---- judge -----------------------------------------------------------------------------------
class FakeJudge:
    name = "judge-x"

    def __init__(self) -> None:
        self.calls = 0

    async def judge(self, system: str, user: str) -> JudgeVerdict:
        self.calls += 1
        return JudgeVerdict(claims=[ClaimVerdict(index=0, supported=True, reason="ok")])


async def test_judge_is_cached(tmp_path: Path) -> None:
    r = report()
    backend = FakeJudge()
    cache = JsonCache(tmp_path, "judge")
    assert (await judge_report(r, backend, cache))[0].supported
    await judge_report(r, backend, cache)
    assert backend.calls == 1


def test_judge_prompt_lists_facts_and_numbered_claims() -> None:
    text = render_user(report())
    assert "[Q1.status]" in text and "0. ACME LTD is active." in text


def test_agreement_counts_the_costly_error(tmp_path: Path) -> None:
    out = agreement([True, False, False, True], [True, True, False, True])
    assert (
        out["n"] == 4
        and out["agreement"]["k"] == 3
        and out["judge_approved_unsupported_claim"] == 1
    )
    with pytest.raises(ValueError):
        agreement([True], [])
    p = tmp_path / "h.jsonl"
    p.write_text(json.dumps({"key": "c1:0", "supported": False}) + "\n\n")
    assert load_hand_labels(p) == {"c1:0": False}
