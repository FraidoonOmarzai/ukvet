"""Phase 4 subcommands: `extend-injection` and `injection` (M6).

Registered from cli.py with one line, so Phase 3's CLI code stays untouched.

    ukvet-evals extend-injection --dataset v0.1
    ukvet-evals injection --dataset v0.1 --split dev --llm record --model claude-haiku-5-5
    ukvet-evals injection --dataset v0.1 --split dev --llm replay --model claude-haiku-5-5 \\
        --baseline evals/baselines/v0.1-injection.json
    ukvet-evals injection --dataset v0.1 --update-baseline
"""

import argparse
import asyncio
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ukvet_evals import injection, injection_cases
from ukvet_evals.run import ReplayMissError
from ukvet_evals.schema import Dataset, write_jsonl

EXIT_REGRESSION = 1
EXIT_REPLAY_MISS = 3


def cmd_extend_injection(args: argparse.Namespace) -> int:
    ds = Dataset(Path(args.root).resolve() / "evals", args.dataset)
    extended = injection_cases.extend(ds.injection)
    added = len(extended) - len(ds.injection)
    write_jsonl(ds.dir / "injection.jsonl", extended)
    print(
        f"{len(extended)} injection cases ({added} new). Ids and payloads of existing cases are "
        "unchanged; canaries were added where missing. Review the new rows, then commit."
    )
    return 0


def cmd_injection(args: argparse.Namespace) -> int:
    from ukvet_evals import cli  # imported late: cli registers this module

    root = cli._root(args)
    cli._load_env_file(root)
    cli._log_test_split(root, args)
    options = injection.InjectionOptions(
        root=root,
        dataset=args.dataset,
        split=args.split,
        llm=args.llm,
        model=args.model,
        hosts=args.hosts,
    )
    try:
        with cli.quiet_logs():
            res = asyncio.run(injection.run_injection(options))
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except ReplayMissError as exc:
        print(f"REPLAY MISS: {exc}", file=sys.stderr)
        return EXIT_REPLAY_MISS

    out = Path(args.out) if args.out else root / "evals" / "results" / f"{args.dataset}-injection"
    out.mkdir(parents=True, exist_ok=True)
    (out / "injection.json").write_text(
        json.dumps(res, indent=1, sort_keys=True) + "\n", encoding="utf-8"
    )
    text = injection.render_markdown(res)
    (out / "injection.md").write_text(text, encoding="utf-8")
    print(text)
    print(f"written to {out}")

    baseline_path = (
        Path(args.baseline)
        if args.baseline
        else root / "evals" / "baselines" / f"{args.dataset}-injection.json"
    )
    if args.update_baseline:
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        baseline_path.write_text(json.dumps(res, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        print(f"baseline updated: {baseline_path}  (explain why in the decision log)")
        return 0
    if args.baseline or baseline_path.exists():
        baseline: dict[str, Any] = json.loads(baseline_path.read_text(encoding="utf-8"))
        problems = injection.compare_baseline(baseline, res)
        for p in problems:
            print(f"REGRESSION: {p}", file=sys.stderr)
        return EXIT_REGRESSION if problems else 0
    rate = res["m6"]["rate"]
    return EXIT_REGRESSION if rate is not None and rate < injection.TARGET_M6 else 0


def register(add: Callable[..., Any], dataset: Callable[[Any], None]) -> None:
    sp = add("extend-injection", cmd_extend_injection, "add Phase 4 injection cases (never edits)")
    dataset(sp)
    sp = add("injection", cmd_injection, "measure M6: prompt-injection resistance (needs an LLM)")
    dataset(sp)
    sp.add_argument("--split", choices=["dev", "test", "all"], default="dev")
    sp.add_argument("--llm", choices=["none", "replay", "record", "live"], default="replay")
    sp.add_argument("--model", help="model name used to find recorded answers (default LLM_MODEL)")
    sp.add_argument("--hosts", type=int, default=3, help="host companies per case (default 3)")
    sp.add_argument("--out")
    sp.add_argument("--baseline", help="fail if a previously resisted run now fails")
    sp.add_argument("--update-baseline", action="store_true")
    sp.add_argument("--confirm-test-split", help="REQUIRED for test/all: why you are looking")
