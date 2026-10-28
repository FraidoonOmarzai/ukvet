"""Pydantic models for facts, claims, flags, reports and API responses."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

ALL_QUESTIONS = ["Q1", "Q2", "Q3", "Q4", "Q5", "Q6", "Q7", "Q8", "Q9"]

DISCLAIMER = (
    "Informational only. Not legal, financial or credit advice. Based on public Companies House "
    "records at the time of retrieval, which may be incomplete or out of date. Verify before "
    "making decisions."
)
ATTRIBUTION = (
    "Contains public sector information licensed under the Open Government Licence v3.0 "
    "(Companies House). Not affiliated with or endorsed by Companies House."
)

RiskLevel = Literal["low", "medium", "high", "insufficient_data"]
Severity = Literal["high", "medium", "low", "info"]


class SourceRef(BaseModel):
    endpoint: str
    url: str
    retrieved_at: datetime


class Fact(BaseModel):
    """One verified statement of fact with its source. The unit of citation."""

    id: str = Field(description="Stable ID, e.g. 'Q4.accounts'. Claims cite these.")
    question_id: str
    statement: str = Field(description="Canonical plain-English statement of the fact.")
    value: dict[str, Any] = Field(default_factory=dict, description="Structured form.")
    caveats: list[str] = Field(default_factory=list)
    sources: list[SourceRef] = Field(default_factory=list)
    # Checkable tokens (see text.py). Internal audit data: excluded from API output.
    dates: list[str] = Field(default_factory=list, exclude=True)
    numbers: list[str] = Field(default_factory=list, exclude=True)


class Claim(BaseModel):
    """A sentence in the report plus the facts that support it."""

    text: str
    fact_ids: list[str] = Field(default_factory=list)


class RedFlag(BaseModel):
    id: str
    severity: Severity
    title: str
    detail: str
    fact_ids: list[str]


class Gap(BaseModel):
    question_id: str
    tool: str
    reason: str
    retryable: bool = False


class Candidate(BaseModel):
    company_number: str
    name: str
    status: str | None = None
    company_type: str | None = None
    date_of_creation: str | None = None
    address_snippet: str | None = None


class AttemptStats(BaseModel):
    """What happened in ONE narrative attempt (the LLM gets at most two)."""

    attempt: int
    outcome: Literal["ok", "violations", "llm_error"]
    claims_total: int = 0
    claims_kept: int = 0
    claims_dropped: int = 0
    violations: list[str] = Field(default_factory=list)
    error: str | None = None


class CitationStats(BaseModel):
    """Citation outcome of the narrative.

    `claims_*` and `violations` describe the LAST attempt that returned a draft. To see what the
    FIRST attempt got wrong, or whether a retry was caused by the checker or by an LLM error, read
    `attempts` and `llm_errors`.
    """

    claims_total: int = 0
    claims_kept: int = 0
    claims_dropped: int = 0
    retries: int = 0
    violations: list[str] = Field(default_factory=list)
    llm_errors: int = 0
    attempts: list[AttemptStats] = Field(default_factory=list)


class Usage(BaseModel):
    """Work done for ONE report: tool calls, LLM calls, tokens and cost (metrics M8 and M9).

    `cost_gbp` is `None` unless both prices are set in `.env`; see `ukvet_agent.usage`.
    """

    tool_calls: int = 0
    tools: list[str] = Field(default_factory=list)
    llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_gbp: float | None = None


class Usage(BaseModel):
    """Measured work for one report: tool calls, LLM calls, tokens, cost (M8, M9)."""

    tool_calls: int = 0
    tools: list[str] = Field(default_factory=list)
    llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_gbp: float | None = Field(
        default=None, description="None unless UKVET_PRICE_IN/OUT_GBP_PER_MTOK are set."
    )


class Report(BaseModel):
    kind: Literal["report"] = "report"
    company_number: str
    company_name: str
    generated_at: datetime
    risk_level: RiskLevel
    assessment: str = Field(
        description="ukvet's automated assessment: an opinion generated from the red-flag rules."
    )
    headline: Claim
    findings: list[Claim]
    red_flags: list[RedFlag]
    facts: list[Fact]
    gaps: list[Gap]
    data_quality_notes: list[str]
    narrative_source: Literal["llm", "template"]
    model: str | None = None
    citation_stats: CitationStats
    timings_ms: dict[str, int] = Field(default_factory=dict)
    usage: Usage = Field(default_factory=Usage)
    disclaimer: str = DISCLAIMER
    attribution: str = ATTRIBUTION


class NeedsSelection(BaseModel):
    kind: Literal["needs_selection"] = "needs_selection"
    query: str
    message: str
    candidates: list[Candidate]
