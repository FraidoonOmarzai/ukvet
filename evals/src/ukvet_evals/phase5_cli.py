"""Phase 5 subcommand: `compare` (model comparison table).

    ukvet-evals compare --init                       # writes evals/comparison.json to fill in
    ukvet-evals compare                              # writes docs/results.md and .json
    ukvet-evals compare --manifest other.json --out docs/results.md

Registered from phase4_cli.register, so cli.py needs no change.
"""

import argparse
import json
import shutil
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ukvet_evals import compare

EXIT_REFUSED = 2


def cmd_compare(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    manifest = root / args.manifest
    example = Path(__file__).resolve().parents[2] / "comparison.example.json"
    if args.init:
        if manifest.exists():
            print(f"{manifest} already exists; not overwriting.", file=sys.stderr)
            return EXIT_REFUSED
        src = example if example.exists() else root / "evals" / "comparison.example.json"
        manifest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(src, manifest)
        print(f"wrote {manifest}. Fill in the REPLACE values, then run `ukvet-evals compare`.")
        return 0
    if not manifest.exists():
        print(
            f"no manifest at {manifest}. Run `ukvet-evals compare --init` first.", file=sys.stderr
        )
        return EXIT_REFUSED
    try:
        text, data = compare.build(manifest, root)
    except compare.ComparisonError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    out = root / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8", newline="\n")
    out.with_suffix(".json").write_text(
        json.dumps(data, indent=1, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )
    print(text)
    for w in data["warnings"]:
        print(f"WARNING: {w}", file=sys.stderr)
    print(f"written to {out}")
    return 0


def register(add: Callable[..., Any], dataset: Callable[[Any], None]) -> None:
    sp = add("compare", cmd_compare, "Phase 5: model comparison table from a manifest")
    sp.add_argument("--manifest", default="evals/comparison.json")
    sp.add_argument("--out", default="docs/results.md")
    sp.add_argument("--init", action="store_true", help="create the manifest from the example")
