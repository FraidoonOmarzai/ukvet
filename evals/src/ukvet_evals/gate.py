"""The CI regression gate (M12): compare a results.json with the committed baseline.

The gate is about REGRESSIONS, not about hitting targets (targets are reported in the results
table). The data is frozen and the pipeline is deterministic in template mode, so any field that
was correct in the baseline and is wrong now is a real change, not noise.
"""

from dataclasses import dataclass, field
from typing import Any

from ukvet_evals.constants import TARGETS

TOL_M1_OVERALL = 0.01
TOL_M3 = 0.02
TOL_M5 = 0.02
TOL_M2 = 0.005


@dataclass
class GateResult:
    passed: bool
    problems: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    table: list[tuple[str, str, str, str]] = field(default_factory=list)

    def markdown(self) -> str:
        head = "## ukvet eval gate: " + ("PASS" if self.passed else "FAIL")
        rows = ["| Metric | Baseline | Now | Change |", "|---|---|---|---|"]
        rows += [f"| {a} | {b} | {c} | {d} |" for a, b, c, d in self.table]
        parts = [head, "", *rows]
        if self.problems:
            parts += ["", "**Regressions**", *[f"- {p}" for p in self.problems]]
        if self.notes:
            parts += ["", *[f"- {n}" for n in self.notes]]
        return "\n".join(parts) + "\n"


def _rate(d: dict[str, Any]) -> float | None:
    return d.get("rate") if d else None


def _pct(v: float | None) -> str:
    return "n/a" if v is None else f"{v:.1%}"


def _row(name: str, base: float | None, now: float | None) -> tuple[str, str, str, str]:
    delta = "" if base is None or now is None else f"{(now - base) * 100:+.1f} pp"
    return (name, _pct(base), _pct(now), delta)


def compare(baseline: dict[str, Any], now: dict[str, Any]) -> GateResult:
    g = GateResult(passed=True)
    bm, nm = baseline["meta"], now["meta"]
    for key in ("dataset", "dataset_version", "split"):
        if bm.get(key) != nm.get(key):
            g.problems.append(
                f"baseline was made for {key}={bm.get(key)!r} but this run has {nm.get(key)!r}: "
                "regenerate the baseline in a PR that explains why"
            )
    if g.problems:
        g.passed = False
        return g

    b1, n1 = baseline["m1"], now["m1"]
    bo, no = _rate(b1["overall"]["fields"]), _rate(n1["overall"]["fields"])
    g.table.append(_row("M1 accuracy (fields)", bo, no))
    if bo is not None and no is not None and no < bo - TOL_M1_OVERALL:
        g.problems.append(
            f"M1 overall fell from {_pct(bo)} to {_pct(no)} (allowed drop {TOL_M1_OVERALL:.0%})"
        )
    floor = TARGETS["m1_category"]
    for q, nv in n1["by_question"].items():
        nq = _rate(nv["fields"])
        bq = _rate(b1["by_question"].get(q, {}).get("fields", {}))
        g.table.append(_row(f"M1 {q}", bq, nq))
        if bq is not None and nq is not None and bq >= floor > nq:
            g.problems.append(f"M1 {q} fell below the {floor:.0%} floor ({_pct(bq)} -> {_pct(nq)})")
    base_fail = {(f["item"], f["field"]) for f in b1["failures"]}
    new_fail = [f for f in n1["failures"] if (f["item"], f["field"]) not in base_fail]
    for f in new_fail[:20]:
        g.problems.append(
            f"new field failure {f['item']} {f['field']}: "
            f"expected {f['expected']!r}, got {f['actual']!r}"
        )

    b3, n3 = baseline["m3"], now["m3"]
    g.table.append(_row("M3 abstention", _rate(b3), _rate(n3)))
    if _rate(b3) is not None and _rate(n3) is not None and _rate(n3) < _rate(b3) - TOL_M3:  # type: ignore[operator]
        g.problems.append(f"M3 fell from {_pct(_rate(b3))} to {_pct(_rate(n3))}")
    base_ok = {c["id"] for c in b3["cases"] if c["passed"]}
    for c in n3["cases"]:
        if c["id"] in base_ok and not c["passed"]:
            g.problems.append(
                f"abstention case {c['id']} used to pass: " + "; ".join(c["failed_checks"][:3])
            )

    b5, n5 = baseline["m5"]["recall"], now["m5"]["recall"]
    g.table.append(_row("M5 red-flag recall", _rate(b5), _rate(n5)))
    if _rate(b5) is not None and _rate(n5) is not None and _rate(n5) < _rate(b5) - TOL_M5:  # type: ignore[operator]
        g.problems.append(f"M5 recall fell from {_pct(_rate(b5))} to {_pct(_rate(n5))}")
    g.table.append(
        _row("M5 precision", _rate(baseline["m5"]["precision"]), _rate(now["m5"]["precision"]))
    )

    bn, nn = baseline["narrative"], now["narrative"]
    m4 = _rate(nn["m4_mechanical_valid"])
    g.table.append(_row("M4 mechanical", _rate(bn["m4_mechanical_valid"]), m4))
    if m4 is not None and m4 < TARGETS["m4"]:
        g.problems.append(f"M4 mechanical citation validity is {_pct(m4)} (must be 100%)")
    if nn["llm_reports"] and bn["llm_reports"]:
        b2, n2 = _rate(bn["m2_unsupported"]), _rate(nn["m2_unsupported"])
        g.table.append(_row("M2 unsupported", b2, n2))
        if b2 is not None and n2 is not None and n2 > b2 + TOL_M2:
            g.problems.append(f"M2 rose from {_pct(b2)} to {_pct(n2)}")
    elif nn["llm_reports"] and not bn["llm_reports"]:
        g.notes.append("baseline has no LLM reports: M2 not compared")

    gb = len(baseline.get("guardrails", {}).get("violations", []))
    gn = len(now.get("guardrails", {}).get("violations", []))
    g.table.append(("Output guardrail violations", str(gb), str(gn), f"{gn - gb:+d}"))
    if gn > gb:
        g.problems.append(f"output guardrail violations rose from {gb} to {gn} (see results.md)")

    g.passed = not g.problems
    return g
