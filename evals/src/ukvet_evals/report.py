"""Render results.json as a readable markdown report (and the headline table)."""

from typing import Any

from ukvet_evals.constants import TARGETS


def _fmt(rate: dict[str, Any] | None) -> str:
    if not rate or rate.get("rate") is None:
        return "n/a"
    ci = rate.get("ci95")
    ci_s = f" [{ci[0]:.1%}, {ci[1]:.1%}]" if ci else ""
    return f"{rate['rate']:.1%}{ci_s}"


def _met(value: float | None, target: float, lower_is_better: bool = False) -> str:
    if value is None:
        return "not measured"
    ok = value <= target if lower_is_better else value >= target
    return "met" if ok else "**MISSED**"


def headline_rows(res: dict[str, Any]) -> list[tuple[str, str, str, str, str]]:
    m1 = res["m1"]["overall"]["fields"]
    cats = res["m1"]["by_question"]
    worst = min(
        ((q, v["fields"]["rate"]) for q, v in cats.items() if v["fields"]["rate"] is not None),
        key=lambda kv: kv[1],
        default=None,
    )
    nar = res["narrative"]
    m2 = nar["m2_unsupported"]
    m4 = nar["m4_mechanical_valid"]
    m5 = res["m5"]["recall"]
    m3 = res["m3"]
    llm = nar["llm_reports"]
    rows = [
        (
            "M1 accuracy (fields)",
            f">= {TARGETS['m1_overall']:.0%}",
            _fmt(m1),
            f"{m1['k']}/{m1['n']} fields",
            _met(m1["rate"], TARGETS["m1_overall"]),
        ),
        (
            "M1 worst question",
            f">= {TARGETS['m1_category']:.0%} each",
            f"{worst[0]} {worst[1]:.1%}" if worst else "n/a",
            "see table",
            _met(worst[1] if worst else None, TARGETS["m1_category"]),
        ),
        (
            "M2 unsupported claims",
            f"< {TARGETS['m2_max']:.0%}",
            _fmt(m2) if llm else "n/a (no LLM reports)",
            f"{m2['k']}/{m2['n']} claims, {llm} LLM reports",
            _met(m2["rate"], TARGETS["m2_max"], True) if llm else "not measured",
        ),
        (
            "M3 abstention",
            f">= {TARGETS['m3']:.0%}",
            _fmt(m3),
            f"{m3['k']}/{m3['n']} cases",
            _met(m3["rate"], TARGETS["m3"]),
        ),
        (
            "M4 citation validity (mechanical)",
            "100%",
            _fmt(m4),
            f"{m4['k']}/{m4['n']} claims",
            _met(m4["rate"], TARGETS["m4"]),
        ),
        (
            "M5 red-flag recall",
            f">= {TARGETS['m5']:.0%}",
            _fmt(m5),
            f"{m5['k']}/{m5['n']} expected flags",
            _met(m5["rate"], TARGETS["m5"]),
        ),
    ]
    return rows


def render_markdown(res: dict[str, Any]) -> str:
    meta = res["meta"]
    out: list[str] = []
    out.append(
        f"# ukvet evaluation: {meta['dataset']} {meta['dataset_version']} ({meta['split']})\n"
    )
    if meta.get("synthetic"):
        out.append(
            "> **Synthetic demo data.** These numbers prove the harness works; they say nothing about ukvet's accuracy.\n"
        )
    llm = meta["llm"]
    out.append(
        f"- git `{meta['git_commit']}` · tool {meta['tool_version']} · {meta['created_at']}\n"
        f"- {meta['companies']} companies, {meta['items']} items · narrative: `{llm['mode']}`"
        f"{' / ' + llm['model'] if llm.get('model') else ''}"
        f"{' · judge ' + meta['judge'] if meta.get('judge') else ''}\n"
    )
    out.append("## Headline\n")
    out.append(
        "| Metric | Target | Result (95% interval) | Size | Verdict |\n|---|---|---|---|---|"
    )
    for name, target, result, size, verdict in headline_rows(res):
        out.append(f"| {name} | {target} | {result} | {size} | {verdict} |")

    out.append("\n## M1 by question\n")
    out.append("| Question | Fields correct | Items fully correct |\n|---|---|---|")
    for q, v in res["m1"]["by_question"].items():
        out.append(
            f"| {q} | {_fmt(v['fields'])} ({v['fields']['k']}/{v['fields']['n']}) | "
            f"{v['items']['k']}/{v['items']['n']} |"
        )
    fails = res["m1"]["failures"]
    out.append(f"\n### M1 failures ({len(fails)})\n")
    for f in fails[:40]:
        out.append(f"- `{f['item']}` {f['field']}: expected `{f['expected']}`, got `{f['actual']}`")
    if not fails:
        out.append("None.")

    m3 = res["m3"]
    bad = [c for c in m3["cases"] if not c["passed"]]
    out.append(f"\n## M3 abstention: {m3['k']}/{m3['n']} passed\n")
    for c in bad:
        out.append(f"- `{c['id']}`: " + "; ".join(c["failed_checks"]))
    if not bad:
        out.append("All cases passed.")

    m5 = res["m5"]
    out.append(
        f"\n## M5 red flags: {m5['labelled_companies']} labelled, {m5['unlabelled_companies']} unlabelled "
        f"(skipped)\n\nPrecision {_fmt(m5['precision'])} · severity agreement {_fmt(m5['severity_agreement'])}\n"
    )
    for m in m5["missed"]:
        out.append(f"- MISSED `{m['flag']}` for {m['company']} ({', '.join(m['tags'])})")
    for u in m5["unexpected"]:
        out.append(
            f"- UNEXPECTED `{u['flag']}` ({u['severity']}) for {u['company']} ({', '.join(u['tags'])})"
        )
    for s in m5["severity_mismatch"]:
        out.append(
            f"- SEVERITY {s['flag']} for {s['company']}: expected {s['expected']}, got {s['got']}"
        )
    sl = m5["second_labeller"]
    if sl["pairs"]:
        out.append(f"\nSecond labeller: agreement {_fmt(sl['agreement'])}, kappa {sl['kappa']}")

    nar = res["narrative"]
    out.append("\n## Narrative (M2, M4)\n")
    out.append(
        f"{nar['reports']} reports, {nar['llm_reports']} written by an LLM, {nar['claims']} claims. "
        f"Writer needed the checker on {_fmt(nar['writer_needed_checker'])} of first-attempt claims; "
        f"{nar['llm_errors']} LLM errors, {nar['retries']} retries."
    )
    if nar["m4_semantic_supported"]["n"]:
        out.append(
            f"\nJudge says cited facts support {_fmt(nar['m4_semantic_supported'])} of judged claims "
            "(a model's opinion; see calibration)."
        )
    for ex in nar["examples"][:15]:
        out.append(
            f"- {ex['company']} [{ex['source']}]: {'; '.join(ex['errors'])} — “{ex['claim']}”"
        )

    guard = res.get("guardrails")
    if guard is not None:
        bad = guard["violations"]
        out.append(
            f"\n## Output guardrails: {guard['reports'] - len({v['company'] for v in bad})}/{guard['reports']} reports clean\n"
        )
        out += [f"- {v['company']}: {v['problem']}" for v in bad[:30]]
        if not bad:
            out.append("No violations (disclaimer, opinion label, no advice or links, no markup).")

    perf = res["perf"]
    out.append(
        f"\n## Timing (replay, no network)\n\nmedian {perf['median_ms']} ms, worst {perf['worst_ms']} ms over {perf['reports']} reports. {perf['note']}."
    )
    return "\n".join(out) + "\n"
