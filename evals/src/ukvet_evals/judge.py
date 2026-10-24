"""LLM-as-judge for the SEMANTIC part of M2/M4 (does the cited fact support the sentence?).

Rules (ADR-009):
- the judge must be a DIFFERENT model family from the writer (a model tends to approve itself);
- it never gates CI: it is reported with its agreement against hand labels;
- calibrate first: hand-judge 20 claims, run `ukvet-evals judge-agreement`, report the number.
"""

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from ukvet_agent.schemas import Report

from ukvet_evals.llmcache import JsonCache, cache_key
from ukvet_evals.stats import Rate, cohens_kappa

SYSTEM = """You are a strict fact-checker for short company due-diligence reports.
You get numbered FACTS (the only truth) and numbered CLAIMS (sentences with the fact ids they cite).
For each claim decide whether the cited facts FULLY support it.
- supported=true only if every statement in the claim follows from the cited facts.
- supported=false if the claim adds, changes or exaggerates anything (a name, a number, a date, a
  cause, a judgement about conduct) that the cited facts do not contain.
- Wording that implies wrongdoing by a person is never supported.
Give a one-line reason. Do not use outside knowledge."""


class ClaimVerdict(BaseModel):
    index: int
    supported: bool
    reason: str = ""


class JudgeVerdict(BaseModel):
    claims: list[ClaimVerdict] = Field(default_factory=list)


class JudgeBackend(Protocol):
    name: str

    async def judge(self, system: str, user: str) -> JudgeVerdict: ...


class JudgeSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="JUDGE_", extra="ignore", env_file=None)

    provider: Literal["none", "openai", "anthropic", "openai_compatible"] = "none"
    model: str | None = None
    api_key: SecretStr | None = None
    base_url: str | None = None
    max_tokens: int = 1500
    timeout_seconds: float = 30.0


class LangChainJudge:
    def __init__(self, chat_model: Any, name: str) -> None:
        self.name = name
        self._structured = chat_model.with_structured_output(JudgeVerdict)

    async def judge(self, system: str, user: str) -> JudgeVerdict:
        result = await self._structured.ainvoke([("system", system), ("human", user)])
        return result if isinstance(result, JudgeVerdict) else JudgeVerdict.model_validate(result)


def build_judge(settings: JudgeSettings) -> JudgeBackend | None:
    if settings.provider == "none":
        return None
    if not settings.model:
        raise ValueError("JUDGE_MODEL is required when JUDGE_PROVIDER is set")
    key = settings.api_key.get_secret_value() if settings.api_key else None
    common: dict[str, Any] = {
        "max_tokens": settings.max_tokens,
        "timeout": settings.timeout_seconds,
    }
    chat: Any
    if settings.provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        if not key:
            raise ValueError("JUDGE_API_KEY is required for the anthropic judge")
        chat = ChatAnthropic(model_name=settings.model, api_key=SecretStr(key), **common)
    else:
        from langchain_openai import ChatOpenAI

        chat = ChatOpenAI(
            model=settings.model,
            api_key=SecretStr(key or "not-needed"),
            base_url=settings.base_url,
            **common,
        )
    return LangChainJudge(chat, settings.model)


def render_user(report: Report) -> str:
    facts = "\n".join(f"[{f.id}] {f.statement}" for f in report.facts)
    claims = [report.headline, *report.findings]
    lines = [
        f"{i}. {c.text}  (cites: {', '.join(c.fact_ids) or 'nothing'})"
        for i, c in enumerate(claims)
    ]
    return f"FACTS\n{facts}\n\nCLAIMS\n" + "\n".join(lines)


async def judge_report(
    report: Report, backend: JudgeBackend, cache: JsonCache | None = None
) -> list[ClaimVerdict]:
    user = render_user(report)
    key = cache_key(backend.name, SYSTEM, user)
    if cache is not None:
        hit = cache.get(key)
        if hit is not None:
            return JudgeVerdict.model_validate(hit["verdict"]).claims
    verdict = await backend.judge(SYSTEM, user)
    if cache is not None:
        cache.put(key, {"model": backend.name, "verdict": verdict.model_dump(mode="json")})
    return verdict.claims


def agreement(hand: Sequence[bool], judged: Sequence[bool]) -> dict[str, Any]:
    """Judge vs hand labels: raw agreement, kappa, and the costly error (judge says supported)."""
    if len(hand) != len(judged):
        raise ValueError("hand and judged lists must be the same length")
    pairs = list(zip(hand, judged, strict=True))
    same = Rate(sum(h == j for h, j in pairs), len(pairs))
    false_ok = sum(1 for h, j in pairs if (not h) and j)
    return {
        "n": len(pairs),
        "agreement": same.to_dict(),
        "kappa": cohens_kappa(
            ["y" if h else "n" for h in hand], ["y" if j else "n" for j in judged]
        ),
        "judge_approved_unsupported_claim": false_ok,
    }


def load_hand_labels(path: Path) -> dict[str, bool]:
    """JSONL rows: {"key": "<company>:<claim index>", "supported": true|false}."""
    out: dict[str, bool] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            out[str(row["key"])] = bool(row["supported"])
    return out
