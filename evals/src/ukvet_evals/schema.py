"""Dataset models and loaders. Everything on disk is JSON / JSONL so diffs are readable."""

import hashlib
import json
from collections.abc import Iterable
from datetime import date
from pathlib import Path
from typing import Any, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from ukvet_evals.constants import DEV_PERCENT, FLAG_IDS, QUESTIONS

Split = Literal["dev", "test"]
Severity = Literal["high", "medium", "low", "info"]
RiskLevel = Literal["low", "medium", "high", "insufficient_data"]
FaultMode = Literal["timeout", "unavailable", "permanent", "transient"]
ToolName = Literal[
    "get_company_profile",
    "get_officers",
    "get_persons_with_significant_control",
    "get_charges",
    "get_insolvency",
    "get_filing_history",
    "get_officer_appointments",
]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


def split_for(company_id: str, salt: str = "", dev_percent: int = DEV_PERCENT) -> Split:
    """Fixed, reproducible split: decided by a hash of (salt, id), never by hand (ADR-009 D5)."""
    digest = hashlib.sha256(f"{salt}:{company_id}".encode()).hexdigest()
    return "dev" if int(digest[:8], 16) % 100 < dev_percent else "test"


def choose_salt(company_ids: list[str], dev_percent: int = DEV_PERCENT, tries: int = 500) -> str:
    """Pick the first salt whose split is closest to the target share.

    A pure hash split of ~28 companies can be badly unbalanced by chance. Choosing the salt ONCE,
    before any result is looked at, keeps the split balanced and still independent of outcomes.
    """
    n = len(company_ids)
    target = n * dev_percent / 100
    best_salt, best_gap = "s0", float("inf")
    for i in range(tries):
        salt = f"s{i}"
        dev = sum(split_for(c, salt, dev_percent) == "dev" for c in company_ids)
        gap = abs(dev - target)
        if gap < best_gap:
            best_salt, best_gap = salt, gap
        if gap < 0.5:
            break
    return best_salt


class Manifest(Strict):
    name: str
    version: str
    split_salt: str
    dev_percent: int = DEV_PERCENT
    description: str = ""
    synthetic: bool = False
    splits_locked: bool = False


class CompanyEntry(Strict):
    id: str = Field(pattern=r"^c\d{3,}$")
    company_number: str = Field(description="Anonymised number; also the snapshot file name.")
    as_of: date
    tags: list[str] = Field(default_factory=list)
    split: Split
    public: bool = Field(default=False, description="Large public company kept un-anonymised.")
    notes: str = ""


class GoldenRow(Strict):
    """Values read BY HAND from the live Companies House website."""

    company: str
    checked_on: date
    source: str = Field(description="What you looked at, e.g. the page URL path.")
    fields: dict[str, Any]
    checker: str = ""


class ExpectedFlag(Strict):
    id: str
    severity: Severity | None = None

    @model_validator(mode="after")
    def _known(self) -> "ExpectedFlag":
        if self.id not in FLAG_IDS:
            raise ValueError(f"unknown flag id '{self.id}'")
        return self


class FlagLabel(Strict):
    """Hand-labelled expected red flags (labelled from the written definitions, ADR-009)."""

    company: str
    expected: list[ExpectedFlag] | None = Field(
        default=None, description="null = not labelled yet (company is skipped by M5)."
    )
    labeller: str = ""
    labelled_on: date | None = None
    second_labeller_expected: list[str] | None = Field(
        default=None, description="Flag ids chosen by a second labeller, for agreement."
    )
    notes: str = ""


class FaultSpec(Strict):
    tool: ToolName
    mode: FaultMode
    times: int = Field(default=1, ge=1, description="transient only: calls that fail first.")
    director_index: int | None = Field(
        default=None, ge=1, description="get_officer_appointments only: 1-based director."
    )


class AbstentionCase(Strict):
    id: str
    company: str
    faults: list[FaultSpec] = Field(min_length=1)
    expected_gap_questions: list[str]
    expected_absent_fact_ids: list[str] = Field(default_factory=list)
    expected_risk: RiskLevel | None = None
    notes: str = ""

    @model_validator(mode="after")
    def _known(self) -> "AbstentionCase":
        bad = [q for q in self.expected_gap_questions if q not in QUESTIONS]
        if bad:
            raise ValueError(f"unknown question ids {bad}")
        return self


class InjectionCase(Strict):
    id: str
    kind: Literal["company_name", "officer_name", "charge_holder", "registry_text"]
    payload: str
    expect: str = Field(description="What must NOT happen (scored in Phase 4, M6).")


class Item(Strict):
    id: str
    company: str
    question: str
    as_of: date
    split: Split
    fields: dict[str, Any]
    label_source: Literal["oracle", "oracle+golden"]
    notes: str = ""


T = TypeVar("T", bound=BaseModel)


def read_jsonl(path: Path, model: type[T]) -> list[T]:
    if not path.exists():
        return []
    rows: list[T] = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip() or line.lstrip().startswith("//"):
            continue
        try:
            rows.append(model.model_validate_json(line))
        except ValidationError as exc:
            raise ValueError(f"{path.name}:{n}: {exc}") from exc
    return rows


def write_jsonl(path: Path, rows: Iterable[BaseModel]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(row.model_dump(mode="json"), sort_keys=True) + "\n")


class Dataset:
    """A versioned dataset directory: evals/datasets/<name>/ + evals/snapshots/<name>/."""

    def __init__(self, root: Path, name: str) -> None:
        self.name = name
        self.dir = root / "datasets" / name
        self.snapshot_dir = root / "snapshots" / name
        if not self.dir.is_dir():
            raise FileNotFoundError(f"dataset '{name}' not found at {self.dir}")
        manifest_path = self.dir / "dataset.json"
        if not manifest_path.exists():
            raise FileNotFoundError(f"{manifest_path} is missing")
        self.manifest = Manifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
        self.companies = read_jsonl(self.dir / "companies.jsonl", CompanyEntry)
        for c in self.companies:
            expected = split_for(c.id, self.manifest.split_salt, self.manifest.dev_percent)
            if c.split != expected:
                raise ValueError(
                    f"{c.id}: split must be '{expected}' (derived from salt and id; never edit it)"
                )
        self.golden = read_jsonl(self.dir / "golden.jsonl", GoldenRow)
        self.flags = read_jsonl(self.dir / "flags.jsonl", FlagLabel)
        self.abstention = read_jsonl(self.dir / "abstention.jsonl", AbstentionCase)
        self.injection = read_jsonl(self.dir / "injection.jsonl", InjectionCase)
        self.items = read_jsonl(self.dir / "items.jsonl", Item)

    def company(self, company_id: str) -> CompanyEntry:
        for c in self.companies:
            if c.id == company_id:
                return c
        raise KeyError(company_id)

    def select(self, split: str) -> list[CompanyEntry]:
        if split == "all":
            return list(self.companies)
        return [c for c in self.companies if c.split == split]
