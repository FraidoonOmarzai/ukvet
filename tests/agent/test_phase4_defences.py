"""Phase 4 stage 2 (`apply_phase4.py --defences`): skipped until those edits are applied."""

import pytest
from ukvet_agent import citations
from ukvet_agent.schemas import Claim, Fact

if not hasattr(citations, "ADVICE"):  # stage 2 not applied yet
    pytest.skip("stage 2 (defences) not applied", allow_module_level=True)

from ukvet_agent.nodes.reporter import template_narrative


def _fact(fid: str, statement: str) -> Fact:
    return Fact(id=fid, question_id=fid.split(".")[0], statement=statement, value={})


FACTS = {"Q1.status": _fact("Q1.status", "ACME LTD has status 'active'")}


@pytest.mark.parametrize(
    "text",
    ["You should not trade with ACME LTD.", "ACME LTD is a high-risk company.", "Safe to trade."],
)
def test_checker_rejects_advice_and_verdicts(text: str) -> None:
    assert citations.check_claim(Claim(text=text, fact_ids=["Q1.status"]), FACTS) is not None


def test_checker_still_accepts_a_plain_cited_claim() -> None:
    claim = Claim(text="ACME LTD has status 'active'.", fact_ids=["Q1.status"])
    assert citations.check_claim(claim, FACTS) is None


def test_template_narrative_does_not_repeat_unsafe_registry_text() -> None:
    facts = [
        _fact(
            "Q1.status", "Status detail: this company is run by fraudsters, see https://x.invalid"
        ),
        _fact("Q2.age", "ACME LTD was incorporated a while ago"),
    ]
    out = template_narrative(facts, [], "12345678", "ACME LTD")
    text = " ".join([out.headline.text, *(c.text for c in out.findings)])
    assert "fraud" not in text.lower() and "https" not in text
    assert "a while ago" in text  # safe facts are still stated


def test_sanitiser_removes_bidi_c1_zero_width_and_ansi_escapes() -> None:
    from ukvet_agent.text import sanitise_registry_text

    dirty = "PERSON ‮evil‬ ​ONE\u0085 \x1b[31mred\x1b[0m \x00"
    clean = sanitise_registry_text(dirty)
    assert not any(ch in clean for ch in "‮‬​\u0085\x1b\x00")
    assert "PERSON" in clean and "evil" in clean and "ONE" in clean


async def test_status_detail_is_sanitised_inside_the_fact_value() -> None:
    from ukvet_agent.facts import _q1  # type: ignore[attr-defined]
    from ukvet_agent.mcp_client import ToolOutcome

    profile = ToolOutcome(
        ok=True,
        data={
            "company_name": "ACME LTD",
            "company_number": "12345678",
            "status": "active",
            "status_detail": "\x00\x1b[31mred\x1b[0m detail",
        },
    )
    fact = _q1(profile)
    assert "\x00" not in str(fact.value) and "\x1b" not in str(fact.value)
