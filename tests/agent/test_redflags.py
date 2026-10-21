from typing import Any

from ukvet_agent.redflags import assessment_text, evaluate_red_flags, risk_level
from ukvet_agent.schemas import Fact, Gap


def mk(fact_id: str, **value: Any) -> Fact:
    return Fact(id=fact_id, question_id=fact_id.split(".")[0], statement="x", value=value)


def flags_of(*facts: Fact) -> dict[str, str]:
    return {f.id: f.severity for f in evaluate_red_flags(list(facts))}


ACTIVE = mk("Q1.status", status="active")


def test_healthy_company_has_no_flags() -> None:
    facts = [
        ACTIVE,
        mk("Q2.age", age_days=4000),
        mk("Q4.accounts", overdue=False),
        mk("Q4.confirmation_statement", overdue=False),
        mk("Q3.officers_current", directors=[{"name": "A"}]),
        mk("Q5.control", current_total=1),
        mk("Q6.charges", outstanding=0),
        mk("Q7.insolvency", case_count=0),
    ]
    assert evaluate_red_flags(facts) == []
    assert risk_level([], []) == "low"


def test_dissolved_is_high() -> None:
    assert flags_of(mk("Q1.status", status="dissolved"))["status"] == "high"


def test_failed_statuses_are_high_and_odd_status_is_medium() -> None:
    assert flags_of(mk("Q1.status", status="liquidation"))["status"] == "high"
    assert flags_of(mk("Q1.status", status="converted-closed"))["status"] == "medium"


def test_insolvency_record_is_high() -> None:
    assert flags_of(mk("Q7.insolvency", case_count=2))["insolvency"] == "high"


def test_age_thresholds_only_for_active_companies() -> None:
    assert flags_of(ACTIVE, mk("Q2.age", age_days=100))["age"] == "medium"
    assert flags_of(ACTIVE, mk("Q2.age", age_days=500))["age"] == "low"
    assert "age" not in flags_of(ACTIVE, mk("Q2.age", age_days=800))
    assert "age" not in flags_of(mk("Q1.status", status="dissolved"), mk("Q2.age", age_days=100))


def test_overdue_filings() -> None:
    got = flags_of(mk("Q4.accounts", overdue=True), mk("Q4.confirmation_statement", overdue=True))
    assert got["accounts_overdue"] == "medium"
    assert got["confirmation_overdue"] == "medium"
    assert flags_of(mk("Q4.accounts", overdue=None)) == {}


def test_outstanding_charges_are_low() -> None:
    assert flags_of(mk("Q6.charges", outstanding=2))["charges"] == "low"


def test_network_rules() -> None:
    def net(**counts: int) -> Fact:
        return mk("Q8.network", other_companies=sum(counts.values()), status_counts=counts)

    assert flags_of(net(liquidation=2, administration=1))["network"] == "high"
    assert flags_of(net(liquidation=1, active=3))["network"] == "low"
    assert flags_of(net(dissolved=5))["network"] == "low"
    assert "network" not in flags_of(net(dissolved=4, active=2))
    assert "network" not in flags_of(mk("Q8.network", other_companies=0, status_counts={}))


def test_network_flag_wording_is_neutral() -> None:
    flag = evaluate_red_flags(
        [mk("Q8.network", other_companies=1, status_counts={"liquidation": 1})]
    )[0]
    assert "not a finding about anyone's conduct" in flag.detail
    assert "1 company" in flag.detail


def test_turnover_and_address_changes() -> None:
    assert (
        flags_of(mk("Q9.officer_changes", appointed=2, resigned=1))["officer_turnover"] == "medium"
    )
    assert flags_of(mk("Q9.officer_changes", appointed=1, resigned=1))["officer_turnover"] == "low"
    assert flags_of(mk("Q9.officer_changes", appointed=1, resigned=0)) == {}
    assert flags_of(mk("Q9.address_changes", count=2))["address_changes"] == "medium"
    assert flags_of(mk("Q9.address_changes", count=1)) == {}


def test_no_directors_and_no_psc_only_when_active() -> None:
    got = flags_of(
        ACTIVE, mk("Q3.officers_current", directors=[]), mk("Q5.control", current_total=0)
    )
    assert got["no_directors"] == "medium"
    assert got["no_psc"] == "info"
    dissolved = mk("Q1.status", status="dissolved")
    assert "no_directors" not in flags_of(dissolved, mk("Q3.officers_current", directors=[]))


def test_flags_sorted_by_severity() -> None:
    flags = evaluate_red_flags(
        [mk("Q6.charges", outstanding=1), mk("Q1.status", status="dissolved")]
    )
    assert [f.severity for f in flags] == ["high", "low"]


def gap(q: str) -> Gap:
    return Gap(question_id=q, tool="t", reason="r")


def test_risk_level_priority() -> None:
    high = evaluate_red_flags([mk("Q1.status", status="dissolved")])
    medium = evaluate_red_flags([mk("Q4.accounts", overdue=True)])
    many_gaps = [gap("Q3"), gap("Q5"), gap("Q8")]
    assert risk_level(high, many_gaps) == "high"  # a real high flag is never hidden
    assert risk_level(medium, many_gaps) == "insufficient_data"
    assert risk_level([], many_gaps) == "insufficient_data"
    assert risk_level([], [gap("Q3"), gap("Q3"), gap("Q5")]) == "low"  # 2 distinct questions
    assert risk_level(medium, []) == "medium"


def test_assessment_text_is_labelled_opinion() -> None:
    flags = evaluate_red_flags([mk("Q4.accounts", overdue=True)])
    text = assessment_text("medium", flags, [gap("Q8")])
    assert (
        "opinion" in text and "MEDIUM risk" in text and "1 check(s) could not be completed" in text
    )
    assert "No red flags" in assessment_text("low", [], [])
    insufficient = assessment_text("insufficient_data", flags, [gap("Q3"), gap("Q5"), gap("Q8")])
    assert "not enough data" in insufficient and "Accounts are overdue" in insufficient


def test_members_voluntary_liquidation_is_not_high() -> None:
    f = flags_of(
        mk("Q1.status", status="liquidation"),
        mk("Q7.insolvency", case_count=1, case_types=["members-voluntary-liquidation"]),
    )
    assert f["status"] == "medium" and "insolvency" not in f  # one flag, not two
    dissolved = flags_of(
        mk("Q1.status", status="dissolved"),
        mk("Q7.insolvency", case_count=1, case_types=["members-voluntary-liquidation"]),
    )
    assert dissolved["insolvency"] == "medium"
    creditors = flags_of(
        mk("Q1.status", status="liquidation"),
        mk("Q7.insolvency", case_count=1, case_types=["creditors-voluntary-liquidation"]),
    )
    assert creditors["status"] == "high" and creditors["insolvency"] == "high"


def test_proposal_to_strike_off_is_high() -> None:
    f = flags_of(mk("Q1.status", status="active", status_detail="active-proposal-to-strike-off"))
    assert f["strike_off"] == "high"
    assert "strike_off" not in flags_of(ACTIVE)


def test_single_linked_liquidation_is_low_two_medium_three_high() -> None:
    def net(n: int) -> dict[str, str]:
        return flags_of(
            ACTIVE, mk("Q8.network", other_companies=9, status_counts={"liquidation": n})
        )

    assert net(1)["network"] == "low"
    assert net(2)["network"] == "medium"
    assert net(3)["network"] == "high"


def test_formation_appointments_are_not_officer_changes() -> None:
    facts = [
        mk("Q2.age", date_of_creation="2026-02-06", age_days=257),
        mk(
            "Q9.officer_changes",
            appointed=2,
            resigned=0,
            appointed_dates=["2026-02-06", "2026-02-06"],
        ),
    ]
    assert "Q9.officer_changes" not in flags_of(*facts)
    later = [
        facts[0],
        mk(
            "Q9.officer_changes",
            appointed=2,
            resigned=0,
            appointed_dates=["2026-02-06", "2026-08-01"],
        ),
    ]
    assert "Q9.officer_changes" not in flags_of(*later)  # one real change
