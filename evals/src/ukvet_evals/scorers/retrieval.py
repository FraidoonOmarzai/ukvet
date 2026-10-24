"""M1: retrieval accuracy. Pipeline facts vs oracle/golden values, per field and per question."""

from dataclasses import dataclass, field
from typing import Any

from ukvet_agent.schemas import Report

from ukvet_evals.constants import QUESTIONS
from ukvet_evals.fields import MISSING, extract_fields, normalise
from ukvet_evals.schema import Item
from ukvet_evals.stats import Rate


@dataclass
class FieldResult:
    item: str
    field: str
    expected: Any
    actual: Any
    correct: bool


@dataclass
class RetrievalScore:
    fields: list[FieldResult] = field(default_factory=list)
    items_total: dict[str, int] = field(default_factory=dict)
    items_correct: dict[str, int] = field(default_factory=dict)

    def rate_for(self, question: str | None = None) -> Rate:
        rows = [r for r in self.fields if question is None or r.field.startswith(f"{question}.")]
        return Rate(sum(r.correct for r in rows), len(rows))

    def item_rate_for(self, question: str | None = None) -> Rate:
        qs = [question] if question else list(self.items_total)
        return Rate(
            sum(self.items_correct.get(q, 0) for q in qs),
            sum(self.items_total.get(q, 0) for q in qs),
        )

    @property
    def failures(self) -> list[FieldResult]:
        return [r for r in self.fields if not r.correct]

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall": {
                "fields": self.rate_for().to_dict(),
                "items": self.item_rate_for().to_dict(),
            },
            "by_question": {
                q: {
                    "fields": self.rate_for(q).to_dict(),
                    "items": self.item_rate_for(q).to_dict(),
                }
                for q in QUESTIONS
                if q in self.items_total
            },
            "failures": [
                {"item": r.item, "field": r.field, "expected": r.expected, "actual": r.actual}
                for r in self.failures
            ],
        }


def score_report(report: Report, items: list[Item], score: RetrievalScore) -> None:
    actual = extract_fields(report)
    for item in items:
        ok_all = True
        for key, expected in item.fields.items():
            got = actual.get(key, MISSING)
            correct = normalise(got) == normalise(expected)
            ok_all &= correct
            score.fields.append(FieldResult(item.id, key, expected, got, correct))
        q = item.question
        score.items_total[q] = score.items_total.get(q, 0) + 1
        score.items_correct[q] = score.items_correct.get(q, 0) + int(ok_all)
