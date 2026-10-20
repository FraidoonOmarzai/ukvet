import pytest
from agent_helpers import NOW, fail, ok, scripted_company
from ukvet_agent.errors import CompanyNotFoundError
from ukvet_agent.mcp_client import ToolOutcome
from ukvet_agent.nodes.researcher import research_node
from ukvet_agent.nodes.verifier import check_consistency, verify_node
from ukvet_agent.schemas import ALL_QUESTIONS
from ukvet_agent.settings import AgentSettings

TODAY = NOW.date()


def settings(**kw: int) -> AgentSettings:
    return AgentSettings(_env_file=None, **kw)  # type: ignore[call-arg]


def state(**extra: object) -> dict[str, object]:
    return {"company_number": "12345678", "plan": ALL_QUESTIONS, **extra}


async def test_stage_one_and_two_calls_and_arguments() -> None:
    tools = scripted_company()
    out = await research_node(state(), tools, settings(), TODAY)
    called = dict(tools.calls)
    assert {c[0] for c in tools.calls} == {
        "get_company_profile",
        "get_officers",
        "get_persons_with_significant_control",
        "get_charges",
        "get_insolvency",
        "get_filing_history",
        "get_officer_appointments",
    }
    assert called["get_officers"]["include_resigned"] is True
    assert called["get_filing_history"]["since"] == "2025-03-04"
    assert called["get_officer_appointments"] == {
        "officer_id": "ID1",
        "exclude_company_number": "12345678",
        "max_items": 50,
    }
    assert set(out["raw"]) == {
        "profile", "officers", "psc", "charges", "insolvency", "filings", "appointments.1",
    }  # fmt: skip
    assert out["retry_keys"] == []


async def test_plan_subset_only_calls_needed_tools() -> None:
    tools = scripted_company()
    await research_node(state(plan=["Q1", "Q2"]), tools, settings(), TODAY)
    assert [c[0] for c in tools.calls] == ["get_company_profile"]


async def test_unknown_company_raises_not_found() -> None:
    tools = scripted_company(get_company_profile=fail("Company 1 was not found."))
    with pytest.raises(CompanyNotFoundError):
        await research_node(state(), tools, settings(), TODAY)


async def test_other_failures_do_not_raise() -> None:
    tools = scripted_company(get_charges=fail("down", retryable=True))
    out = await research_node(state(), tools, settings(), TODAY)
    assert not out["raw"]["charges"].ok


async def test_director_cap_limits_appointment_lookups() -> None:
    directors = [
        {"name": f"D{i}", "officer_id": f"ID{i}", "role": "director", "is_active": True}
        for i in range(8)
    ]
    tools = scripted_company(get_officers=ok({"items": directors}))
    out = await research_node(state(), tools, settings(max_directors=3), TODAY)
    assert sorted(k for k in out["raw"] if k.startswith("appointments.")) == [
        "appointments.1", "appointments.2", "appointments.3",
    ]  # fmt: skip


async def test_missing_officer_id_fails_without_calling_tool() -> None:
    director = {"name": "D", "officer_id": None, "role": "director", "is_active": True}
    tools = scripted_company(get_officers=ok({"items": [director]}))
    out = await research_node(state(), tools, settings(), TODAY)
    assert not out["raw"]["appointments.1"].ok
    assert "get_officer_appointments" not in [c[0] for c in tools.calls]


async def test_retry_refetches_only_requested_keys() -> None:
    tools = scripted_company()
    first = await research_node(state(), tools, settings(), TODAY)
    tools.calls.clear()
    out = await research_node(state(raw=first["raw"], retry_keys=["psc"]), tools, settings(), TODAY)
    assert [c[0] for c in tools.calls] == ["get_persons_with_significant_control"]
    assert out["raw"]["profile"] is first["raw"]["profile"]


async def test_retry_of_officers_triggers_missing_appointment_lookups() -> None:
    tools = scripted_company(get_officers=[fail("down", True), ok({"items": [
        {"name": "D", "officer_id": "ID1", "role": "director", "is_active": True}
    ]})])  # fmt: skip
    first = await research_node(state(), tools, settings(), TODAY)
    assert "appointments.1" not in first["raw"]
    out = await research_node(
        state(raw=first["raw"], retry_keys=["officers"]), tools, settings(), TODAY
    )
    assert out["raw"]["appointments.1"].ok


async def full_raw(**overrides: ToolOutcome | list[ToolOutcome]) -> dict[str, object]:
    out = await research_node(state(), scripted_company(**overrides), settings(), TODAY)
    return {"plan": ALL_QUESTIONS, **out}


async def test_verifier_builds_facts_and_requests_no_retry_when_clean() -> None:
    update = verify_node(await full_raw(), settings(), TODAY)
    assert update["gaps"] == [] and update["retry_keys"] == [] and update["loops"] == 0
    assert len(update["facts"]) >= 10


async def test_verifier_retries_only_retryable_gaps() -> None:
    raw = await full_raw(
        get_charges=fail("Companies House is not responding", True),
        get_insolvency=fail("some permanent problem", False),
    )
    update = verify_node(raw, settings(), TODAY)
    assert update["retry_keys"] == ["charges"]
    assert update["loops"] == 1


async def test_verifier_stops_after_max_loops() -> None:
    raw = await full_raw(get_charges=fail("not responding", True))
    raw["loops"] = 2
    update = verify_node(raw, settings(max_verifier_loops=2), TODAY)
    assert update["retry_keys"] == [] and update["loops"] == 2
    assert [g.tool for g in update["gaps"]] == ["charges"]


async def test_verifier_with_zero_loops_never_retries() -> None:
    raw = await full_raw(get_charges=fail("not responding", True))
    assert verify_node(raw, settings(max_verifier_loops=0), TODAY)["retry_keys"] == []


def test_consistency_checks() -> None:
    def raw(profile: dict[str, object], **o: ToolOutcome) -> dict[str, ToolOutcome]:
        return {"profile": ok(profile), **o}

    none_found = ok({}, found=False)
    assert check_consistency({}) == []
    assert check_consistency(raw({"has_charges": True}, charges=none_found))
    assert check_consistency(raw({"has_charges": False}, charges=ok({"items": [1]})))
    assert check_consistency(raw({"has_insolvency_history": True}, insolvency=none_found))
    notes = check_consistency(raw({"status": "liquidation"}, insolvency=none_found))
    assert "liquidation" in notes[0]
    assert check_consistency(raw({"has_charges": True}, charges=ok({"items": [1]}))) == []
