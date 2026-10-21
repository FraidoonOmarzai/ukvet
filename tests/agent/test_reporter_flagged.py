from agent_helpers import make_fact
from ukvet_agent.nodes.reporter import template_narrative
from ukvet_agent.schemas import RedFlag


def test_low_flag_evidence_is_shown_even_when_findings_are_capped() -> None:
    facts = [make_fact(f"Q{i}.x", f"fact {i}") for i in range(1, 10)] + [
        make_fact("Q8.network", "network fact")
    ]
    flag = RedFlag(id="network", severity="low", title="t", detail="d", fact_ids=["Q8.network"])
    draft = template_narrative(facts, [flag], "1", "n")
    assert draft.findings[0].fact_ids == ["Q8.network"]
