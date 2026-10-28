"""Apply the Phase 4 edits to files that already exist in your repo.

Run from the repository root, AFTER copying the new files from the zip:

    uv run python apply_phase4.py            # stage 1: measure (tracing, usage, guardrail check, M6)
    uv run python apply_phase4.py --defences # stage 2: behaviour changes. ONLY after Step 9 (M6 "before")

Every edit is an exact-text replacement:
  * already applied  -> skipped ("ok, already there")
  * text not found   -> reported as ANCHOR NOT FOUND; nothing is guessed. The script keeps going,
                        prints the exact change to make by hand, and exits with code 1.
Commit your work first (`git status` clean), so `git diff` shows exactly what this changed.
"""

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

AGENT = "packages/ukvet-agent/src/ukvet_agent"
EV = "evals/src/ukvet_evals"


@dataclass
class Edit:
    file: str
    old: str
    new: str
    regex: bool = False
    note: str = ""


STAGE1: list[Edit] = [
    # ---- schemas: Usage on every report ------------------------------------------------------
    Edit(
        f"{AGENT}/schemas.py",
        "class Report(BaseModel):",
        '''class Usage(BaseModel):
    """Measured work for one report: tool calls, LLM calls, tokens, cost (M8, M9)."""

    tool_calls: int = 0
    tools: list[str] = Field(default_factory=list)
    llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_gbp: float | None = Field(
        default=None, description="None unless UKVET_PRICE_IN/OUT_GBP_PER_MTOK are set."
    )


class Report(BaseModel):''',
    ),
    Edit(
        f"{AGENT}/schemas.py",
        "    timings_ms: dict[str, int] = Field(default_factory=dict)\n    disclaimer",
        "    timings_ms: dict[str, int] = Field(default_factory=dict)\n"
        "    usage: Usage = Field(default_factory=Usage)\n    disclaimer",
    ),
    # ---- red flags: a named constant for the opinion label -----------------------------------
    Edit(
        f"{AGENT}/redflags.py",
        '''def assessment_text(level: RiskLevel, flags: list[RedFlag], gaps: list[Gap]) -> str:
    """Deterministic, honest, labelled as opinion."""
    prefix = (
        "ukvet's automated assessment (an opinion generated from rules, not a statement of fact): "
    )
''',
        '''ASSESSMENT_PREFIX = (
    "ukvet's automated assessment (an opinion generated from rules, not a statement of fact): "
)


def assessment_text(level: RiskLevel, flags: list[RedFlag], gaps: list[Gap]) -> str:
    """Deterministic, honest, labelled as opinion."""
    prefix = ASSESSMENT_PREFIX
''',
    ),
    # ---- graph: spans, tool counting, usage --------------------------------------------------
    Edit(
        f"{AGENT}/graph.py",
        "from ukvet_agent.settings import AgentSettings\n",
        "from ukvet_agent import usage as usage_mod\n"
        "from ukvet_agent.settings import AgentSettings\n"
        "from ukvet_agent.tracing import TracedTools, get_tracer\n",
    ),
    Edit(
        f"{AGENT}/graph.py",
        "        update = await fn(state)\n",
        "        with get_tracer().node(name):\n            update = await fn(state)\n",
    ),
    Edit(
        f"{AGENT}/graph.py",
        """def build_graph(deps: Deps) -> Any:
    async def plan(state: AgentState) -> dict[str, Any]:
        return await plan_node(dict(state), deps.tools)

    async def research(state: AgentState) -> dict[str, Any]:
        return await research_node(dict(state), deps.tools, deps.settings, deps.today())
""",
        """def build_graph(deps: Deps) -> Any:
    tools = TracedTools(deps.tools)  # counts every call (M9) and opens a span when tracing is on

    async def plan(state: AgentState) -> dict[str, Any]:
        return await plan_node(dict(state), tools)

    async def research(state: AgentState) -> dict[str, Any]:
        return await research_node(dict(state), tools, deps.settings, deps.today())
""",
    ),
    Edit(
        f"{AGENT}/graph.py",
        """    start = time.perf_counter()
    final: AgentState = await graph.ainvoke({"request": request})
    result = final["result"]
    if isinstance(result, Report):
        timings = dict(final.get("timings_ms") or {})
        timings["total"] = round((time.perf_counter() - start) * 1000)
        result.timings_ms = timings
    return result""",
        """    start = time.perf_counter()
    recorder, token = usage_mod.start()
    try:
        with get_tracer().report(request):
            final: AgentState = await graph.ainvoke({"request": request})
    finally:
        usage_mod.stop(token)
    result = final["result"]
    if isinstance(result, Report):
        timings = dict(final.get("timings_ms") or {})
        timings["total"] = round((time.perf_counter() - start) * 1000)
        result.timings_ms = timings
        result.usage = recorder.snapshot()
    return result""",
    ),
    # ---- llm: token counting and Langfuse callbacks ------------------------------------------
    Edit(
        f"{AGENT}/llm.py",
        "from ukvet_agent.schemas import Claim\n",
        "from ukvet_agent.schemas import Claim\n"
        "from ukvet_agent.tracing import get_tracer\n"
        "from ukvet_agent.usage import UsageCallback\n"
        "from ukvet_agent.usage import current as current_usage\n",
    ),
    Edit(
        f"{AGENT}/llm.py",
        '        result = await self._structured.ainvoke([("system", system), ("human", user)])\n',
        """        messages = [("system", system), ("human", user)]
        callbacks: list[Any] = list(get_tracer().llm_callbacks())
        recorder = current_usage()
        if recorder is not None:
            callbacks.append(UsageCallback(recorder))
        if callbacks:
            result = await self._structured.ainvoke(messages, config={"callbacks": callbacks})
        else:
            result = await self._structured.ainvoke(messages)
""",
    ),
    # ---- CLI and API: flush traces before exit -----------------------------------------------
    Edit(
        f"{AGENT}/cli.py",
        "from ukvet_agent.schemas import NeedsSelection, Report\n",
        "from ukvet_agent.schemas import NeedsSelection, Report\n"
        "from ukvet_agent.tracing import flush_tracer\n",
    ),
    Edit(
        f"{AGENT}/cli.py",
        "    sys.exit(code)\n\n\nif __name__",
        "    flush_tracer()\n    sys.exit(code)\n\n\nif __name__",
    ),
    Edit(
        f"{AGENT}/api.py",
        "from ukvet_agent.settings import AgentSettings\n",
        "from ukvet_agent.settings import AgentSettings\nfrom ukvet_agent.tracing import flush_tracer\n",
    ),
    Edit(
        f"{AGENT}/api.py",
        "            yield\n\n    app = FastAPI(",
        "            yield\n        flush_tracer()\n\n    app = FastAPI(",
    ),
    # ---- root pyproject: long data lines allowed in the new injection modules -----------------
    Edit(
        "pyproject.toml",
        '"evals/src/ukvet_evals/report.py" = ["E501"]',
        '"evals/src/ukvet_evals/report.py" = ["E501"]\n'
        '"evals/src/ukvet_evals/injection.py" = ["E501"]\n'
        '"evals/src/ukvet_evals/injection_cases.py" = ["E501"]',
    ),
    # ---- agent package: optional langfuse ----------------------------------------------------
    Edit(
        "packages/ukvet-agent/pyproject.toml",
        "[project.scripts]",
        '[project.optional-dependencies]\nobservability = ["langfuse>=5,<6"]\n\n[project.scripts]',
    ),
    Edit(
        "pyproject.toml",
        '    "pytest-asyncio>=1.4.0",\n',
        '    "pytest-asyncio>=1.4.0",\n    "langfuse>=5,<6",\n',
    ),
    # ---- config template ---------------------------------------------------------------------
    Edit(
        ".env.example",
        r"# --- Later phases ---.*\Z",
        """# --- Phase 4: tracing and cost (all optional) ---
# Langfuse tracing is OFF unless both keys are set. Install with: uv sync --extra observability
# LANGFUSE_PUBLIC_KEY=
# LANGFUSE_SECRET_KEY=
# LANGFUSE_HOST=https://cloud.langfuse.com
# redacted (default): no prompts, answers or names are sent, only timings, tokens and costs.
# full: send everything. Private project and short retention only (prompts contain names).
# UKVET_TRACE_CONTENT=redacted
# Token prices in GBP per million tokens, from your provider's price page. Needed for cost (M8).
# UKVET_PRICE_IN_GBP_PER_MTOK=
# UKVET_PRICE_OUT_GBP_PER_MTOK=
""",
        regex=True,
    ),
    # ---- evals: injection cases, CLI, guardrails in the run ----------------------------------
    Edit(
        f"{EV}/schema.py",
        """    kind: Literal["company_name", "officer_name", "charge_holder", "registry_text"]
    payload: str
    expect: str = Field(description="What must NOT happen (scored in Phase 4, M6).")""",
        """    kind: Literal["company_name", "officer_name", "psc_name", "charge_holder", "registry_text"]
    payload: str
    expect: str = Field(description="What must NOT happen (scored in Phase 4, M6).")
    canaries: list[str] = Field(
        default_factory=list,
        description="Tokens the payload asks the model to print; one in the report = it worked.",
    )""",
    ),
    Edit(
        f"{EV}/cli.py",
        "from ukvet_evals import authoring\n",
        "from ukvet_evals import authoring, phase4_cli\n",
    ),
    Edit(
        f"{EV}/cli.py",
        '    sp = add("report", cmd_report, "print results.json as markdown")\n'
        '    sp.add_argument("--results", required=True)\n    return p',
        '    sp = add("report", cmd_report, "print results.json as markdown")\n'
        '    sp.add_argument("--results", required=True)\n'
        "    phase4_cli.register(add, dataset)\n    return p",
    ),
    Edit(
        f"{EV}/run.py",
        "from ukvet_agent.llm import LlmSettings, NarrativeWriter, build_writer\n",
        "from ukvet_agent.guardrails import check_report\n"
        "from ukvet_agent.llm import LlmSettings, NarrativeWriter, build_writer\n",
    ),
    Edit(
        f"{EV}/run.py",
        "    cases: list[CaseResult] = []\n",
        "    cases: list[CaseResult] = []\n    guardrail_problems: list[dict[str, str]] = []\n",
    ),
    Edit(
        f"{EV}/run.py",
        "            score_narrative(report, narrative, c.id)\n",
        "            score_narrative(report, narrative, c.id)\n"
        "            guardrail_problems += [\n"
        '                {"company": c.id, "problem": p} for p in check_report(report)\n'
        "            ]\n",
    ),
    Edit(
        f"{EV}/run.py",
        '        "judge_rows": judge_rows,\n',
        '        "judge_rows": judge_rows,\n'
        '        "guardrails": {"reports": len(reports), "violations": guardrail_problems},\n',
    ),
    Edit(
        f"{EV}/report.py",
        '    perf = res["perf"]\n',
        """    guard = res.get("guardrails")
    if guard is not None:
        bad = guard["violations"]
        out.append(f"\\n## Output guardrails: {guard['reports'] - len({v['company'] for v in bad})}/{guard['reports']} reports clean\\n")
        out += [f"- {v['company']}: {v['problem']}" for v in bad[:30]]
        if not bad:
            out.append("No violations (disclaimer, opinion label, no advice or links, no markup).")

    perf = res["perf"]
""",
    ),
    Edit(
        f"{EV}/gate.py",
        "    g.passed = not g.problems\n    return g",
        """    gb = len(baseline.get("guardrails", {}).get("violations", []))
    gn = len(now.get("guardrails", {}).get("violations", []))
    g.table.append(("Output guardrail violations", str(gb), str(gn), f"{gn - gb:+d}"))
    if gn > gb:
        g.problems.append(f"output guardrail violations rose from {gb} to {gn} (see results.md)")

    g.passed = not g.problems
    return g""",
    ),
]

# Behaviour changes. Apply only after you have measured M6 "before" (Step 9 of the guide).
STAGE2: list[Edit] = [
    Edit(
        f"{AGENT}/citations.py",
        "from ukvet_agent.schemas import Claim, Fact\n",
        "from ukvet_agent.guardrails import ADVICE, VERDICT\nfrom ukvet_agent.schemas import Claim, Fact\n",
    ),
    Edit(
        f"{AGENT}/citations.py",
        '    if _FORBIDDEN.search(text):\n        return "uses wording that implies wrongdoing"\n',
        '    if _FORBIDDEN.search(text):\n        return "uses wording that implies wrongdoing"\n'
        "    if ADVICE.search(text) or VERDICT.search(text):\n"
        '        return "gives advice or states a risk verdict"\n',
    ),
    Edit(
        f"{AGENT}/nodes/reporter.py",
        "from ukvet_agent.llm import NarrativeDraft, NarrativeWriter\n",
        "from ukvet_agent.guardrails import claim_problems\n"
        "from ukvet_agent.llm import NarrativeDraft, NarrativeWriter\n",
    ),
    Edit(
        f"{AGENT}/nodes/reporter.py",
        '    q1 = by_id.get("Q1.status")\n    if q1 is not None:\n',
        '    q1 = by_id.get("Q1.status")\n'
        "    if q1 is not None and claim_problems(q1.statement):\n"
        "        # The registry text itself contains wording we never repeat (a link, advice, a\n"
        "        # wrongdoing word). Say so without quoting it.\n"
        "        headline = Claim(\n"
        '            text=f"The status of company {number} is recorded; see the facts below.",\n'
        "            fact_ids=[q1.id],\n"
        "        )\n"
        "    elif q1 is not None:\n",
    ),
    Edit(
        f"{AGENT}/nodes/reporter.py",
        '        if i in by_id and i != "Q1.status"\n    ][:MAX_FINDINGS]',
        '        if i in by_id and i != "Q1.status" and not claim_problems(by_id[i].statement)\n'
        "    ][:MAX_FINDINGS]",
    ),
]


CONFTEST_FIXTURE = '''

@pytest.fixture(autouse=True)
def no_real_tracing() -> Iterator[None]:
    """A developer's .env with LANGFUSE keys must never make a test talk to Langfuse."""
    from ukvet_agent.tracing import NoopTracer, set_tracer

    set_tracer(NoopTracer())
    yield
    set_tracer(None)
'''


def add_conftest_fixture(root: Path) -> list[str]:
    path = root / "tests" / "conftest.py"
    if not path.exists():
        return ["MISSING FILE tests/conftest.py (add the no_real_tracing fixture by hand)"]
    text = path.read_text(encoding="utf-8")
    if "no_real_tracing" in text:
        print("ok, already there  tests/conftest.py: no_real_tracing")
        return []
    head = ""
    if "from collections.abc import Iterator" not in text:
        head += "from collections.abc import Iterator\n"
    if not re.search(r"^import pytest", text, re.M):
        head += "import pytest\n"
    # imports go right after the module docstring / first line; ruff --fix sorts them afterwards
    path.write_text(
        head + text.rstrip("\n") + "\n" + CONFTEST_FIXTURE, encoding="utf-8", newline="\n"
    )
    print("edited             tests/conftest.py")
    return []


def apply(edits: list[Edit], root: Path) -> list[str]:
    failures: list[str] = []
    for e in edits:
        path = root / e.file
        if not path.exists():
            failures.append(f"MISSING FILE {e.file}")
            print(f"MISSING FILE   {e.file}")
            continue
        text = path.read_text(encoding="utf-8")
        if e.regex:
            if re.search(r"UKVET_TRACE_CONTENT", text):
                print(f"ok, already there  {e.file}")
                continue
            new_text, n = re.subn(e.old, lambda _m, new=e.new: new, text, flags=re.DOTALL)
            if n == 0:
                new_text, n = text.rstrip("\n") + "\n\n" + e.new, 1  # no old block: append
        else:
            if e.new in text:
                print(f"ok, already there  {e.file}: {e.old.strip().splitlines()[0][:60]}")
                continue
            if text.count(e.old) != 1:
                reason = "not found" if e.old not in text else "found more than once"
                failures.append(f"{e.file}: {reason}: {e.old.strip().splitlines()[0][:70]}")
                print(f"ANCHOR NOT FOUND   {e.file} ({reason})")
                print("  make this change by hand: find")
                print("    " + e.old.strip().replace("\n", "\n    "))
                print("  and make it")
                print("    " + e.new.strip().replace("\n", "\n    "))
                continue
            new_text = text.replace(e.old, e.new)
        path.write_text(new_text, encoding="utf-8", newline="\n")
        print(f"edited             {e.file}")
    return failures


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--defences", action="store_true", help="stage 2: behaviour changes")
    ap.add_argument("--root", default=".")
    args = ap.parse_args()
    root = Path(args.root).resolve()
    if not (root / "packages" / "ukvet-agent").is_dir():
        print("Run this from the ukvet repository root.", file=sys.stderr)
        return 2
    failures = apply(STAGE2 if args.defences else STAGE1, root)
    if not args.defences:
        failures += add_conftest_fixture(root)
    if failures:
        print(f"\n{len(failures)} edit(s) need doing by hand (see above).", file=sys.stderr)
        return 1
    print("\nAll edits applied. Next: uv sync --all-groups --all-packages --extra observability")
    return 0


if __name__ == "__main__":
    sys.exit(main())
