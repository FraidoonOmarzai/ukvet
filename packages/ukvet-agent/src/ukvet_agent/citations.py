"""The citation checker: ukvet's core quality mechanism (feeds metrics M2 and M4).

Every claim the LLM writes is checked deterministically:
  1. it must cite at least one fact, and every cited fact ID must exist;
  2. every date and number in the claim must appear in the cited facts;
  3. it must not use wording that implies wrongdoing;
  4. it must be non-empty and not absurdly long.
Claims that fail are dropped (and reported), never shown.

Known limit (be honest about it): this verifies IDs, dates and numbers, which are what LLMs most
often get wrong. It does not verify that a *name* was copied correctly or that a qualitative
statement is fair; Phase 3's evals measure those.
"""

import re
from dataclasses import dataclass

from ukvet_agent.schemas import Claim, Fact
from ukvet_agent.text import extract_checkables

MAX_CLAIM_CHARS = 600
_FORBIDDEN = re.compile(
    r"\b(fraud\w*|scam\w*|criminal\w*|crook\w*|illegal\w*|unlawful\w*|dishonest\w*|"
    r"suspicious|shady|serial)\b",
    re.IGNORECASE,
)


@dataclass
class Violation:
    claim: str
    reason: str

    def __str__(self) -> str:
        return f"{self.reason}: {self.claim[:120]}"


@dataclass
class CheckResult:
    kept: list[Claim]
    violations: list[Violation]


def check_claim(claim: Claim, facts: dict[str, Fact]) -> str | None:
    """Return the reason a claim is invalid, or None if it passes."""
    text = claim.text.strip()
    if not text:
        return "empty claim"
    if len(text) > MAX_CLAIM_CHARS:
        return "claim too long"
    if not claim.fact_ids:
        return "no citation"
    unknown = [i for i in claim.fact_ids if i not in facts]
    if unknown:
        return f"cites unknown fact id(s) {', '.join(unknown)}"
    if _FORBIDDEN.search(text):
        return "uses wording that implies wrongdoing"

    cited_dates: set[str] = set()
    cited_numbers: set[str] = set()
    for fid in claim.fact_ids:
        cited_dates.update(facts[fid].dates)
        cited_numbers.update(facts[fid].numbers)
    found = extract_checkables(text)
    bad_dates = sorted(found.dates - cited_dates)
    bad_numbers = sorted(found.numbers - cited_numbers)
    if bad_dates or bad_numbers:
        values = ", ".join([*bad_dates, *bad_numbers])
        return f"contains value(s) not in the cited facts ({values})"
    return None


def check_claims(claims: list[Claim], facts: dict[str, Fact]) -> CheckResult:
    kept: list[Claim] = []
    violations: list[Violation] = []
    seen: set[str] = set()
    for claim in claims:
        reason = check_claim(claim, facts)
        if reason:
            violations.append(Violation(claim.text, reason))
            continue
        key = claim.text.strip().lower()
        if key in seen:
            continue
        seen.add(key)
        kept.append(Claim(text=claim.text.strip(), fact_ids=list(dict.fromkeys(claim.fact_ids))))
    return CheckResult(kept=kept, violations=violations)
