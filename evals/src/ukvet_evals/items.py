"""Build the frozen item list (items.jsonl) from snapshots + oracle, cross-checked with golden."""

from dataclasses import dataclass
from typing import Any

from ukvet_evals.fields import FIELDS, normalise, question_of
from ukvet_evals.oracle import oracle_fields
from ukvet_evals.schema import CompanyEntry, GoldenRow, Item
from ukvet_evals.snapshot import Snapshot


@dataclass
class GoldenConflict:
    company: str
    field: str
    oracle: Any
    golden: Any

    def __str__(self) -> str:
        return f"{self.company} {self.field}: oracle={self.oracle!r} golden={self.golden!r}"


def golden_conflicts(
    companies: list[CompanyEntry], snaps: dict[str, Snapshot], golden: list[GoldenRow]
) -> list[GoldenConflict]:
    """Every field where the hand-read website value disagrees with the oracle."""
    by_id = {c.id: c for c in companies}
    out: list[GoldenConflict] = []
    for row in golden:
        company = by_id[row.company]
        oracle = oracle_fields(snaps[company.company_number], company.as_of)
        for key, value in row.fields.items():
            if key not in oracle:
                out.append(GoldenConflict(row.company, key, "<unknown field>", value))
            elif normalise(oracle[key]) != normalise(value):
                out.append(GoldenConflict(row.company, key, oracle[key], value))
    return out


def build_items(
    companies: list[CompanyEntry], snaps: dict[str, Snapshot], golden: list[GoldenRow]
) -> list[Item]:
    gold: dict[str, set[str]] = {}
    for row in golden:
        gold.setdefault(row.company, set()).update(row.fields)
    items: list[Item] = []
    for c in companies:
        oracle = oracle_fields(snaps[c.company_number], c.as_of)
        for q, keys in FIELDS.items():
            fields = {k: normalise(oracle[k]) for k in keys}
            covered = gold.get(c.id, set()) & set(keys)
            items.append(
                Item(
                    id=f"{c.id}-{q}",
                    company=c.id,
                    question=q,
                    as_of=c.as_of,
                    split=c.split,
                    fields=fields,
                    label_source="oracle+golden" if covered else "oracle",
                    notes=f"golden-checked: {', '.join(sorted(covered))}" if covered else "",
                )
            )
    return items


def golden_coverage(golden: list[GoldenRow]) -> dict[str, int]:
    """How many golden-checked fields exist per question (shown in the report)."""
    counts = {q: 0 for q in FIELDS}
    for row in golden:
        for key in row.fields:
            q = question_of(key)
            if q in counts:
                counts[q] += 1
    return counts
