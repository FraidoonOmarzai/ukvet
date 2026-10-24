"""M5: red-flag recall (and precision) against hand-written labels.

Labels are written from the flag DEFINITIONS before the rules are run on a company, so the rules
are not graded against their own output. Companies with `expected: null` are skipped (and counted
as unlabelled in the report).
"""

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from ukvet_agent.schemas import Report

from ukvet_evals.schema import FlagLabel
from ukvet_evals.stats import Rate, cohens_kappa


@dataclass
class FlagScore:
    labelled: int = 0
    unlabelled: int = 0
    expected_total: int = 0
    found_total: int = 0
    produced_total: int = 0
    produced_expected: int = 0
    severity_checked: int = 0
    severity_match: int = 0
    by_flag_expected: Counter[str] = field(default_factory=Counter)
    by_flag_found: Counter[str] = field(default_factory=Counter)
    missed: list[dict[str, Any]] = field(default_factory=list)
    unexpected: list[dict[str, Any]] = field(default_factory=list)
    severity_mismatch: list[dict[str, Any]] = field(default_factory=list)
    second_labeller_pairs: list[tuple[str, str]] = field(default_factory=list)

    def recall(self) -> Rate:
        return Rate(self.found_total, self.expected_total)

    def precision(self) -> Rate:
        return Rate(self.produced_expected, self.produced_total)

    def severity(self) -> Rate:
        return Rate(self.severity_match, self.severity_checked)

    def to_dict(self) -> dict[str, Any]:
        a = [x for x, _ in self.second_labeller_pairs]
        b = [y for _, y in self.second_labeller_pairs]
        agree = Rate(sum(x == y for x, y in self.second_labeller_pairs), len(a))
        return {
            "labelled_companies": self.labelled,
            "unlabelled_companies": self.unlabelled,
            "recall": self.recall().to_dict(),
            "precision": self.precision().to_dict(),
            "severity_agreement": self.severity().to_dict(),
            "by_flag": {
                f: {"expected": n, "found": self.by_flag_found.get(f, 0)}
                for f, n in sorted(self.by_flag_expected.items())
            },
            "missed": self.missed,
            "unexpected": self.unexpected,
            "severity_mismatch": self.severity_mismatch,
            "second_labeller": {
                "pairs": len(a),
                "agreement": agree.to_dict(),
                "kappa": cohens_kappa(a, b),
            },
        }


def score_flags(report: Report, label: FlagLabel, tags: list[str], score: FlagScore) -> None:
    if label.expected is None:
        score.unlabelled += 1
        return
    score.labelled += 1
    produced = {f.id: f.severity for f in report.red_flags}
    expected = {e.id: e.severity for e in label.expected}
    for fid, sev in expected.items():
        score.expected_total += 1
        score.by_flag_expected[fid] += 1
        if fid in produced:
            score.found_total += 1
            score.by_flag_found[fid] += 1
            if sev is not None:
                score.severity_checked += 1
                if produced[fid] == sev:
                    score.severity_match += 1
                else:
                    score.severity_mismatch.append(
                        {
                            "company": label.company,
                            "flag": fid,
                            "expected": sev,
                            "got": produced[fid],
                        }
                    )
        else:
            score.missed.append({"company": label.company, "flag": fid, "tags": tags})
    for fid, sev in produced.items():
        score.produced_total += 1
        if fid in expected:
            score.produced_expected += 1
        else:
            score.unexpected.append(
                {"company": label.company, "flag": fid, "severity": sev, "tags": tags}
            )
    if label.second_labeller_expected is not None:
        for fid in sorted(set(expected) | set(label.second_labeller_expected)):
            score.second_labeller_pairs.append(
                (
                    "yes" if fid in expected else "no",
                    "yes" if fid in label.second_labeller_expected else "no",
                )
            )
