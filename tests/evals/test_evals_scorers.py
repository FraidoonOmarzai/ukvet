from evals_helpers import fact, report
from ukvet_agent.schemas import CitationStats, Claim, Gap, RedFlag
from ukvet_evals.schema import AbstentionCase, ExpectedFlag, FaultSpec, FlagLabel
from ukvet_evals.scorers.abstention import expected_risk, score_case
from ukvet_evals.scorers.flags import FlagScore, score_flags
from ukvet_evals.scorers.narrative import (
    NarrativeScore,
    mechanical_claim_errors,
    score_narrative,
)

FACTS = [
    fact("Q1.status", "ACME LTD (12345678) has status 'active'", status="active"),
    fact("Q2.age", "Incorporated on 4 March 2019; age 7.0 years (2557 days)", age_days=2557),
    fact(
        "Q3.officers_current", "2 current officers: 1 director (PERSON 001 (appointed 1 May 2020))"
    ),
]


def errs(text: str, ids: list[str]) -> list[str]:
    return mechanical_claim_errors(text, ids, FACTS)


# ---- narrative -------------------------------------------------------------------------------
def test_valid_claims_pass() -> None:
    assert errs("ACME LTD has status active.", ["Q1.status"]) == []
    assert errs("It was incorporated on 4 March 2019, about 7 years ago.", ["Q2.age"]) == []
    assert errs("PERSON 001 was appointed on 1 May 2020.", ["Q3.officers_current"]) == []


def test_citation_problems() -> None:
    assert errs("ACME LTD is active.", []) == ["no citation"]
    assert errs("ACME LTD is active.", ["Q9.nope"])[0].startswith("unknown fact id")
    assert errs("   ", ["Q1.status"]) == ["empty claim"]


def test_wrong_date_and_number_are_caught() -> None:
    assert any(
        "date not in cited" in e for e in errs("Incorporated on 9 September 2012.", ["Q2.age"])
    )
    assert any("number not in cited" in e for e in errs("It is 12 years old.", ["Q2.age"]))


def test_name_check_is_stricter_than_production() -> None:
    # Production's checker only verifies dates and numbers; a wrong NAME slips through it.
    assert any(
        "name or term" in e for e in errs("Director John Smith resigned.", ["Q3.officers_current"])
    )
    assert errs("The director is PERSON 001.", ["Q3.officers_current"]) == []


def test_forbidden_wording() -> None:
    assert "forbidden wording" in errs("ACME LTD looks suspicious.", ["Q1.status"])


def test_narrative_score_counts_and_exempts_the_gap_headline() -> None:
    good = report(findings=[Claim(text="It is 12 years old.", fact_ids=["Q2.age"])], facts=FACTS)
    s = NarrativeScore()
    score_narrative(good, s, "c001")
    assert s.claims == 2 and s.invalid_claims == 1 and s.by_category == {"number_not": 1}
    assert s.m2().k == 1 and s.m4_mechanical().k == 1

    gap_headline = report(
        headline=Claim(text="Status information could not be retrieved.", fact_ids=[]),
        gaps=[Gap(question_id="Q1", tool="profile", reason="x")],
    )
    s2 = NarrativeScore()
    score_narrative(gap_headline, s2, "c002")
    assert s2.invalid_claims == 0  # an explicit admission of missing data is not an uncited claim


def test_narrative_records_first_attempt_from_stats() -> None:
    from ukvet_agent.schemas import AttemptStats

    stats = CitationStats(
        attempts=[AttemptStats(attempt=1, outcome="violations", claims_total=5, claims_kept=3, claims_dropped=2),
                  AttemptStats(attempt=2, outcome="ok", claims_total=3, claims_kept=3)],
        retries=1,
    )  # fmt: skip
    s = NarrativeScore()
    score_narrative(report(stats=stats, source="llm"), s, "c001")
    assert s.llm_reports == 1 and s.first_attempt_claims == 5 and s.first_attempt_dropped == 2
    assert s.checker_intervention().k == 2


# ---- flags -----------------------------------------------------------------------------------
def flag(fid: str, sev: str = "medium") -> RedFlag:
    return RedFlag(id=fid, severity=sev, title="t", detail="d", fact_ids=["Q1.status"])  # type: ignore[arg-type]


def test_flag_recall_precision_and_lists() -> None:
    label = FlagLabel(
        company="c001",
        expected=[ExpectedFlag(id="status", severity="high"), ExpectedFlag(id="charges")],
    )
    s = FlagScore()
    score_flags(report(flags=[flag("status", "medium"), flag("age")]), label, ["dissolved"], s)
    assert (s.found_total, s.expected_total) == (1, 2)  # charges missed
    assert (s.produced_expected, s.produced_total) == (1, 2)  # age unexpected
    assert s.missed[0]["flag"] == "charges" and s.unexpected[0]["flag"] == "age"
    assert s.severity_mismatch[0]["expected"] == "high" and s.severity().k == 0


def test_unlabelled_company_is_skipped() -> None:
    s = FlagScore()
    score_flags(report(flags=[flag("status")]), FlagLabel(company="c001"), [], s)
    assert s.unlabelled == 1 and s.expected_total == 0 and s.produced_total == 0


def test_empty_expected_list_means_no_flags_expected() -> None:
    s = FlagScore()
    score_flags(report(flags=[flag("age", "low")]), FlagLabel(company="c001", expected=[]), [], s)
    assert s.labelled == 1 and s.unexpected and s.precision().k == 0


def test_second_labeller_agreement() -> None:
    label = FlagLabel(
        company="c1",
        expected=[ExpectedFlag(id="status")],
        second_labeller_expected=["status", "age"],
    )
    s = FlagScore()
    score_flags(report(flags=[flag("status")]), label, [], s)
    out = s.to_dict()["second_labeller"]
    assert out["pairs"] == 2 and out["agreement"]["k"] == 1


# ---- abstention ------------------------------------------------------------------------------
def case(**kw: object) -> AbstentionCase:
    base: dict[str, object] = {
        "id": "a1", "company": "c001", "faults": [FaultSpec(tool="get_charges", mode="timeout")],
        "expected_gap_questions": ["Q6"], "expected_absent_fact_ids": ["Q6.charges"],
    }  # fmt: skip
    base.update(kw)
    return AbstentionCase(**base)  # type: ignore[arg-type]


CLEAN = report(facts=[*FACTS, fact("Q6.charges", "1 outstanding charges", outstanding=1)])
GAP6 = [Gap(question_id="Q6", tool="charges", reason="x", retryable=True)]
ASSESS = "ukvet's automated assessment: LOW risk. 1 check(s) could not be completed."


def test_abstention_pass() -> None:
    faulty = report(facts=FACTS, gaps=GAP6, assessment=ASSESS)
    assert score_case(case(), CLEAN, faulty).passed


def test_abstention_catches_invented_fact() -> None:
    invented = report(
        facts=[*FACTS, fact("Q6.charges", "0 outstanding charges", outstanding=0)],
        gaps=GAP6,
        assessment=ASSESS,
    )
    r = score_case(case(), CLEAN, invented)
    assert not r.passed and any("must be absent" in c for c in r.failed_checks)


def test_abstention_catches_corrupted_and_missing_facts() -> None:
    changed = [
        fact("Q1.status", "ACME LTD (12345678) has status 'dissolved'", status="dissolved"),
        *FACTS[1:],
    ]
    r = score_case(case(), CLEAN, report(facts=changed, gaps=GAP6, assessment=ASSESS))
    assert any("changed value" in c for c in r.failed_checks)
    dropped = score_case(case(), CLEAN, report(facts=FACTS[:1], gaps=GAP6, assessment=ASSESS))
    assert any("disappeared" in c for c in dropped.failed_checks)


def test_abstention_catches_wrong_gap_set_and_risk() -> None:
    r = score_case(case(), CLEAN, report(facts=FACTS, gaps=[], assessment=ASSESS))
    assert any(c.startswith("gap_questions") for c in r.failed_checks)
    bad_risk = report(facts=FACTS, gaps=GAP6, assessment=ASSESS, risk="high")
    assert any("risk_level" in c for c in score_case(case(), CLEAN, bad_risk).failed_checks)


def test_abstention_requires_the_assessment_to_admit_gaps() -> None:
    silent = report(facts=FACTS, gaps=GAP6, assessment="LOW risk. Nothing to see.")
    assert any("assessment" in c for c in score_case(case(), CLEAN, silent).failed_checks)


def test_gaps_already_in_the_clean_run_are_not_blamed_on_the_fault() -> None:
    clean = report(facts=[*FACTS, fact("Q6.charges", "1 outstanding charges", outstanding=1)],
                   gaps=[Gap(question_id="Q8", tool="appointments.2", reason="x")], assessment=ASSESS)  # fmt: skip
    faulty = report(facts=FACTS, assessment=ASSESS,
                    gaps=[*GAP6, Gap(question_id="Q8", tool="appointments.2", reason="x")])  # fmt: skip
    assert score_case(case(), clean, faulty).passed


def test_expected_risk_rule() -> None:
    gaps3 = [Gap(question_id=q, tool="t", reason="r") for q in ("Q1", "Q2", "Q3")]
    assert expected_risk(report(gaps=gaps3)) == "insufficient_data"
    assert expected_risk(report(gaps=gaps3, flags=[flag("status", "high")])) == "high"
    assert expected_risk(report(flags=[flag("age", "medium")])) == "medium"
    assert expected_risk(report()) == "low"
