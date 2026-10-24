"""F2 regression: citation stats must describe every attempt, not only the last one."""

from typing import Any

from agent_helpers import NOW, FakeWriter, draft, make_fact, ok
from ukvet_agent.nodes.reporter import report_node
from ukvet_agent.schemas import Report

FACTS = [
    make_fact("Q1.status", "ACME LTD (12345678) has status 'active'", status="active"),
    make_fact("Q2.age", "Incorporated on 4 March 2019; age 7.0 years (2557 days)"),
]
GOOD = draft(
    ("ACME LTD is active.", ["Q1.status"]),
    ("It was incorporated on 4 March 2019.", ["Q2.age"]),
)
BAD = draft(
    ("ACME LTD is active.", ["Q1.status"]),
    ("It was incorporated on 9 September 2012.", ["Q2.age"]),
)


async def run(writer: Any) -> Report:
    state = {
        "company_number": "12345678",
        "company_name": "ACME LTD",
        "facts": FACTS,
        "gaps": [],
        "raw": {"profile": ok({"company_name": "ACME LTD"})},
        "notes": [],
    }
    out = await report_node(state, writer, NOW, 5)
    result = out["result"]
    assert isinstance(result, Report)
    return result


async def test_clean_first_attempt() -> None:
    s = (await run(FakeWriter(GOOD))).citation_stats
    assert [a.outcome for a in s.attempts] == ["ok"]
    assert s.retries == 0 and s.llm_errors == 0


async def test_first_attempt_bad_second_clean_is_not_hidden() -> None:
    r = await run(FakeWriter(BAD, GOOD))
    s = r.citation_stats
    assert r.narrative_source == "llm"
    assert s.retries == 1 and s.llm_errors == 0
    assert [a.outcome for a in s.attempts] == ["violations", "ok"]
    assert s.attempts[0].claims_dropped == 1
    assert "not in the cited facts" in s.attempts[0].violations[0]
    assert s.claims_dropped == 0  # the LAST attempt was clean


async def test_llm_error_is_counted_separately_from_checker_violations() -> None:
    r = await run(FakeWriter(RuntimeError("boom"), GOOD))
    s = r.citation_stats
    assert s.retries == 1 and s.llm_errors == 1
    assert [a.outcome for a in s.attempts] == ["llm_error", "ok"]
    assert s.attempts[0].error == "RuntimeError"
    assert all(a.claims_dropped == 0 for a in s.attempts)


async def test_both_attempts_fail_falls_back_to_template() -> None:
    r = await run(FakeWriter(RuntimeError("a"), RuntimeError("b")))
    assert r.narrative_source == "template"
    assert r.citation_stats.llm_errors == 2
    assert len(r.citation_stats.attempts) == 2
