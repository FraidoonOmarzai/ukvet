# Golden labels and flag labels: how to make them

Where this fits: Phase 3, steps 3.6 (golden) and 3.9 (flags). Do these **after** recording the companies and locking the split, and **before** the first real eval run.

| Item | What it is | Why it exists |
|---|---|---|
| **Golden labels** | Values for a few fields per company that were checked against the Companies House website | Proves the oracle (expected values) is right, so M1 accuracy means something |
| **Flag labels** | The red flags you expect for each company, written from the written definitions | Lets M5 (red-flag recall and precision) be computed |

Files involved (all under `evals/datasets/v0.1/` unless stated):

| File | Written by |
|---|---|
| `golden.jsonl` | `scripts/golden_from_manual.py` or `scripts/golden_entry.py` |
| `flags.jsonl` | `ukvet-evals label-template`, then `scripts/flag_labeller.py` |
| `items.jsonl` | `ukvet-evals build-items` (rebuilds after golden changes) |
| `data/raw/eval_mapping.json` | `ukvet-evals record` (private, git-ignored, never commit) |

---

## 0. Before you start

- [ ] Companies are recorded: `uv run ukvet-evals validate --dataset v0.1` shows your companies, and `tags_missing` is empty.
- [ ] The split is locked: `choose-salt` then `set-splits --lock` were run once, before looking at any score.
- [ ] `.env` is not committed; `data/raw/` is git-ignored.

Handy view of which alias is which real company (keep the output private):
```powershell
uv run python scripts/golden_sheet.py
```

---

## Part 1: Golden labels

### What counts as golden
A row whose values were read from the **live Companies House website**, not from the snapshots and not from the oracle. If golden were copied from the snapshots it would always agree with the oracle and prove nothing.

### Option A: reuse your manual check (no new website visits)
`docs/accuracy-check.md` records 10 companies you compared with the website on 21 Oct 2026 (0 errors in about 75 values). `scripts/golden_from_manual.py` holds those verified values and writes the golden rows.

1. Make sure the 10 companies are in the dataset. Missing ones are printed by the script with the exact `record` command. The 10 numbers and suggested tags:

```powershell
uv run ukvet-evals record 00445790 --dataset v0.1 --public 00445790 --tags large-plc
uv run ukvet-evals record 17491796 --dataset v0.1 --tags under-1-year,no-psc
uv run ukvet-evals record 12115175 --dataset v0.1 --tags dissolved
uv run ukvet-evals record 01468547 --dataset v0.1 --tags liquidation-mvl,overdue-filings
uv run ukvet-evals record 12056899 --dataset v0.1 --tags strike-off-proposal,overdue-filings
uv run ukvet-evals record 17016019 --dataset v0.1 --tags under-1-year,charges-outstanding
uv run ukvet-evals record 03977902 --dataset v0.1 --tags corporate-psc,charges-outstanding
uv run ukvet-evals record 17313434 --dataset v0.1 --tags under-1-year
uv run ukvet-evals record 14189917 --dataset v0.1 --tags charges-outstanding
uv run ukvet-evals record 12204233 --dataset v0.1 --tags healthy-small
```
(Skip any that are already recorded. Needs `CH_API_KEY` in `.env`. About 25 requests per company.)

2. Write the golden rows:
```powershell
uv run python scripts/golden_from_manual.py --dataset v0.1 --checker FO
```
Run it again after recording the missing companies. It only adds or replaces these 10 rows.

### Option B: check more companies interactively
`scripts/golden_entry.py` asks for each value, **you type what the website shows**, and only then tells you whether the oracle agrees. It saves your value, never the oracle's.

```powershell
uv run python scripts/golden_entry.py c004 c005 --dataset v0.1 --checker FO
```
- Dates can be typed as `30 September 2027`. Overdue badges: `y` or `n`. Enter skips a field. `none` means the page shows nothing.
- Enter 5 or more fields per company. Skip Q3 and Q6 for any company whose recording was truncated at the fetch cap (the validate warning names them, for example `c031`).
- `DIFFERENT` means you and the oracle disagree. Press Enter to keep your value, or `r` to retype.

### Check the golden rows
```powershell
uv run ukvet-evals build-items --dataset v0.1
uv run ukvet-evals validate --dataset v0.1
```
- `golden_companies` should equal the number of companies you labelled.
- `build-items` prints a conflict for each field where golden and oracle differ. For every conflict:
  1. Re-read the page. A typo in your row is the commonest cause: fix it.
  2. If the company changed since the snapshot was recorded (a new filing or officer), it is a false alarm: re-record that company or drop the field.
  3. If you are sure of your value, open `evals/snapshots/v0.1/<number>.json` and find out why the oracle differs. That is a real finding: record it in the error analysis.

### Honest limits (put these in the write-up)
- Golden covers only the companies you checked (10 in the reduced version). Say "10-company golden subset", not "verified on the full set".
- `validate --strict` will keep warning that the golden set is smaller than the 25-company minimum. Do not change the minimum to hide it.
- Pages change daily, so golden values are only comparable with a snapshot recorded close to the check date (the rows record `checked_on`).

---

## Part 2: Flag labels

### What a flag label is
For each company, the list of red flags an analyst would expect, using only the written definitions in `evals/LABELLING.md`. M5 compares ukvet's actual flags to these.

Rule that keeps M5 honest: **label before you run the rules, and never change a label after seeing results without a note in `notes`.**

### Steps
1. Create the empty rows (one per company, `expected: null`):
```powershell
uv run ukvet-evals label-template --dataset v0.1
```
2. Draft and review the labels:
```powershell
uv run python scripts/flag_labeller.py --dataset v0.1 --labeller FO
```
`scripts/flag_labeller.py` reads the raw snapshots and applies the written definitions with its own code. It imports nothing from ukvet, so it does not copy the rules it will grade. For each company it shows the facts and a draft:
- **Enter** accepts the draft
- **`none`** means you expect no flags
- **`s`** skips the company
- A list such as `status:high,charges:low` replaces the draft (valid flag ids are in `evals/LABELLING.md`)

It saves after every company, so you can stop and resume. Add `--auto` to accept every draft, and `--only c040 c041` to limit it to some companies.

3. Check:
```powershell
uv run ukvet-evals validate --dataset v0.1
```
`flag_labelled` should be 20 or more (the minimum), ideally all companies.

### While reviewing each draft
- Does it match the table in `evals/LABELLING.md`? For example: a solvent (members' voluntary) liquidation is `status:medium`; a strike-off proposal is `strike_off:high`; a company under 1 year old is `age:medium`.
- If you think a definition is wrong, label by the definition and write your disagreement in `notes`. That is a finding about the rule.
- Officer appointments within 30 days of incorporation do not count towards `officer_turnover`.

### Second labeller (optional, about 20% of companies)
Ask a colleague to read `evals/LABELLING.md` and fill `second_labeller_expected` (a list of flag ids) for about 8 companies **without seeing your labels**. Agreement and kappa then appear in the report.

### Honest limits (put these in the write-up)
- The labels are drafted by a script from the written definitions and reviewed by one person. Say "labels drafted by script from the written definitions and reviewed by one person". Without a second labeller, M5 measures agreement with that reading, not independent expert judgement.
- Accepting every draft without reading it makes M5 weaker. Read at least the companies with several flags.

---

## Part 3: Finish

```powershell
uv run ukvet-evals build-items --dataset v0.1
uv run ukvet-evals validate --dataset v0.1
```

Expected end state:

| Check | Target |
|---|---|
| `golden_companies` | 10 (reduced) or 25 (full) |
| `flag_labelled` | 20 or more |
| Remaining warnings | truncated companies, and the golden minimum if you stayed at 10 |
| Output ends with | `OK` |

Then, and only then, run the evals for the first time. Do not edit labels afterwards without a note.

## Do not commit
`data/raw/eval_mapping.json`, the output of `golden_sheet.py`, `.env`, and any raw (unanonymised) recordings. Do commit `evals/datasets/v0.1/` and `evals/snapshots/v0.1/` once `validate` has passed the leak check.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Set CH_API_KEY` | `.env` is missing or not in the repo root |
| `record`: company not found | Check the number has 8 characters including leading zeros |
| `golden_companies` still 1 | The other companies are not recorded yet: run the `record` commands, then `golden_from_manual.py` again |
| `golden_from_manual.py` says a number is "not in your dataset" | Record it (command printed), then rerun |
| Conflict lines from `build-items` | See "Check the golden rows" above |
| `flag_labeller.py`: snapshot missing | Recording did not finish for that company: record it again |
| Splits are locked | Expected after `set-splits --lock`. New companies get their split from the same salt automatically |
