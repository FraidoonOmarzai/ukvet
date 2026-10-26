"""Print real company number, alias, tags and page link for each eval company.

Reads data/raw/eval_mapping.json (private) and evals/datasets/<name>/companies.jsonl.
Prints to the terminal only. Never writes a file, never prints person names.
Usage: uv run python scripts/golden_sheet.py [dataset]   (default v0.1)
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

NUM = re.compile(r"^(?:[0-9]{8}|[A-Z]{2}[0-9]{6}|[A-Z]{2}[0-9]{5}[A-Z0-9])$")
URL = "https://find-and-update.company-information.service.gov.uk/company/"


def walk(node: object, found: dict[str, str]) -> None:
    if isinstance(node, dict):
        for k, v in node.items():
            if isinstance(k, str) and NUM.match(k) and isinstance(v, str):
                found[k] = v
            else:
                walk(v, found)
    elif isinstance(node, list):
        for item in node:
            walk(item, found)


def main() -> int:
    dataset = sys.argv[1] if len(sys.argv) > 1 else "v0.1"
    mapping = json.loads(Path("data/raw/eval_mapping.json").read_text(encoding="utf-8"))
    pairs: dict[str, str] = {}
    walk(mapping, pairs)
    rows = [
        json.loads(line)
        for line in Path(f"evals/datasets/{dataset}/companies.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    by_value: dict[str, dict] = {}
    for row in rows:
        for v in row.values():
            if isinstance(v, str):
                by_value[v] = row
    shown = 0
    print(f"{'alias':6} {'split':5} {'real number':10}  tags")
    for real, fake in sorted(
        pairs.items(), key=lambda kv: by_value.get(kv[1], {}).get("id", "zzz")
    ):
        row = by_value.get(fake)
        if row is None:
            continue
        alias = row.get("id", "?")
        split = row.get("split", "?")
        tags = ",".join(row.get("tags", []))
        print(f"{alias:6} {split:5} {real:10}  {tags}")
        print(f"       {URL}{real}")
        shown += 1
    print(f"\n{shown} of {len(rows)} companies matched.")
    if shown < len(rows):
        print("Some companies did not match: paste the output of the line below (no names) to me.")
        print(
            "python -c \"import json;d=json.load(open('data/raw/eval_mapping.json'));print({k:(type(v).__name__,len(v)) for k,v in d.items()})\""
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
