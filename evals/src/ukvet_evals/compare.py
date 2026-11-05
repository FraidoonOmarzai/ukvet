"""Phase 5: put two (or more) models side by side, honestly.

Input: a small manifest (see evals/comparison.example.json) that points at, per model:
  * the `ukvet-evals run` results.json            (M1, M2, M4, fallback share)  - required
  * the `scripts/phase4_metrics.py` metrics.json  (M7 latency, M8 cost)         - optional
  * the `ukvet-evals injection` injection.json    (M6)                          - optional
plus, for a self-hosted model, the GPU price and hours so cost per report can be worked out.

Output: `docs/results.md` (a table plus the facts a reader needs to trust it) and a JSON copy.

Honesty rules enforced here (see docs/PHASE-5-README.md, Part 2):
* the runs must use the same dataset version and split, or the comparison is refused;
* a template run (`--llm none`) is not a model and is refused;
* a different git commit, a non-test split, a small latency sample, or a high template-fallback
  share is printed as a warning right above the table, never hidden;
* nothing is invented: a missing input shows as "n/a".

The analysis, trade-off and recommendation sections are left for a human to write.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MIN_LIVE_RUNS = 20
HIGH_FALLBACK = 0.10  # more than 10% template reports: scores mostly describe the template
KINDS = ("api", "self-hosted", "hosted-open")
QUESTIONS = tuple(f"Q{i}" for i in range(1, 10))


class ComparisonError(ValueError):
    """The inputs cannot be compared fairly."""


@dataclass
class Entry:
    label: str
    kind: str
    model_id: str
    results: Path
    live: Path | None = None
    injection: Path | None = None
    hardware: str = ""
    gpu_gbp_per_hour: float | None = None
    gpu_hours: float | None = None
    notes: str = ""


def load_manifest(path: Path, root: Path) -> tuple[str, list[Entry]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    entries: list[Entry] = []
    for m in raw.get("models", []):
        kind = m.get("kind", "api")
        if kind not in KINDS:
            raise ComparisonError(f"model '{m.get('label')}': kind must be one of {KINDS}")

        def p(key: str, m: dict[str, Any] = m) -> Path | None:
            return root / m[key] if m.get(key) else None

        results = p("results")
        if results is None:
            raise ComparisonError(f"model '{m.get('label')}': 'results' is required")
        entries.append(
            Entry(
                label=m["label"],
                kind=kind,
                model_id=m["model_id"],
                results=results,
                live=p("live"),
                injection=p("injection"),
                hardware=m.get("hardware", ""),
                gpu_gbp_per_hour=m.get("gpu_gbp_per_hour"),
                gpu_hours=m.get("gpu_hours"),
                notes=m.get("notes", ""),
            )
        )
    return raw.get("title", "Model comparison"), entries


def _read(path: Path | None, what: str, label: str) -> dict[str, Any] | None:
    if path is None:
        return None
    if not path.exists():
        raise ComparisonError(f"model '{label}': {what} file not found: {path}")
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


# ---- cost of a self-hosted model --------------------------------------------------------------


def selfhost_cost(
    gpu_gbp_per_hour: float, gpu_hours: float, reports: int, busy_ms: float | None
) -> dict[str, Any]:
    """Cost per report = GPU price x hours the server was up / reports served in that time.

    `utilisation` is the share of those hours the GPU spent working on a report. When reports are
    generated one at a time it is low, so the figure is a worst case for self-hosting, not the
    best case. Say so next to the number.
    """
    if reports <= 0 or gpu_hours <= 0 or gpu_gbp_per_hour < 0:
        raise ComparisonError("selfhost cost needs reports > 0, gpu_hours > 0 and a price >= 0")
    total = gpu_gbp_per_hour * gpu_hours
    util = None if busy_ms is None else min(1.0, busy_ms / (gpu_hours * 3_600_000))
    return {
        "gbp_per_report": total / reports,
        "total_gbp": total,
        "reports": reports,
        "gpu_hours": gpu_hours,
        "utilisation": util,
    }


# ---- one model -> one flat record -------------------------------------------------------------


def summarise(entry: Entry) -> dict[str, Any]:
    res = _read(entry.results, "results", entry.label)
    assert res is not None
    meta, narrative = res["meta"], res["narrative"]
    llm = meta.get("llm", {})
    if llm.get("mode") in (None, "none"):
        raise ComparisonError(
            f"model '{entry.label}': results were made with --llm none (template only). "
            "Re-run with --llm replay or record."
        )
    reports = narrative["reports"]
    llm_reports = narrative["llm_reports"]
    live = _read(entry.live, "live metrics", entry.label)
    inj = _read(entry.injection, "injection", entry.label)

    out: dict[str, Any] = {
        "label": entry.label,
        "kind": entry.kind,
        "model_id": entry.model_id,
        "hardware": entry.hardware,
        "notes": entry.notes,
        "run": {
            "dataset": meta["dataset"],
            "dataset_version": meta["dataset_version"],
            "split": meta["split"],
            "git_commit": meta["git_commit"],
            "created_at": meta["created_at"],
            "llm_mode": llm.get("mode"),
            "llm_model": llm.get("model"),
            "companies": meta["companies"],
        },
        "m1": res["m1"]["overall"]["fields"],
        "m1_by_question": {q: v["fields"] for q, v in res["m1"]["by_question"].items()},
        "m2": narrative["m2_unsupported"],
        "m4": narrative["m4_mechanical_valid"],
        "llm_written": {"reports": reports, "llm_reports": llm_reports},
        "llm_share": None if reports == 0 else llm_reports / reports,
        "template_fallback_share": None if reports == 0 else 1 - llm_reports / reports,
        "llm_errors": narrative.get("llm_errors", 0),
        "retries": narrative.get("retries", 0),
        "claims": narrative.get("claims", 0),
        "m3": res.get("m3", {}).get("rate"),
        "m5_recall": res.get("m5", {}).get("recall", {}).get("rate"),
        "guardrail_violations": res.get("guardrails", {}).get("violations"),
        "m6": None,
        "m7": None,
        "m8": None,
        "m9": None,
        "live_reports": 0,
    }
    if inj is not None:
        out["m6"] = {
            "rate": inj["m6"],
            "reached_prompt": inj["reached_prompt"],
            "runs": inj["runs"],
            "narrative_source": inj.get("narrative_source"),
        }
    if live is not None:
        n = live["reports"]
        out["live_reports"] = n
        out["m7"] = {**live["m7_latency_ms"], "reports": n}
        out["m9"] = live["m9_tool_calls"]
        out["live_llm_reports"] = live.get("llm_reports")
        if entry.kind == "self-hosted":
            if entry.gpu_gbp_per_hour is None or entry.gpu_hours is None:
                raise ComparisonError(
                    f"model '{entry.label}': a self-hosted model needs "
                    "gpu_gbp_per_hour and gpu_hours"
                )
            out["m8"] = {
                "method": "gpu price x hours up / reports",
                **selfhost_cost(
                    entry.gpu_gbp_per_hour, entry.gpu_hours, n, live.get("busy_ms_total")
                ),
            }
        else:
            out["m8"] = {"method": "tokens x configured price", **live["m8_cost_gbp"]}
    return out


# ---- fairness checks --------------------------------------------------------------------------


def check(models: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    """(errors, warnings). Errors refuse the comparison; warnings are printed with the table."""
    errors: list[str] = []
    warnings: list[str] = []
    if len(models) < 2:
        errors.append("a comparison needs at least two models")
        return errors, warnings

    def values(key: str) -> set[Any]:
        return {m["run"][key] for m in models}

    if len(values("dataset_version")) > 1 or len(values("dataset")) > 1:
        errors.append("the runs use different datasets or dataset versions")
    if len(values("split")) > 1:
        errors.append("the runs use different splits")
    if len(values("git_commit")) > 1:
        warnings.append(
            "the runs were made at different git commits "
            f"({', '.join(sorted(map(str, values('git_commit'))))}): the code or prompt may differ"
        )
    if "test" not in values("split"):
        warnings.append("not the test split: these are development numbers, not the final ones")
    labels = [m["label"] for m in models]
    if len(set(labels)) != len(labels):
        errors.append("two models share a label")

    for m in models:
        who = m["label"]
        run_model = m["run"]["llm_model"]
        if run_model and run_model != m["model_id"]:
            errors.append(
                f"{who}: manifest says model '{m['model_id']}' but the run used '{run_model}'"
            )
        share = m["template_fallback_share"]
        if share is not None and share > HIGH_FALLBACK:
            warnings.append(
                f"{who}: {share:.0%} of reports fell back to the template, so M1, M2 and M4 "
                "partly describe the template, not the model"
            )
        if m["live_reports"] == 0:
            warnings.append(f"{who}: no live latency/cost run (M7, M8 are n/a)")
        elif m["live_reports"] < MIN_LIVE_RUNS:
            warnings.append(
                f"{who}: only {m['live_reports']} live reports; the p95 latency is weak "
                f"(use {MIN_LIVE_RUNS}+)"
            )
        if m["m6"] is None:
            warnings.append(f"{who}: no injection run (M6 is n/a)")
        elif m["m6"]["reached_prompt"] == 0:
            warnings.append(f"{who}: no injection payload reached the prompt, M6 says nothing")
    return errors, warnings


# ---- rendering --------------------------------------------------------------------------------


def _rate(r: dict[str, Any] | None) -> str:
    if not r or r.get("rate") is None:
        return "n/a"
    ci = r.get("ci95")
    ci_s = f" [{ci[0]:.1%}, {ci[1]:.1%}]" if ci else ""
    return f"{r['rate']:.1%}{ci_s} ({r['k']}/{r['n']})"


def _pct(v: float | None) -> str:
    return "n/a" if v is None else f"{v:.0%}"


def _seconds(ms: float | None) -> str:
    return "n/a" if ms is None else f"{ms / 1000:.1f} s"


def _m7(m: dict[str, Any]) -> str:
    v = m["m7"]
    if not v or v.get("p95") is None:
        return "n/a"
    weak = " (weak)" if v.get("weak") else ""
    return f"{_seconds(v['p95'])}{weak}, p50 {_seconds(v['p50'])}, n={v['reports']}"


def _m8(m: dict[str, Any]) -> str:
    v = m["m8"]
    if not v:
        return "n/a"
    if "gbp_per_report" in v:
        util = v.get("utilisation")
        u = "" if util is None else f", GPU busy {util:.0%} of the time"
        return f"£{v['gbp_per_report']:.4f} (self-hosted{u})"
    if v.get("mean") is None:
        return "n/a (no token prices set)"
    return f"£{v['mean']:.5f} (API tokens)"


def render(title: str, models: list[dict[str, Any]], warnings: list[str]) -> str:
    first = models[0]["run"]
    out = [
        f"# {title}\n",
        f"Dataset `{first['dataset']}` {first['dataset_version']}, split `{first['split']}`, "
        f"git `{first['git_commit']}`. Intervals are 95% Wilson.\n",
    ]
    if warnings:
        out.append("**Read these before the table:**\n")
        out += [f"- {w}" for w in warnings]
        out.append("")
    out += [
        "## Results\n",
        "| Model | M1 accuracy | M2 unsupported | M4 citations valid | LLM-written | "
        "M6 injection | M7 p95 latency | M8 cost/report |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for m in models:
        m6 = _rate(m["m6"]["rate"]) if m["m6"] else "n/a"
        out.append(
            f"| {m['label']} | {_rate(m['m1'])} | {_rate(m['m2'])} | {_rate(m['m4'])} | "
            f"{_pct(m['llm_share'])} ({m['llm_written']['llm_reports']}/"
            f"{m['llm_written']['reports']}) | "
            f"{m6} | {_m7(m)} | {_m8(m)} |"
        )
    out += ["", "Targets: M1 >= 90%, M2 < 2%, M4 = 100%, M6 >= 95%, M7 p95 < 30 s, M8 < £0.05.\n"]

    out += [
        "## M1 accuracy by question (fields)\n",
        "| Question | " + " | ".join(m["label"] for m in models) + " |",
        "|---|" + "---|" * len(models),
    ]
    for q in QUESTIONS:
        cells = [_rate(m["m1_by_question"].get(q)) for m in models]
        out.append(f"| {q} | " + " | ".join(cells) + " |")

    out += ["", "## How each model ran\n"]
    for m in models:
        hw = f", {m['hardware']}" if m["hardware"] else ""
        out.append(f"### {m['label']}\n")
        out.append(f"- `{m['model_id']}` ({m['kind']}{hw})")
        out.append(
            f"- template fallback: {_pct(m['template_fallback_share'])}; "
            f"LLM errors {m['llm_errors']}; checker retries {m['retries']}; "
            f"{m['claims']} claims checked"
        )
        out.append(
            f"- guardrail violations: {m['guardrail_violations']}; "
            f"M9 tool calls per report: "
            + ("n/a" if not m["m9"] else f"mean {m['m9']['mean']:.1f}, max {m['m9']['max']}")
        )
        if m["notes"]:
            out.append(f"- notes: {m['notes']}")
        out.append("")

    out += [
        "## Failure analysis\n",
        "_Write by hand after reading 5 to 10 failing or fallback cases per model: schema errors, "
        "timeouts, dropped claims, wrong facts, injection._\n",
        "## Trade-offs\n",
        "_Accuracy vs cost vs latency vs control. Which model for which use._\n",
        "## Limitations\n",
        "- One open-weight model, one run each; no repeat-run variance measured.",
        "- M1, M2 and M4 are rule-based on anonymised snapshots; fairness of wording (risk R15) "
        "is not judged.",
        "- M7 and M8 are from live runs on one network and, for self-hosted, one GPU; they do not "
        "transfer to other hardware. Self-hosted cost assumes the GPU was billed for the whole "
        "time it was up.",
        "- Template fallbacks count in M1/M2/M4 (see the LLM-written column).",
        "",
        "## Recommendation\n",
        "_One paragraph, supported by the table above._\n",
    ]
    return "\n".join(out) + "\n"


def build(manifest: Path, root: Path) -> tuple[str, dict[str, Any]]:
    title, entries = load_manifest(manifest, root)
    models = [summarise(e) for e in entries]
    errors, warnings = check(models)
    if errors:
        raise ComparisonError("; ".join(errors))
    return render(title, models, warnings), {
        "title": title,
        "models": models,
        "warnings": warnings,
    }
