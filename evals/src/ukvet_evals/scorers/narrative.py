"""M2 (unsupported claims) and M4 (citation validity) for the written narrative.

The mechanical checks here are a SEPARATE re-implementation of what ukvet_agent.citations does
(it does not import it), and they are stricter in one way production is not: proper names must
appear in the cited facts. Disagreements with production are visible as claims that production
kept but this scorer rejects (`stricter_than_production`).

The optional semantic check (does the cited fact actually support the sentence?) comes from the
LLM judge (judge.py) and is always reported separately, with its calibration against hand labels.
"""

import contextlib
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from ukvet_agent.schemas import Fact, Report

from ukvet_evals.stats import Rate

_MONTHS = [
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
]  # fmt: skip
_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_LONG = re.compile(r"\b(\d{1,2})\s+(" + "|".join(_MONTHS) + r")\s+(\d{4})\b", re.IGNORECASE)
_NUM = re.compile(r"(?<![\w.])\d+(?:\.\d+)?(?!\w)")
_FORBIDDEN = re.compile(
    r"\b(fraud\w*|scam\w*|criminal\w*|crook\w*|illegal\w*|unlawful\w*|dishonest\w*|"
    r"suspicious|shady|serial)\b",
    re.IGNORECASE,
)
_WORD = re.compile(r"[A-Za-z][A-Za-z'&-]+")
_CAPITALISED = re.compile(r"\b[A-Z][A-Za-z'&-]{2,}\b")
_ALLOWED_CAPS = {
    *(m for m in _MONTHS),
    "companies", "house", "ukvet", "uk", "psc", "llp", "ltd", "limited", "plc", "the", "this",
    "that", "these", "however", "also", "both", "there", "its", "it", "no", "all", "one", "two",
    "three", "four", "five", "six", "seven", "eight", "nine", "ten", "overall", "in", "on",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday", "accounts",
    "confirmation", "statement", "charges", "charge", "director", "directors", "officer",
    "officers", "company", "registered", "office", "red", "flag", "flags", "risk", "status",
    "active", "dissolved", "liquidation", "administration", "high", "medium", "low", "info",
}  # fmt: skip


def _norm_num(raw: str) -> str:
    return raw.rstrip("0").rstrip(".") if "." in raw else raw


def tokens(text: str) -> tuple[set[str], set[str]]:
    """(ISO dates, plain numbers) found in prose."""
    dates: set[str] = set()
    for m in _ISO.finditer(text):
        with contextlib.suppress(ValueError):
            dates.add(date(int(m[1]), int(m[2]), int(m[3])).isoformat())
    for m in _LONG.finditer(text):
        with contextlib.suppress(ValueError):
            dates.add(date(int(m[3]), _MONTHS.index(m[2].lower()) + 1, int(m[1])).isoformat())
    stripped = _LONG.sub(" ", _ISO.sub(" ", text))
    return dates, {_norm_num(n) for n in _NUM.findall(stripped)}


def _scalars(value: Any) -> list[str]:
    out: list[str] = []
    if isinstance(value, dict):
        for k, v in value.items():
            out.append(str(k))
            out.extend(_scalars(v))
    elif isinstance(value, list):
        for v in value:
            out.extend(_scalars(v))
    elif value is not None and not isinstance(value, bool):
        out.append(str(value))
    return out


def _support_text(fact: Fact) -> str:
    return " ".join([fact.statement, *fact.caveats, *_scalars(fact.value)])


def mechanical_claim_errors(text: str, fact_ids: list[str], facts: list[Fact]) -> list[str]:
    """Independent citation check. Returns a list of problems (empty = valid)."""
    by_id = {f.id: f for f in facts}
    errors: list[str] = []
    if not text.strip():
        return ["empty claim"]
    if not fact_ids:
        return ["no citation"]
    unknown = [i for i in fact_ids if i not in by_id]
    if unknown:
        return [f"unknown fact id {', '.join(unknown)}"]
    if _FORBIDDEN.search(text):
        errors.append("forbidden wording")
    support = " ".join(_support_text(by_id[i]) for i in fact_ids)
    s_dates, s_nums = tokens(support)
    c_dates, c_nums = tokens(text)
    # ISO dates inside the value are digits too: allow their components as numbers.
    for d in c_dates - s_dates:
        errors.append(f"date not in cited facts: {d}")
    for n in sorted(c_nums - s_nums):
        errors.append(f"number not in cited facts: {n}")
    support_words = {w.lower() for w in _WORD.findall(support)}
    for sentence in re.split(r"(?<=[.!?])\s+", text.strip()):
        for m in _CAPITALISED.finditer(sentence):
            word = m.group(0).lower()
            at_start = sentence[: m.start()].strip() == ""
            if at_start or word in _ALLOWED_CAPS or word in support_words:
                continue
            errors.append(f"name or term not in cited facts: {m.group(0)}")
    return errors


def report_claim_errors(report: Report) -> list[tuple[str, list[str]]]:
    """(claim text, problems) for every claim that has any.

    One deliberate exemption: when the status check itself failed (a Q1 gap), the template
    headline says so and cites nothing, because there is no fact to cite. That sentence is an
    explicit admission of missing data, not an uncited assertion, so it is not counted as an error.
    """
    q1_gap = any(g.question_id == "Q1" for g in report.gaps)
    out: list[tuple[str, list[str]]] = []
    for i, claim in enumerate([report.headline, *report.findings]):
        errors = mechanical_claim_errors(claim.text, claim.fact_ids, report.facts)
        if i == 0 and q1_gap and not claim.fact_ids and errors == ["no citation"]:
            continue
        if errors:
            out.append((claim.text, errors))
    return out


def _category(error: str) -> str:
    for key in (
        "no citation",
        "unknown fact",
        "forbidden",
        "date not",
        "number not",
        "name or term",
    ):
        if error.startswith(key):
            return key.replace(" ", "_")
    return "other"


@dataclass
class NarrativeScore:
    reports: int = 0
    llm_reports: int = 0
    claims: int = 0
    invalid_claims: int = 0
    by_category: dict[str, int] = field(default_factory=dict)
    examples: list[dict[str, Any]] = field(default_factory=list)
    first_attempt_claims: int = 0
    first_attempt_dropped: int = 0
    llm_errors: int = 0
    retries: int = 0
    semantic_judged: int = 0
    semantic_unsupported: int = 0

    def m2(self) -> Rate:
        """Share of shown claims that are unsupported (mechanical + name check)."""
        return Rate(self.invalid_claims, self.claims)

    def m4_mechanical(self) -> Rate:
        return Rate(self.claims - self.invalid_claims, self.claims)

    def m4_semantic(self) -> Rate:
        return Rate(self.semantic_judged - self.semantic_unsupported, self.semantic_judged)

    def checker_intervention(self) -> Rate:
        return Rate(self.first_attempt_dropped, self.first_attempt_claims)

    def to_dict(self) -> dict[str, Any]:
        return {
            "reports": self.reports,
            "llm_reports": self.llm_reports,
            "claims": self.claims,
            "m2_unsupported": self.m2().to_dict(),
            "m4_mechanical_valid": self.m4_mechanical().to_dict(),
            "m4_semantic_supported": self.m4_semantic().to_dict(),
            "invalid_by_category": self.by_category,
            "writer_needed_checker": self.checker_intervention().to_dict(),
            "llm_errors": self.llm_errors,
            "retries": self.retries,
            "examples": self.examples[:25],
        }


def score_narrative(report: Report, score: NarrativeScore, company: str) -> None:
    score.reports += 1
    if report.narrative_source == "llm":
        score.llm_reports += 1
    stats = report.citation_stats
    score.llm_errors += stats.llm_errors
    score.retries += stats.retries
    if stats.attempts and stats.attempts[0].outcome != "llm_error":
        score.first_attempt_claims += stats.attempts[0].claims_total
        score.first_attempt_dropped += stats.attempts[0].claims_dropped
    score.claims += 1 + len(report.findings)
    for text, errors in report_claim_errors(report):
        score.invalid_claims += 1
        for e in errors:
            score.by_category[_category(e)] = score.by_category.get(_category(e), 0) + 1
        score.examples.append(
            {
                "company": company,
                "claim": text[:200],
                "errors": errors,
                "source": report.narrative_source,
            }
        )
