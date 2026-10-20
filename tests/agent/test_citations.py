import pytest
from ukvet_agent.citations import MAX_CLAIM_CHARS, check_claim, check_claims
from ukvet_agent.schemas import Claim, Fact
from ukvet_agent.text import fact_tokens


def fact(fid: str, statement: str, *extra_numbers: object) -> Fact:
    t = fact_tokens(statement, extra_numbers)
    return Fact(
        id=fid,
        question_id=fid.split(".")[0],
        statement=statement,
        dates=sorted(t.dates),
        numbers=sorted(t.numbers),
    )


FACTS = {
    "Q2.age": fact("Q2.age", "Incorporated on 4 March 2019; age 7.0 years (2557 days)"),
    "Q6.charges": fact("Q6.charges", "1 outstanding, 0 part-satisfied and 1 satisfied charges"),
}


def test_valid_claim_passes() -> None:
    claim = Claim(text="It was incorporated on 4 March 2019.", fact_ids=["Q2.age"])
    assert check_claim(claim, FACTS) is None


def test_year_only_mention_is_allowed() -> None:
    assert check_claim(Claim(text="Formed in 2019.", fact_ids=["Q2.age"]), FACTS) is None


@pytest.mark.parametrize(
    ("text", "ids", "needle"),
    [
        ("", ["Q2.age"], "empty"),
        ("   ", ["Q2.age"], "empty"),
        ("Formed in 2019.", [], "no citation"),
        ("Formed in 2019.", ["Q99.nope"], "unknown fact id"),
        ("Formed on 5 March 2019.", ["Q2.age"], "not in the cited facts"),
        ("It has 9 charges.", ["Q6.charges"], "not in the cited facts"),
        ("The company is a fraud.", ["Q2.age"], "wrongdoing"),
        ("Looks suspicious.", ["Q2.age"], "wrongdoing"),
        ("Formed in 2019. " + "x" * MAX_CLAIM_CHARS, ["Q2.age"], "too long"),
    ],
)
def test_invalid_claims(text: str, ids: list[str], needle: str) -> None:
    reason = check_claim(Claim(text=text, fact_ids=ids), FACTS)
    assert reason is not None and needle in reason


def test_numbers_must_come_from_the_cited_fact_not_just_any_fact() -> None:
    # "2557" exists in Q2.age but the claim cites Q6.charges
    claim = Claim(text="It is 2557 days old.", fact_ids=["Q6.charges"])
    assert check_claim(claim, FACTS) is not None


def test_citing_several_facts_pools_their_values() -> None:
    claim = Claim(text="Formed 4 March 2019 and has 1 satisfied charge.", fact_ids=list(FACTS))
    assert check_claim(claim, FACTS) is None


def test_check_claims_drops_invalid_dedupes_and_reports() -> None:
    good = Claim(text="Formed in 2019.", fact_ids=["Q2.age"])
    result = check_claims(
        [good, good, Claim(text="Formed in 1999.", fact_ids=["Q2.age"])],
        FACTS,
    )
    assert [c.text for c in result.kept] == ["Formed in 2019."]
    assert len(result.violations) == 1
    assert "1999" in str(result.violations[0])
