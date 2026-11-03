"""Output guardrails (Phase 4): mechanical checks that a finished report keeps its promises.

The promises (docs/11-system-design.md section 8, backlog "Output guardrails"):

1. No statements about individuals beyond the records. Enforced upstream (the writer only sees
   facts; the citation checker requires dates, numbers and wording to match the cited facts and
   rejects wrongdoing wording). Re-checked here on the FINISHED report.
2. Opinion is labelled as opinion: the assessment always starts with the automated-assessment
   label, and the narrative never states a risk level or gives advice (ukvet calculates the level).
3. The disclaimer and the Companies House attribution are always present, unchanged.
4. Nothing that looks like markup, a link or a control character reaches the user.

`check_report` returns a list of problems; an empty list means the report passed. It never raises
and it does not change the report. It is used by the eval harness (every report in the dataset
must pass) and is cheap enough to run in production if you want a last line of defence.

Limit: these are wording and structure checks. Whether a sentence is FAIR in meaning is not
something a regex can judge (risk R15).
"""

import re
from typing import Any

from ukvet_agent.redflags import ASSESSMENT_PREFIX
from ukvet_agent.schemas import ATTRIBUTION, DISCLAIMER, Claim, Fact, Report

# Wording ukvet never repeats or writes. (The citation checker keeps its own copy of FORBIDDEN so
# that module stays standalone; the eval scorer keeps a third, independent one.)
FORBIDDEN = re.compile(
    r"\b(fraud\w*|scam\w*|criminal\w*|crook\w*|illegal\w*|unlawful\w*|dishonest\w*|"
    r"suspicious|shady|serial)\b",
    re.IGNORECASE,
)
# Advice or a verdict on whether to trade: ukvet informs, it does not advise.
ADVICE = re.compile(
    r"\b(you should|we recommend|i recommend|recommend(?:ed)? (?:that|avoiding|against)|"
    r"advis(?:e|able)|safe to (?:trade|deal|invest)|not safe to|"
    r"avoid (?:trading|dealing|doing business)|"
    r"(?:do not|don't|should not) (?:trade|deal|invest))\b",
    re.IGNORECASE,
)
# The overall risk level is calculated by rules, never stated by the writer.
VERDICT = re.compile(
    r"\b(?:low|medium|high)[- ]risk\b|\brisk level\b|\boverall risk\b", re.IGNORECASE
)
_URL = re.compile(r"https?://|www\.|\]\(", re.IGNORECASE)
_MARKUP = re.compile(r"[<>]")
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f‪-‮⁦-⁩]")
MAX_FIELD_CHARS = 2000


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in _strings(v)]
    if isinstance(value, list):
        return [s for v in value for s in _strings(v)]
    return []


_NAME_KEYS = ("name", "director")
MIN_NAME_CHARS = 5


def _walk_names(value: Any) -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for k, v in value.items():
            if k in _NAME_KEYS and isinstance(v, str) and len(v) >= MIN_NAME_CHARS:
                found.append(v)
            else:
                found += _walk_names(v)
    elif isinstance(value, list):
        for v in value:
            found += _walk_names(v)
    return found


def person_names(facts: list[Fact]) -> set[str]:
    """Names of people (officers, PSCs, directors) that appear in the facts' values."""
    return {n for f in facts for n in _walk_names(f.value)}


def person_citation_problems(claim: Claim, facts: list[Fact], names: set[str]) -> list[str]:
    """A sentence that names a person must cite a fact that contains that name.

    Limit: only exact name strings are recognised. A paraphrased name is not seen.
    """
    by_id = {f.id: f for f in facts}
    cited = " ".join(
        f"{by_id[i].statement} {by_id[i].value}".lower() for i in claim.fact_ids if i in by_id
    )
    text = claim.text.lower()
    return [
        f"names a person without citing their fact: {claim.text[:60]}"
        for name in sorted(names)
        if name.lower() in text and name.lower() not in cited
    ][:1]


def claim_problems(text: str, *, llm_text: bool = False) -> list[str]:
    """Wording problems in ONE sentence. `llm_text=True` also rejects a stated risk verdict."""
    problems: list[str] = []
    if FORBIDDEN.search(text):
        problems.append("wording implies wrongdoing")
    if ADVICE.search(text):
        problems.append("gives advice")
    if llm_text and VERDICT.search(text):
        problems.append("states a risk verdict")
    if _URL.search(text):
        problems.append("contains a link")
    return problems


def check_report(report: Report) -> list[str]:
    problems: list[str] = []

    if report.disclaimer != DISCLAIMER:
        problems.append("disclaimer missing or changed")
    if report.attribution != ATTRIBUTION:
        problems.append("attribution missing or changed")
    if not report.assessment.startswith(ASSESSMENT_PREFIX):
        problems.append("assessment is not labelled as ukvet's automated opinion")

    claims = [report.headline, *report.findings]
    names = person_names(report.facts)
    q1_gap = any(g.question_id == "Q1" for g in report.gaps)
    for i, claim in enumerate(claims):
        if not claim.fact_ids and not (i == 0 and q1_gap):
            problems.append(f"claim has no citation: {claim.text[:60]}")
        problems += [
            f"{p}: {claim.text[:60]}"
            for p in claim_problems(claim.text, llm_text=report.narrative_source == "llm")
        ]
        problems += person_citation_problems(claim, report.facts, names)

    for text in _strings(report.model_dump(mode="json")):
        if _MARKUP.search(text):
            problems.append(f"raw angle bracket in output: {text[:60]!r}")
        if _CONTROL.search(text):
            problems.append(f"control character in output: {text[:60]!r}")
        if len(text) > MAX_FIELD_CHARS:
            problems.append(f"oversized field ({len(text)} chars)")
    return list(dict.fromkeys(problems))
