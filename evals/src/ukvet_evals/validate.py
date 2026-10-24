"""Dataset validation: structure, cross-references, drift, personal-data leak check, coverage."""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ukvet_evals.constants import (
    MIN_ABSTENTION_CASES,
    MIN_COMPANIES,
    MIN_FLAG_COMPANIES,
    MIN_INJECTION_CASES,
    MIN_ITEMS,
    MIN_ITEMS_PER_QUESTION,
    QUESTIONS,
    REQUIRED_TAGS,
)
from ukvet_evals.items import build_items, golden_conflicts
from ukvet_evals.schema import Dataset
from ukvet_evals.snapshot import Snapshot

# Keys the anonymiser must have removed (kept in sync with scripts/anonymise.py by a test).
FORBIDDEN_KEYS = {
    "date_of_birth", "address", "nationality", "occupation", "country_of_residence",
    "registered_office_address", "service_address", "usual_residential_address",
    "residential_address", "principal_office_address", "practitioners", "description_values",
    "name_elements", "identification", "etag", "former_names", "previous_company_names",
    "foreign_company_details", "accounts_reference_date", "address_snippet", "snippet", "matches",
}  # fmt: skip
_PERSON = re.compile(
    r"^(PERSON|CORPORATE CONTROLLER) \d{3,}$|^DIRECTOR [A-Z]$|^PERSON [A-Z]$|^SECRETARY [A-Z]$"
)
_COMPANY = re.compile(r"^TEST COMPANY \d{3,}$|TEST LTD$")


@dataclass
class Report:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    coverage: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors


def _walk(obj: Any, path: str = "") -> Any:
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield f"{path}/{k}", k, v
            yield from _walk(v, f"{path}/{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk(v, f"{path}[{i}]")


def leak_problems(snap: Snapshot) -> list[str]:
    """Personal data that must never be committed. Public companies keep their real names."""
    problems: list[str] = []
    bodies = [(k, e.body) for k, e in snap.endpoints.items() if e.body]
    bodies += [(f"appointments/{k}", e.body) for k, e in snap.appointments.items() if e.body]
    for label, body in bodies:
        for path, key, value in _walk(body):
            if key in FORBIDDEN_KEYS:
                problems.append(f"{label}{path}: forbidden key '{key}'")
            if snap.meta.public:
                continue
            person_context = label in {"officers", "psc"} or label.startswith("appointments/")
            if (
                key == "name"
                and isinstance(value, str)
                and person_context
                and not _PERSON.match(value)
            ):
                problems.append(f"{label}{path}: name '{value[:20]}' is not anonymised")
            if key == "company_name" and isinstance(value, str) and not _COMPANY.search(value):
                problems.append(f"{label}{path}: company_name '{value[:20]}' is not anonymised")
    return problems


def validate(root: Path, name: str, *, strict: bool = False) -> Report:
    rep = Report()
    try:
        ds = Dataset(root / "evals", name)
    except (FileNotFoundError, ValueError) as exc:
        rep.errors.append(str(exc))
        return rep

    ids = [c.id for c in ds.companies]
    numbers = [c.company_number for c in ds.companies]
    if len(set(ids)) != len(ids):
        rep.errors.append("duplicate company ids")
    if len(set(numbers)) != len(numbers):
        rep.errors.append("duplicate company numbers")

    snaps: dict[str, Snapshot] = {}
    for c in ds.companies:
        path = ds.snapshot_dir / f"{c.company_number}.json"
        if not path.exists():
            rep.errors.append(f"{c.id}: snapshot {path.name} is missing")
            continue
        snap = Snapshot.load(path)
        snaps[c.company_number] = snap
        if snap.meta.company_number != c.company_number or snap.meta.as_of != c.as_of:
            rep.errors.append(f"{c.id}: snapshot meta does not match companies.jsonl")
        if snap.meta.public != c.public:
            rep.errors.append(f"{c.id}: 'public' flag differs between snapshot and companies.jsonl")
        if not ds.manifest.synthetic and not snap.meta.synthetic:
            rep.errors += [f"{c.id}: LEAK {p}" for p in leak_problems(snap)]
        for ep in snap.meta.truncated:
            rep.warnings.append(f"{c.id}: endpoint '{ep}' was truncated at the fetch cap")
    for path in ds.snapshot_dir.glob("*.json"):
        if path.stem not in numbers:
            rep.warnings.append(f"snapshot {path.name} is not used by any company")

    known = set(ids)
    for label, rows in (
        ("golden", [g.company for g in ds.golden]),
        ("flags", [f.company for f in ds.flags]),
        ("abstention", [a.company for a in ds.abstention]),
    ):
        for company in rows:
            if company not in known:
                rep.errors.append(f"{label}: unknown company '{company}'")

    if len(snaps) == len(ds.companies):
        conflicts = golden_conflicts(ds.companies, snaps, ds.golden)
        rep.errors += [f"golden conflict: {c}" for c in conflicts]
        fresh = build_items(ds.companies, snaps, ds.golden)
        if [i.model_dump(mode="json") for i in fresh] != [
            i.model_dump(mode="json") for i in ds.items
        ]:
            rep.errors.append("items.jsonl is out of date: run `ukvet-evals build-items`")

    per_q = {q: sum(1 for i in ds.items if i.question == q) for q in QUESTIONS}
    tag_counts: dict[str, int] = {}
    for c in ds.companies:
        for t in c.tags:
            tag_counts[t] = tag_counts.get(t, 0) + 1
    labelled = sum(1 for f in ds.flags if f.expected is not None)
    test_n = sum(1 for c in ds.companies if c.split == "test")
    rep.coverage = {
        "companies": len(ds.companies),
        "dev": len(ds.companies) - test_n,
        "test": test_n,
        "items": len(ds.items),
        "items_per_question": per_q,
        "golden_companies": len({g.company for g in ds.golden}),
        "flag_labelled": labelled,
        "abstention_cases": len(ds.abstention),
        "injection_cases": len(ds.injection),
        "tags_missing": {
            t: n - tag_counts.get(t, 0)
            for t, n in REQUIRED_TAGS.items()
            if tag_counts.get(t, 0) < n
        },
    }

    gaps: list[str] = []
    if len(ds.companies) < MIN_COMPANIES:
        gaps.append(f"companies {len(ds.companies)} < {MIN_COMPANIES}")
    if len(ds.items) < MIN_ITEMS:
        gaps.append(f"items {len(ds.items)} < {MIN_ITEMS}")
    for q, n in per_q.items():
        if n < MIN_ITEMS_PER_QUESTION:
            gaps.append(f"{q} has {n} items < {MIN_ITEMS_PER_QUESTION}")
    if labelled < MIN_FLAG_COMPANIES:
        gaps.append(f"labelled flag companies {labelled} < {MIN_FLAG_COMPANIES}")
    if len(ds.abstention) < MIN_ABSTENTION_CASES:
        gaps.append(f"abstention cases {len(ds.abstention)} < {MIN_ABSTENTION_CASES}")
    if len(ds.injection) < MIN_INJECTION_CASES:
        gaps.append(f"injection cases {len(ds.injection)} < {MIN_INJECTION_CASES}")
    if len({g.company for g in ds.golden}) < min(MIN_COMPANIES, len(ds.companies)):
        gaps.append("golden set covers fewer companies than the dataset minimum")
    for tag, missing in rep.coverage["tags_missing"].items():
        gaps.append(f"tag '{tag}' needs {missing} more compan{'y' if missing == 1 else 'ies'}")
    (rep.errors if strict and not ds.manifest.synthetic else rep.warnings).extend(
        f"coverage: {g}" for g in gaps
    )
    return rep
