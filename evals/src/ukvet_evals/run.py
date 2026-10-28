"""The evaluation runner: replay companies, score M1/M2/M3/M4/M5, return a results dict."""

import statistics
import subprocess  # noqa: S404
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from ukvet_agent.guardrails import check_report
from ukvet_agent.llm import LlmSettings, NarrativeWriter, build_writer
from ukvet_agent.mcp_client import ToolClient
from ukvet_agent.schemas import Report

from ukvet_evals import __version__
from ukvet_evals.faults import FaultyTools
from ukvet_evals.items import build_items, golden_conflicts
from ukvet_evals.judge import JudgeBackend, judge_report
from ukvet_evals.llmcache import CachingWriter, JsonCache
from ukvet_evals.schema import Dataset, FaultSpec, Item
from ukvet_evals.scorers.abstention import CaseResult, score_case
from ukvet_evals.scorers.flags import FlagScore, score_flags
from ukvet_evals.scorers.narrative import NarrativeScore, score_narrative
from ukvet_evals.scorers.retrieval import RetrievalScore, score_report
from ukvet_evals.snapshot import ReplayHarness, Snapshot
from ukvet_evals.stats import Rate

LlmMode = Literal["none", "replay", "record", "live"]


class ReplayMissError(RuntimeError):
    """Recorded LLM answers are missing: re-record with `--llm record` (needs an API key)."""


class DatasetDriftError(RuntimeError):
    """items.jsonl no longer matches snapshots + oracle + golden."""


@dataclass
class RunOptions:
    root: Path
    dataset: str
    split: str = "dev"
    llm: LlmMode = "none"
    model: str | None = None
    judge: JudgeBackend | None = None
    skip: set[str] = field(default_factory=set)


def git_commit(root: Path) -> str:
    try:
        out = subprocess.run(  # noqa: S603
            ["git", "rev-parse", "--short", "HEAD"],  # noqa: S607
            cwd=root, capture_output=True, text=True, timeout=10, check=False,
        )  # fmt: skip
        return out.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def _writer(options: RunOptions) -> CachingWriter | NarrativeWriter | None:
    if options.llm == "none":
        return None
    settings = LlmSettings()
    if options.llm == "live":
        return build_writer(settings)
    model = options.model or settings.model
    if not model:
        raise ValueError("set --model (or LLM_MODEL) so recorded answers can be found")
    inner = build_writer(settings) if options.llm == "record" else None
    return CachingWriter(options.root / "evals" / "llm_cache", options.llm, model, inner)


def _faulty(faults: list[FaultSpec]) -> Callable[[ToolClient], ToolClient]:
    def wrap(tools: ToolClient) -> ToolClient:
        return FaultyTools(tools, faults)

    return wrap


def check_items_fresh(ds: Dataset, snaps: dict[str, Snapshot]) -> list[Item]:
    """The frozen items.jsonl must equal what the oracle + golden produce now."""
    fresh = build_items(ds.companies, snaps, ds.golden)
    if [i.model_dump(mode="json") for i in fresh] != [i.model_dump(mode="json") for i in ds.items]:
        raise DatasetDriftError(
            "items.jsonl is out of date (snapshots, oracle or golden changed). "
            "Review the diff and run `ukvet-evals build-items`."
        )
    return ds.items


async def evaluate(options: RunOptions) -> dict[str, Any]:
    ds = Dataset(options.root / "evals", options.dataset)
    companies = ds.select(options.split)
    snaps = {
        c.company_number: Snapshot.load(ds.snapshot_dir / f"{c.company_number}.json")
        for c in ds.companies
    }
    conflicts = golden_conflicts(ds.companies, snaps, ds.golden)
    if conflicts:
        raise DatasetDriftError(
            "golden values disagree with the oracle:\n" + "\n".join(str(c) for c in conflicts)
        )
    items = check_items_fresh(ds, snaps)

    writer = _writer(options)
    retrieval, narrative, flags = RetrievalScore(), NarrativeScore(), FlagScore()
    reports: dict[str, Report] = {}
    totals_ms: list[int] = []
    harness = ReplayHarness({c.company_number: snaps[c.company_number] for c in companies})
    judge_rows: list[dict[str, Any]] = []
    cases: list[CaseResult] = []
    guardrail_problems: list[dict[str, str]] = []

    async with harness.open():
        for c in companies:
            report = await harness.run(c.company_number, writer=writer)
            reports[c.id] = report
            totals_ms.append(report.timings_ms.get("total", 0))
            score_report(report, [i for i in items if i.company == c.id], retrieval)
            score_narrative(report, narrative, c.id)
            guardrail_problems += [{"company": c.id, "problem": p} for p in check_report(report)]
            label = next((f for f in ds.flags if f.company == c.id), None)
            if label is not None:
                score_flags(report, label, c.tags, flags)
            if options.judge is not None and report.narrative_source == "llm":
                cache = JsonCache(
                    options.root / "evals" / "llm_cache", f"judge-{options.judge.name}"
                )
                for i, v in enumerate(await judge_report(report, options.judge, cache)):
                    judge_rows.append(
                        {"key": f"{c.id}:{i}", "supported": v.supported, "reason": v.reason}
                    )
                    narrative.semantic_judged += 1
                    narrative.semantic_unsupported += int(not v.supported)

        ids = {c.id for c in companies}
        for case in ds.abstention:
            if case.company not in ids:
                continue
            number = ds.company(case.company).company_number
            faulty = await harness.run(number, writer=None, wrap_tools=_faulty(case.faults))
            cases.append(score_case(case, reports[case.company], faulty))

    if isinstance(writer, CachingWriter) and writer.misses:
        raise ReplayMissError(
            f"{len(writer.misses)} recorded LLM answer(s) missing for model '{writer.model_name}'. "
            "Facts or prompts changed: run `ukvet-evals run --llm record` with your API key."
        )

    m3 = Rate(sum(r.passed for r in cases), len(cases))
    llm_info: dict[str, Any] = {"mode": options.llm, "model": getattr(writer, "model_name", None)}
    if isinstance(writer, CachingWriter):
        llm_info |= {"cache_hits": writer.hits, "live_calls": writer.live_calls}

    return {
        "meta": {
            "tool_version": __version__,
            "dataset": ds.name,
            "dataset_version": ds.manifest.version,
            "split": options.split,
            "git_commit": git_commit(options.root),
            "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "companies": len(companies),
            "items": len([i for i in items if i.company in {c.id for c in companies}]),
            "synthetic": ds.manifest.synthetic,
            "llm": llm_info,
            "judge": options.judge.name if options.judge else None,
        },
        "m1": retrieval.to_dict(),
        "m3": {
            **m3.to_dict(),
            "cases": [
                {"id": r.case, "passed": r.passed, "failed_checks": r.failed_checks, **r.detail}
                for r in cases
            ],
        },
        "m5": flags.to_dict(),
        "narrative": narrative.to_dict(),
        "judge_rows": judge_rows,
        "guardrails": {"reports": len(reports), "violations": guardrail_problems},
        "perf": {
            "reports": len(totals_ms),
            "median_ms": int(statistics.median(totals_ms)) if totals_ms else None,
            "worst_ms": max(totals_ms) if totals_ms else None,
            "note": "replay timings exclude network; see scripts/measure.py for live latency",
        },
    }
