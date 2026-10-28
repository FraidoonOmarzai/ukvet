"""`ukvet-evals` command line. Run from the repository root.

ukvet-evals validate --dataset v0.1 [--strict]
ukvet-evals run --dataset v0.1 --split dev
ukvet-evals gate --dataset v0.1                 # what CI runs
ukvet-evals record 00445790 12056899 --dataset v0.1 --tags healthy-small
ukvet-evals build-items --dataset v0.1
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Any

from ukvet_evals import authoring, phase4_cli
from ukvet_evals.gate import compare
from ukvet_evals.items import build_items, golden_conflicts
from ukvet_evals.judge import JudgeSettings, agreement, build_judge, load_hand_labels
from ukvet_evals.report import render_markdown
from ukvet_evals.run import DatasetDriftError, ReplayMissError, RunOptions, evaluate, git_commit
from ukvet_evals.schema import (
    CompanyEntry,
    Dataset,
    Manifest,
    choose_salt,
    read_jsonl,
    split_for,
    write_jsonl,
)  # fmt: skip
from ukvet_evals.snapshot import Snapshot
from ukvet_evals.validate import validate

EXIT_DRIFT = 2
EXIT_REPLAY_MISS = 3


@contextmanager
def quiet_logs() -> Iterator[None]:
    """Silence per-request log lines during a run, then restore the previous level."""
    previous = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        yield
    finally:
        logging.disable(previous)


def _root(args: argparse.Namespace) -> Path:
    return Path(args.root).resolve()


def _load_env_file(root: Path) -> None:
    """Minimal .env reader (no python-dotenv dependency); real environment variables win."""
    path = root / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _snaps(ds: Dataset) -> dict[str, Snapshot]:
    return {
        c.company_number: Snapshot.load(ds.snapshot_dir / f"{c.company_number}.json")
        for c in ds.companies
    }


def _out_dir(args: argparse.Namespace, root: Path) -> Path:
    return (
        Path(args.out) if args.out else root / "evals" / "results" / f"{args.dataset}-{args.split}"
    )


def _log_test_split(root: Path, args: argparse.Namespace) -> None:
    if args.split in ("test", "all"):
        if not args.confirm_test_split:
            sys.exit(
                "The TEST split is for milestones only (ADR-009 D5). Re-run with "
                '--confirm-test-split "why you are looking at it now".'
            )
        log = root / "evals" / "results" / "TEST_SPLIT_LOG.md"
        log.parent.mkdir(parents=True, exist_ok=True)
        new = not log.exists()
        with log.open("a", encoding="utf-8") as fh:
            if new:
                fh.write("# Test split log\n\nEvery look at the test split, with the reason.\n\n")
            fh.write(
                f"- {date.today()} · git {git_commit(root)} · {args.dataset} · {args.split} · "
                f"{args.confirm_test_split}\n"
            )


def cmd_run(args: argparse.Namespace) -> int:
    root = _root(args)
    _load_env_file(root)
    _log_test_split(root, args)
    judge = None
    if args.judge:
        judge = build_judge(JudgeSettings())
        if judge is None:
            sys.exit(
                "--judge needs JUDGE_PROVIDER, JUDGE_MODEL and JUDGE_API_KEY "
                "(a different model family from the writer)"
            )
    options = RunOptions(
        root=root,
        dataset=args.dataset,
        split=args.split,
        llm=args.llm,
        model=args.model,
        judge=judge,
    )
    try:
        with quiet_logs():
            res = asyncio.run(evaluate(options))
    except DatasetDriftError as exc:
        print(f"DATASET PROBLEM: {exc}", file=sys.stderr)
        return EXIT_DRIFT
    except ReplayMissError as exc:
        print(f"REPLAY MISS: {exc}", file=sys.stderr)
        return EXIT_REPLAY_MISS
    out = _out_dir(args, root)
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(
        json.dumps(res, indent=1, sort_keys=True) + "\n", encoding="utf-8"
    )
    (out / "results.md").write_text(render_markdown(res), encoding="utf-8")
    print(render_markdown(res))
    print(f"written to {out}")
    return 0


def cmd_gate(args: argparse.Namespace) -> int:
    root = _root(args)
    baseline_path = (
        Path(args.baseline)
        if args.baseline
        else root / "evals" / "baselines" / f"{args.dataset}.json"
    )
    if args.results:
        res = json.loads(Path(args.results).read_text(encoding="utf-8"))
    else:
        try:
            with quiet_logs():
                res = asyncio.run(
                    evaluate(RunOptions(root=root, dataset=args.dataset, split="dev", llm="none"))
                )
        except DatasetDriftError as exc:
            print(f"DATASET PROBLEM: {exc}", file=sys.stderr)
            return EXIT_DRIFT
    if args.update_baseline:
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        stable = {k: v for k, v in res.items() if k not in ("perf", "judge_rows")}
        stable["meta"] = {k: v for k, v in res["meta"].items() if k != "created_at"}
        baseline_path.write_text(
            json.dumps(stable, indent=1, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(
            f"baseline written to {baseline_path}\n"
            "Commit it in a PR that says WHY, and add a decision-log entry."
        )
        return 0
    if not baseline_path.exists():
        print(
            f"No baseline at {baseline_path}. Create one with --update-baseline.", file=sys.stderr
        )
        return 1
    result = compare(json.loads(baseline_path.read_text(encoding="utf-8")), res)
    text = result.markdown()
    print(text)
    if args.markdown:
        Path(args.markdown).write_text(text, encoding="utf-8")
    return 0 if result.passed else 1


def cmd_validate(args: argparse.Namespace) -> int:
    rep = validate(_root(args), args.dataset, strict=args.strict)
    print(json.dumps(rep.coverage, indent=1))
    for w in rep.warnings:
        print(f"warning: {w}")
    for e in rep.errors:
        print(f"ERROR: {e}")
    print("OK" if rep.ok else "FAILED")
    return 0 if rep.ok else 1


def cmd_build_items(args: argparse.Namespace) -> int:
    root = _root(args)
    ds = Dataset(root / "evals", args.dataset)
    snaps = _snaps(ds)
    conflicts = golden_conflicts(ds.companies, snaps, ds.golden)
    if conflicts:
        print("Golden values disagree with the oracle. Fix the oracle or the label first:")
        for c in conflicts:
            print(f"  {c}")
        return 1
    items = build_items(ds.companies, snaps, ds.golden)
    write_jsonl(ds.dir / "items.jsonl", items)
    print(f"wrote {len(items)} items to {ds.dir / 'items.jsonl'}")
    return 0


def _manifest_path(ds: Dataset) -> Path:
    return ds.dir / "dataset.json"


def cmd_choose_salt(args: argparse.Namespace) -> int:
    ds = Dataset(_root(args) / "evals", args.dataset)
    if ds.manifest.splits_locked:
        print("Splits are locked; refusing to change the salt.", file=sys.stderr)
        return 1
    ids = [c.id for c in ds.companies]
    salt = choose_salt(ids, ds.manifest.dev_percent)
    updated = ds.manifest.model_copy(update={"split_salt": salt})
    _manifest_path(ds).write_text(updated.model_dump_json(indent=1) + "\n", encoding="utf-8")
    dev = sum(split_for(i, salt, ds.manifest.dev_percent) == "dev" for i in ids)
    print(f"salt {salt}: {dev} dev / {len(ids) - dev} test. Now run `set-splits --lock`.")
    return 0


def cmd_set_splits(args: argparse.Namespace) -> int:
    root = _root(args)
    path = root / "evals" / "datasets" / args.dataset
    manifest = Manifest.model_validate_json((path / "dataset.json").read_text(encoding="utf-8"))
    if manifest.splits_locked:
        print("Splits are locked.", file=sys.stderr)
        return 1
    rows = read_jsonl(path / "companies.jsonl", CompanyEntry)
    rows = [
        r.model_copy(update={"split": split_for(r.id, manifest.split_salt, manifest.dev_percent)})
        for r in rows
    ]
    write_jsonl(path / "companies.jsonl", rows)
    if args.lock:
        (path / "dataset.json").write_text(
            manifest.model_copy(update={"splits_locked": True}).model_dump_json(indent=1) + "\n",
            encoding="utf-8",
        )
    print(
        f"{sum(r.split == 'dev' for r in rows)} dev / {sum(r.split == 'test' for r in rows)} test"
        f"{' (locked)' if args.lock else ''}"
    )
    return 0


def cmd_record(args: argparse.Namespace) -> int:
    from ukvet_evals.record import http_fetch, make_anonymiser, record_company

    root = _root(args)
    _load_env_file(root)
    key = os.environ.get("CH_API_KEY")
    if not key:
        sys.exit("Set CH_API_KEY in .env or the environment")
    ds_dir = root / "evals" / "datasets" / args.dataset
    snap_dir = root / "evals" / "snapshots" / args.dataset
    ds_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = ds_dir / "dataset.json"
    if manifest_path.exists():
        manifest = Manifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    else:
        manifest = Manifest(name=args.dataset, version=args.dataset, split_salt="s0")
        manifest_path.write_text(manifest.model_dump_json(indent=1) + "\n", encoding="utf-8")
    companies = read_jsonl(ds_dir / "companies.jsonl", CompanyEntry)
    anon = make_anonymiser(root, set(args.public or []))
    as_of = date.fromisoformat(args.as_of) if args.as_of else date.today()
    tags = [t for t in (args.tags or "").split(",") if t]
    fetch, close = http_fetch(key)
    try:
        for number in args.numbers:
            snap = record_company(fetch, number, as_of, anon, public=number in (args.public or []))
            if snap is None:
                print(f"{number}: not found, skipped")
                continue
            alias = snap.meta.company_number
            snap.save(snap_dir / f"{alias}.json")
            existing = next((c for c in companies if c.company_number == alias), None)
            if existing is None:
                cid = f"c{len(companies) + 1:03d}"
                split = split_for(cid, manifest.split_salt, manifest.dev_percent)
                entry = CompanyEntry(
                    id=cid,
                    company_number=alias,
                    as_of=as_of,
                    tags=tags,
                    split=split,
                    public=number in (args.public or []),
                )
                companies.append(entry)
                write_jsonl(ds_dir / "companies.jsonl", companies)
                print(f"{number} -> {alias} ({cid}) recorded")
            else:
                print(f"{number} -> {alias} ({existing.id}) re-recorded")
            anon.save()
    finally:
        close()
        anon.save()
    write_jsonl(ds_dir / "companies.jsonl", companies)
    print(
        "Next: choose-salt / set-splits --lock (once, before looking at results), then build-items."
    )
    return 0


def cmd_gen_abstention(args: argparse.Namespace) -> int:
    ds = Dataset(_root(args) / "evals", args.dataset)
    cases = authoring.gen_abstention(ds.companies, _snaps(ds), ds.abstention)
    write_jsonl(ds.dir / "abstention.jsonl", cases)
    print(
        f"{len(cases)} cases ({len(cases) - len(ds.abstention)} new drafts). "
        "REVIEW every expectation."
    )
    return 0


def cmd_label_template(args: argparse.Namespace) -> int:
    ds = Dataset(_root(args) / "evals", args.dataset)
    rows = authoring.flag_template(ds.companies, ds.flags)
    write_jsonl(ds.dir / "flags.jsonl", rows)
    todo = sum(1 for r in rows if r.expected is None)
    print(
        f"{len(rows)} rows, {todo} still unlabelled (expected: null). "
        "Label from evals/LABELLING.md BEFORE running the rules."
    )
    return 0


def cmd_seed_injection(args: argparse.Namespace) -> int:
    ds = Dataset(_root(args) / "evals", args.dataset)
    if ds.injection:
        print("injection.jsonl already has cases; not overwriting")
        return 0
    write_jsonl(ds.dir / "injection.jsonl", authoring.injection_cases())
    print(f"seeded {len(authoring.INJECTION_SEEDS)} injection cases (scored in Phase 4)")
    return 0


def cmd_demo_build(args: argparse.Namespace) -> int:
    from ukvet_evals.demo import build_demo

    print(f"demo dataset written to {build_demo(_root(args))}")
    return 0


def cmd_draft_build(args: argparse.Namespace) -> int:
    from ukvet_evals.draft import build_draft

    print(f"synthetic v0.1-draft dataset written to {build_draft(_root(args))}")
    return 0


def cmd_judge_agreement(args: argparse.Namespace) -> int:
    res = json.loads(Path(args.results).read_text(encoding="utf-8"))
    hand = load_hand_labels(Path(args.hand))
    judged = {r["key"]: bool(r["supported"]) for r in res.get("judge_rows", [])}
    keys = sorted(set(hand) & set(judged))
    if not keys:
        sys.exit("no overlapping keys between hand labels and judge rows")
    print(json.dumps(agreement([hand[k] for k in keys], [judged[k] for k in keys]), indent=1))
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    res: dict[str, Any] = json.loads(Path(args.results).read_text(encoding="utf-8"))
    print(render_markdown(res))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ukvet-evals",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--root", default=".", help="repository root (default: current directory)")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add(name: str, fn: Any, help_: str) -> argparse.ArgumentParser:
        sp = sub.add_parser(name, help=help_)
        sp.set_defaults(fn=fn)
        return sp

    def dataset(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--dataset", default=os.environ.get("EVAL_DATASET", "demo"))

    sp = add("run", cmd_run, "replay companies and score M1-M5")
    dataset(sp)
    sp.add_argument("--split", choices=["dev", "test", "all"], default="dev")
    sp.add_argument("--llm", choices=["none", "replay", "record", "live"], default="none")
    sp.add_argument("--model", help="model name used to find recorded answers (default LLM_MODEL)")
    sp.add_argument("--judge", action="store_true", help="also run the LLM judge (JUDGE_* env)")
    sp.add_argument("--out")
    sp.add_argument("--confirm-test-split", help="REQUIRED for test/all: why you are looking at it")

    sp = add("gate", cmd_gate, "compare a run with the committed baseline (CI)")
    dataset(sp)
    sp.add_argument("--baseline")
    sp.add_argument("--results", help="use an existing results.json instead of running")
    sp.add_argument("--markdown", help="write the comparison table here (for a PR comment)")
    sp.add_argument("--update-baseline", action="store_true")

    sp = add("validate", cmd_validate, "check structure, drift, personal-data leaks and coverage")
    dataset(sp)
    sp.add_argument("--strict", action="store_true", help="coverage shortfalls become errors")

    sp = add(
        "build-items", cmd_build_items, "regenerate items.jsonl from snapshots + oracle + golden"
    )
    dataset(sp)
    sp = add("choose-salt", cmd_choose_salt, "pick the split salt once (before looking at results)")
    dataset(sp)
    sp = add("set-splits", cmd_set_splits, "apply the salt to companies.jsonl")
    dataset(sp)
    sp.add_argument("--lock", action="store_true", help="freeze the split for good")

    sp = add("record", cmd_record, "record anonymised snapshots from the live API")
    dataset(sp)
    sp.add_argument("numbers", nargs="+")
    sp.add_argument("--as-of")
    sp.add_argument("--tags", help="comma-separated tags for these companies")
    sp.add_argument("--public", nargs="*", help="large public company numbers kept un-anonymised")

    sp = add("gen-abstention", cmd_gen_abstention, "draft abstention cases (review them)")
    dataset(sp)
    sp = add("label-template", cmd_label_template, "add unlabelled rows to flags.jsonl")
    dataset(sp)
    sp = add("seed-injection", cmd_seed_injection, "seed injection.jsonl for Phase 4")
    dataset(sp)
    add("demo-build", cmd_demo_build, "rebuild the synthetic demo dataset")
    add("draft-build", cmd_draft_build, "rebuild the synthetic 28-company v0.1-draft dataset")
    sp = add("judge-agreement", cmd_judge_agreement, "compare judge verdicts with hand labels")
    sp.add_argument("--results", required=True)
    sp.add_argument("--hand", required=True)
    sp = add("report", cmd_report, "print results.json as markdown")
    sp.add_argument("--results", required=True)
    phase4_cli.register(add, dataset)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.fn(args))


if __name__ == "__main__":
    sys.exit(main())
