"""Phase 4: output guardrails on a finished report."""

import pytest
from evals_helpers import fact, report
from ukvet_agent.guardrails import check_report, claim_problems
from ukvet_agent.redflags import ASSESSMENT_PREFIX
from ukvet_agent.schemas import ATTRIBUTION, DISCLAIMER, Claim, Gap


def test_a_clean_report_passes() -> None:
    assert check_report(report(assessment=ASSESSMENT_PREFIX + " LOW risk.")) == []


@pytest.mark.parametrize(
    "text",
    ["The director is a fraudster.", "This looks suspicious.", "An illegal filing was made."],
)
def test_wrongdoing_wording_is_flagged(text: str) -> None:
    assert "wording implies wrongdoing" in claim_problems(text)


@pytest.mark.parametrize(
    "text",
    ["You should not trade with them.", "We recommend avoiding this company.", "Safe to trade."],
)
def test_advice_is_flagged(text: str) -> None:
    assert "gives advice" in claim_problems(text)


def test_a_stated_verdict_is_only_flagged_for_llm_text() -> None:
    assert claim_problems("This is a high-risk company.") == []
    assert claim_problems("This is a high-risk company.", llm_text=True) == [
        "states a risk verdict"
    ]


def test_links_are_flagged() -> None:
    assert "contains a link" in claim_problems("See https://evil.example.invalid")
    assert "contains a link" in claim_problems("[click](x)")


def test_report_level_promises_are_enforced() -> None:
    bad = report(assessment="This company is fine.")
    bad.disclaimer = "nothing"
    bad.attribution = "mine"
    problems = check_report(bad)
    assert "disclaimer missing or changed" in problems
    assert "attribution missing or changed" in problems
    assert "assessment is not labelled as ukvet's automated opinion" in problems
    assert (DISCLAIMER, ATTRIBUTION) != ("nothing", "mine")


def test_uncited_claims_are_flagged_but_an_empty_headline_with_a_q1_gap_is_not() -> None:
    uncited = report(findings=[Claim(text="Something happened.", fact_ids=[])])
    assert any(p.startswith("claim has no citation") for p in check_report(uncited))
    gap = report(
        facts=[fact("Q2.x", "something")],
        headline=Claim(text="Company not found.", fact_ids=[]),
        gaps=[Gap(question_id="Q1", tool="get_company_profile", reason="registry down")],
    )
    assert not any(p.startswith("claim has no citation") for p in check_report(gap))


def test_markup_control_characters_and_oversized_text_are_flagged() -> None:
    f = fact("Q1.status", "ok <script>")
    problems = check_report(report(facts=[f]))
    assert any("raw angle bracket" in p for p in problems)
    f = fact("Q1.status", "ok\x07")
    assert any("control character" in p for p in check_report(report(facts=[f])))
    f = fact("Q1.status", "x" * 2500)
    assert any("oversized field" in p for p in check_report(report(facts=[f])))


def test_problems_are_not_repeated() -> None:
    f = fact("Q1.status", "<<<>>>")
    problems = check_report(report(facts=[f]))
    assert len(problems) == len(set(problems))


# ---- promise 1: a sentence that names a person must cite a fact that contains the name --------


def _person_facts() -> list:  # type: ignore[type-arg]
    return [
        fact("Q1.status", "ACME LTD is active"),
        fact("Q3.officers_current", "1 director: JOHN SMITH", directors=[{"name": "JOHN SMITH"}]),
    ]


def test_naming_a_person_without_citing_their_fact_is_flagged() -> None:
    bad = report(
        facts=_person_facts(),
        headline=Claim(text="JOHN SMITH runs ACME LTD.", fact_ids=["Q1.status"]),
        assessment=ASSESSMENT_PREFIX + "LOW risk.",
    )
    assert any("names a person without citing" in p for p in check_report(bad))


def test_naming_a_person_with_the_right_citation_passes() -> None:
    good = report(
        facts=_person_facts(),
        headline=Claim(text="ACME LTD is active.", fact_ids=["Q1.status"]),
        findings=[Claim(text="JOHN SMITH is the only director.", fact_ids=["Q3.officers_current"])],
        assessment=ASSESSMENT_PREFIX + "LOW risk.",
    )
    assert check_report(good) == []


# ---- promise 1 (wording): the citation checker's phrase list --------------------------------

BAD_PHRASES = [
    "The director is a fraudster.",
    "This is a scam company.",
    "A criminal runs it.",
    "Directors behaved illegally and unlawfully.",
    "They are dishonest.",
    "It looks suspicious.",
    "A serial failure.",
    "A shady set-up.",
]
APPROVED_PHRASES = [
    "JOHN SMITH was a director of 3 companies that were dissolved.",
    "The company has 2 outstanding charges.",
    "Accounts are overdue.",
    "No person with significant control is on record.",
]


@pytest.mark.parametrize("text", BAD_PHRASES)
def test_the_citation_checker_rejects_wrongdoing_phrases(text: str) -> None:
    from ukvet_agent.citations import check_claim

    facts = {"Q1.status": fact("Q1.status", "ACME LTD is active")}
    assert check_claim(Claim(text=text, fact_ids=["Q1.status"]), facts) is not None


@pytest.mark.parametrize("text", APPROVED_PHRASES)
def test_approved_phrasings_are_not_flagged_as_wrongdoing(text: str) -> None:
    assert "wording implies wrongdoing" not in claim_problems(text)


# ---- promises 2 and 3 across every report of the committed demo dataset -----------------------


async def test_every_demo_report_has_the_disclaimer_label_and_passes_the_guardrails() -> None:
    from evals_helpers import REPO
    from ukvet_evals.run import RunOptions, evaluate

    res = await evaluate(RunOptions(root=REPO, dataset="demo", split="all"))
    assert res["guardrails"]["reports"] > 0
    assert res["guardrails"]["violations"] == [], res["guardrails"]["violations"]
