# ukvet evals

Repeatable measurement of ukvet: retrieval accuracy (M1), unsupported claims (M2), abstention (M3),
citation validity (M4) and red-flag recall (M5), plus the CI regression gate (M12).

> `datasets/demo` is **synthetic** (6 made-up companies). It proves the harness works and lets CI
> run before real data exists. Its scores say nothing about ukvet's accuracy. The real dataset is
> `datasets/v0.1`, which you build in Phase 3 (see "Build the real dataset" below).

## How it works in one picture

```
live Companies House API
        │  ukvet-evals record        (anonymised on the way in; never raw on disk)
        ▼
snapshots/<dataset>/<alias>.json     ← frozen raw API responses + "as of" date
        │
        ├─► oracle.py                independent code (imports neither ukvet package)
        │        └─► items.jsonl     expected value of every checkable field
        │                 ▲
        │      golden.jsonl: values YOU read by hand on the website (cross-checks the oracle)
        │
        └─► ReplayHarness            serves the snapshots through the REAL MCP server + agent graph
                 │                    (clock frozen at as_of; no network, no key, no cost)
                 ▼
            Report per company ──► scorers ──► results.json / results.md ──► gate vs baseline
```

| Layer | Scored by | Failure points at |
|---|---|---|
| Retrieval: facts equal the oracle | `scorers/retrieval.py` (M1) | mapper / client / fact builder |
| Rules: right flags, only those | `scorers/flags.py` (M5, plus precision) | rule thresholds |
| Abstention: failed tool → explicit gap, nothing invented | `faults.py` + `scorers/abstention.py` (M3) | verifier / risk logic |
| Writing: sentences supported by cited facts | `scorers/narrative.py` (M2, M4) | prompt / model |
| Quality opinion (optional) | `judge.py` | wording |

## Commands (run from the repository root; no `make` needed)

```powershell
uv run ukvet-evals validate --dataset demo            # structure, drift, personal-data leak check
uv run ukvet-evals run --dataset demo                 # dev split, template narrative, prints the table
uv run ukvet-evals gate --dataset demo                # what CI runs: compare with the baseline
uv run ukvet-evals gate --dataset demo --update-baseline   # ONLY in a PR that explains why
uv run ukvet-evals run --dataset v0.1 --split all --confirm-test-split "milestone: baseline"
```

Exit codes: `0` ok · `1` regression / failed validation · `2` dataset problem (stale `items.jsonl`,
golden disagrees with oracle) · `3` recorded LLM answers missing (re-record).

## The test split is protected

`--split test` or `all` refuses to run without `--confirm-test-split "reason"` and appends the
reason, date and git commit to `evals/results/TEST_SPLIT_LOG.md`. Tune rules and prompts on **dev**
only. Look at test once per milestone. The split is a hash of `(salt, company id)`, fixed once with
`choose-salt` + `set-splits --lock`. `companies.jsonl` is rejected if anyone hand-edits a split.

## Files in a dataset (`evals/datasets/<name>/`)

| File | What | Who writes it |
|---|---|---|
| `dataset.json` | name, version, split salt, locked flag | `record` / `choose-salt` |
| `companies.jsonl` | id (`c001`), anonymised number, `as_of`, tags, split | `record` |
| `../../snapshots/<name>/*.json` | frozen anonymised API responses (committed) | `record` |
| `golden.jsonl` | values **you** read from the live website, with date and source | you |
| `items.jsonl` | one item per company × question, expected field values | `build-items` (oracle + golden) |
| `flags.jsonl` | expected red flags per company | you (see `LABELLING.md`) |
| `abstention.jsonl` | fault-injection cases and expectations | `gen-abstention`, then you review |
| `injection.jsonl` | prompt-injection payloads (scored in Phase 4, M6) | `seed-injection` |

`items.jsonl` is **frozen on purpose**: a change in the oracle shows up as a diff, and `run` stops
with exit code 2 if it is stale.

## Build the real dataset (Phase 3 steps 3.3 to 3.7)

1. **Pick companies** (28 is the plan; at least 25). Every tag in `constants.REQUIRED_TAGS`
   needs its minimum, see `validate --strict`. Use Companies House search with a status filter
   to find the unusual ones (dissolved, strike-off proposal, members' voluntary liquidation...).
2. **Record** (needs `CH_API_KEY` in `.env`; about 25 requests per company):
   ```powershell
   uv run ukvet-evals record 00445790 --dataset v0.1 --public 00445790 --tags large-plc
   uv run ukvet-evals record 12056899 17016019 --dataset v0.1 --tags healthy-small,under-1-year
   ```
   Numbers become aliases (`91xxxxxx`), people become `PERSON 001`; the real-to-alias map lives in
   `data/raw/eval_mapping.json` (git-ignored; back it up privately). Large public companies passed
   with `--public` keep their identity, but people are still anonymised.
3. **Fix the split once**, before looking at any result:
   ```powershell
   uv run ukvet-evals choose-salt --dataset v0.1
   uv run ukvet-evals set-splits --dataset v0.1 --lock
   ```
4. **Golden labels**: for at least 25 companies, open each real company's page on the website and
   write 5 or more fields into `golden.jsonl` (format below). Do this *before* `build-items`.
5. **Build items** and read every disagreement: `uv run ukvet-evals build-items --dataset v0.1`.
   A disagreement is an oracle bug, a label slip or a real ukvet bug. Fix it and log it.
6. **Draft the other files**: `label-template`, `gen-abstention`, `seed-injection`; then label
   flags **by hand from `LABELLING.md`** and review every abstention expectation.
7. `uv run ukvet-evals validate --dataset v0.1 --strict` must say `OK`.

`golden.jsonl` row (one JSON object per line):
```json
{"company": "c014", "checked_on": "2026-10-24", "source": "find-and-update ... /company/00445790", "checker": "FO", "fields": {"Q1.status": "active", "Q4.accounts.next_due": "2027-06-30", "Q6.outstanding": 2}}
```
Valid field names are in `ukvet_evals/fields.py` (`FIELDS`).

## LLM runs (M2 / M4 on real model text)

```powershell
# 1. record once (spends pence; set LLM_PROVIDER / LLM_MODEL / LLM_API_KEY in .env)
uv run ukvet-evals run --dataset v0.1 --split dev --llm record
# 2. replay for free, any number of times, in CI
uv run ukvet-evals run --dataset v0.1 --split dev --llm replay --model claude-haiku-5-5
```
Answers are cached in `evals/llm_cache/<model>/` keyed by a hash of (model, system prompt, user
prompt). If the facts or the prompt change, replay fails with exit code 3 ("re-record") instead of
quietly scoring a template report. The cache holds text written about **anonymised** facts, so it
is committed.

**Judge (optional, never gates CI).** Use a *different model family* from the writer. Set
`JUDGE_PROVIDER`, `JUDGE_MODEL`, `JUDGE_API_KEY`, then add `--judge`. Calibrate it: hand-label 20
claims in a JSONL file (`{"key": "c014:2", "supported": false}`; the key is company id and claim
index, see `judge_rows` in results), then
`uv run ukvet-evals judge-agreement --results <results.json> --hand <hand.jsonl>`. Report the
agreement and the number of unsupported claims the judge approved.

## Reading the numbers honestly

- Every proportion has a Wilson 95% interval and its size. Quote the size with the number.
- M1 measures **retrieval and mapping against an independent oracle**, not "the truth about the
  company". The golden cross-check is what ties it to reality, so report how many fields it covers.
- M2 counts a claim as unsupported if the independent checker rejects it. That checker is stricter
  than production (it also checks names), so the report also shows how often the writer needed
  production's checker ("writer needed checker").
- M4 *mechanical* is close to 100% by design (bad claims are dropped before display); the
  informative number is the semantic one from the judge, and only with its agreement figure.
- M5 labels are yours: they reduce bias by being written from definitions **before** the rules are
  run, and by a second labeller on 20% of companies (`second_labeller_expected`).
- Replay timings exclude the network. Use `scripts/measure.py` for latency claims.
- Claims you may make after Phase 3 are listed in `docs/eval-report.md`.

## Python API (for notebooks)

```python
from pathlib import Path
import asyncio
from ukvet_evals.run import RunOptions, evaluate

res = asyncio.run(evaluate(RunOptions(root=Path("."), dataset="v0.1", split="dev")))
res["m1"]["by_question"]["Q4"]["fields"]  # {"k": 36, "n": 36, "rate": 1.0, "ci95": [...]}
```
---
---

## Results (Phase 3)
 
Dataset v0.1: 48 companies, 432 items, writer model `claude-haiku-5-5`, run on 27 Oct 2026. Intervals are Wilson 95%.
 
| Metric                                      | Target        | Result (95% interval)       | Size                  |
| ------------------------------------------- | ------------- | --------------------------- | --------------------- |
| M1 field accuracy vs independent oracle     | >= 90%        | 100.0% [99.7%, 100.0%]      | 1488 fields           |
| M2 unsupported claims (mechanical)          | < 2%          | 0.0% [0.0%, 0.9%]           | 421 claims            |
| M3 abstention under fault injection         | >= 90%        | 100.0% [91.0%, 100.0%]     | 39 cases              |
| M4 citation validity (mechanical)           | 100%          | 100.0% [99.1%, 100.0%]     | 421 claims            |
| M5 red-flag recall                          | >= 85%        | 100.0% [95.9%, 100.0%]     | 89 flags              |
| M7 latency, worst of 20 live runs (Phase 2) | < 30 s        | 5.9 s                       | 10 companies          |
| M8 cost per report (Phase 2)                | < £0.05       | about £0.0004               |                       |
 
**Read these honestly.** 100% shows the set is easy, not that ukvet is perfect.
 
- Ground truth was cross-checked by hand against the live website for **10 companies only**.
- Flag labels were drafted by script from written definitions and reviewed by one person (no second labeller).
- M2 and M4 are mechanical checks. Whether a cited fact truly supports a sentence, and whether wording is fair, was not measured.
- M6 prompt-injection resistance is not measured yet (15 cases are seeded for Phase 4).
- Results use frozen snapshots and one writer model.
Full report: `docs/eval-report.md`. How the evaluation was built, step by step: `development/phases/PHASE-3-EVAL.md`.