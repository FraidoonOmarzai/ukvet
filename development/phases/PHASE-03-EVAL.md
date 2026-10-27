# Phase 3: Evaluation (how we measure ukvet)

This guide is for someone who has never seen this project. Follow it top to bottom. Every step says **why** you do it, **what to run**, **where to run it**, **what you should see**, and **what can go wrong**.

All commands are PowerShell, run from the **repo root** (`C:\Users\44787\Desktop\ukvet`) unless a step says otherwise. There is no `make` on Windows; we use `uv run ...`.

---

## 1. Why Phase 3 exists

ukvet is a tool that looks up a UK company on Companies House and writes a due-diligence report (status, age, accounts, directors, charges, red flags). Before Phase 3 we had checked it by hand on 10 companies. That has three problems:

1. **It does not repeat.** Nobody can re-run "I looked at the website and it seemed fine".
2. **It does not protect us.** If a later change breaks something, nothing tells us.
3. **It gives no honest number.** "It works" is not a result. "1488 of 1488 fields matched, 95% interval 99.7% to 100%" is.

Phase 3 turns the manual check into a **repeatable, versioned measurement**:

- a fixed set of **48 real companies** saved as frozen, anonymised snapshots (so results do not change when Companies House changes, and no personal data is in the repo);
- a list of **questions** (Q1 to Q9) asked about each company, with **known correct answers**;
- **scorers** that compare ukvet's answers with the correct answers and produce metrics (M1 to M5, plus latency and cost);
- a **CI gate** that fails a pull request if the numbers get worse;
- a **report** that says what was measured, what was not, and what may be claimed.

If you remember one thing: *Phase 3 is how we prove, with numbers, that ukvet is right, and how we notice quickly when it stops being right.*

---

## 2. Words you will see

| Word | Meaning |
|---|---|
| **Item** | One question about one company (for example "Q3: how many officers?" for company c012). 48 companies x 9 questions = 432 items. |
| **Q1 to Q9** | The nine questions: status, age, officers, accounts and filings, PSCs, charges, insolvency, network, flags (see `evals/README.md` for exact wording). |
| **Snapshot** | A saved copy of the raw Companies House API answers for one company. Frozen: replayed instead of calling the live API. |
| **Anonymised** | Personal data replaced with fake names; real company numbers replaced with fake ones (`91...`). |
| **Alias** | The fake id of a company, like `c004`. The link real number to alias is in `data/raw/eval_mapping.json` (private). |
| **Oracle** | Expected values computed from the raw JSON by separate code that imports **neither** `ukvet_mcp` **nor** `ukvet_agent`. A test enforces this. It is the answer key. |
| **Golden** | Values you read yourself from the live Companies House website. They check the oracle. |
| **Flag labels** | The red flags an analyst should expect for each company, written from definitions in `evals/LABELLING.md`. |
| **as_of** | The frozen "today" used when replaying, so "company is 11 months old" does not change over time. |
| **Dev / test split** | Companies split by a salted hash. Dev is for fixing things. Test is looked at **once**, at the end, so we cannot tune to it. |
| **Baseline** | The saved numbers (`evals/baselines/v0.1.json`) the CI gate compares new runs against. |
| **Gate** | `ukvet-evals gate`: exits non-zero if a run is worse than the baseline. |
| **Tier 1 / Tier 2** | Tier 1 = free CI run in template mode (no LLM). Tier 2 = recorded LLM answers replayed (designed, not enabled). |
| **Wilson interval** | The 95% range a percentage could really be given the sample size. 100% of 10 is weak; 100% of 1488 is strong. |

### The metrics

| Metric | Measures | Target |
|---|---|---|
| M1 | Field accuracy against the oracle | >= 90% overall, each question >= 80% |
| M2 | Unsupported claims in model-written text | < 2% |
| M3 | Abstention: when data is missing, ukvet says so (fault injection) | >= 90% |
| M4 | Citation validity (mechanical: cited ids exist and match) | 100% |
| M5 | Red-flag recall (and precision) | recall >= 85% |
| M6 | Prompt-injection resistance | Phase 4, not measured here |
| M7 | Latency | worst < 30 s |
| M8 | Cost per report | < £0.05 |
| M12 | CI gate works | blocks regressions |

---

## 3. The design decisions in one paragraph each (ADR-009)

You will meet these rules again in the steps. They are here so nothing looks arbitrary.

- **D1, an item is one question about one company.** Small units give many data points and show exactly which question fails.
- **D2, three kinds of ground truth.** Golden (human, from the website), oracle (code, from raw JSON), and rule labels (flags, written from definitions *before* running the rules). Each checks a different thing, and none is copied from ukvet.
- **D3, frozen snapshots replayed through the real stack.** Same input every time, so a changed score means changed code, not a changed website.
- **D4, privacy.** Anonymise people, check for leaks, keep the mapping private. Large listed companies may stay public (`--public`).
- **D5, dev/test split chosen once and locked.** Looking at the test split needs a reason on the command line, which is logged.
- **D6, two CI tiers.** Free every time (Tier 1), recorded-LLM replay (Tier 2) so CI never needs a secret.

---

## 4. Rules that apply to every step

1. **Never commit** `.env`, `data/raw/eval_mapping.json`, `evals/results/`, raw (unanonymised) recordings, real director names, or the output of `scripts/golden_sheet.py`.
2. **Never look at the test split** before the final run. (`--split all` and `--split test` need `--confirm-test-split "reason"`.)
3. **Never edit a label or the baseline to turn a result green** without writing down why (decision log and a `notes` field). If you change something after seeing dev results, say so in the report.
4. **Label before you run.** Flag labels are written from the definitions before the rules are scored, otherwise M5 only proves the rules agree with themselves.
5. **No secrets in CI.**

---

## 5. Setup (once)

**Why:** every later step assumes the project installs, the tests pass and your API key is available.

```powershell
cd C:\Users\44787\Desktop\ukvet
uv sync --all-groups --all-packages
uv run pytest
```

- You need Python 3.12 (the project targets 3.12) and `uv`.
- Create `.env` in the repo root with `CH_API_KEY=<your Companies House key>`. Recording the LLM answers (Step 12) also needs your Anthropic key; see `.env.example` for the exact variable name.
- Expected: `pytest` ends with all tests passing (the evals package alone has 84).

If you see `Set CH_API_KEY`, `.env` is missing or not in the repo root.

---

## 6. Folder map

```text
evals/
  README.md                 how the harness works (read second)
  LABELLING.md              the written flag definitions (the "rules of the exam")
  GOLDEN-AND-FLAGS.md       detailed guide to golden and flag labels
  datasets/v0.1/
    companies.jsonl         one row per company: alias, tags, split
    golden.jsonl            your website-checked values
    flags.jsonl             expected red flags per company
    abstention.jsonl        fault-injection cases (missing data scenarios)
    injection.jsonl         prompt-injection payloads (scored in Phase 4)
    items.jsonl             the answer key, built by build-items
  snapshots/v0.1/           frozen anonymised raw API answers
  baselines/v0.1.json       the numbers CI compares against
  llm_cache/                recorded LLM answers (for replay)
  results/                  run outputs (private, git-ignored)
  src/ukvet_evals/          the harness code and the `ukvet-evals` command
scripts/
  golden_sheet.py           alias to real company number helper (private output)
  golden_from_manual.py     writes golden rows from the 10 hand-checked companies
  golden_entry.py           interactive golden entry for more companies
  flag_labeller.py          drafts flag labels from the written definitions
  officer_dates.py          shows officer events for one company
data/raw/eval_mapping.json  PRIVATE real number to alias map (git-ignored)
docs/adr/009-evaluation-design.md   the design decisions
docs/eval-report.md                 the final report
.github/workflows/evals.yml         CI: job `gate` and manual job `record-llm`
```

---

## 7. Step by step

Each step lists: **Why**, **Run**, **You should see**, **Done when**, **If it goes wrong**.

**Note:** Step by step code to add is also in `setup/phase-3-guide.md`

### Step 1. Prove the harness works on fake data

**Why:** before spending time on real data, confirm the machinery itself runs. The demo dataset is synthetic, so a failure here is a code problem, not a data problem.

```powershell
uv run ukvet-evals demo-build
uv run ukvet-evals run --dataset demo
```

**You should see:** a results table with metrics and no crash.
**Done when:** the run finishes. 
**If it goes wrong:** run `uv run pytest` and fix failures first. Do not continue with a broken harness.

---

### Step 2. Choose the companies

**Why:** a test set of only healthy companies would score high and prove nothing. We need awkward cases (dissolved, in liquidation, brand new, many directors). The set is chosen **on purpose to cover 19 tags**, not at random.

The minimum number of companies per tag:

| Tag | Min | Look for | How to find |
|---|---|---|---|
| `large-plc` | 3 | Big listed company | Search a famous name |
| `healthy-small` | 4 | Ordinary active small Ltd | Any ordinary company |
| `under-1-year` | 3 | Incorporated < 1 year ago | Advanced search, incorporation date filter |
| `1-to-2-years` | 2 | Incorporated 1 to 2 years ago | Same filter |
| `dissolved` | 3 | Status dissolved | Advanced search, status |
| `liquidation-mvl` | 2 | Liquidation, members' voluntary | Status liquidation; Insolvency tab |
| `liquidation-creditors` | 2 | Liquidation, creditors' voluntary | Same |
| `administration-or-receivership` | 2 | In administration or receivership | Status filter |
| `strike-off-proposal` | 2 | "Active - Proposal to Strike Off" | Status filter |
| `overdue-filings` | 3 | Red "overdue" accounts or confirmation statement | Overview page |
| `charges-outstanding` | 2 | Outstanding charges | Charges tab |
| `charges-all-satisfied` | 2 | All charges satisfied | Charges tab |
| `corporate-psc` | 2 | PSC is another company | People tab |
| `no-psc` | 2 | No PSC listed | People tab |
| `llp-or-sc-or-ni` | 3 | One LLP (`OC`), one Scottish (`SC`), one NI (`NI`) | Number prefix |
| `many-appointments-director` | 2 | Director with many other companies | Click an officer |
| `corporate-officer` | 2 | A company acts as director/secretary | People tab |
| `officer-changes-12m` | 3 | Directors joined or left this year | Officers tab |
| `address-change-12m` | 2 | Registered office changed this year | Filing history |

One company can carry several tags, so about 28 companies cover all of it (we ended with 48). Keep a spreadsheet so you do not record a company twice.

**Done when:** you have a list of company numbers with tags. Company numbers have **8 characters including leading zeros** (`03977902`, not `3977902`).

---

### Step 3. Record the companies

**Why:** this saves the frozen snapshots. It fetches about 25 API requests per company, anonymises people, replaces the real number with a fake alias, and writes a private mapping.

Run once per group of companies that share tags:

```powershell
# Large listed companies keep their real name: add --public with the same number
uv run ukvet-evals record 00445790 --dataset v0.1 --public 00445790 --tags large-plc

# Ordinary companies, several at once
uv run ukvet-evals record 12056899 17016019 --dataset v0.1 --tags healthy-small

# Several tags on one company: comma-separated, NO spaces
uv run ukvet-evals record 17313434 --dataset v0.1 --tags under-1-year,no-psc
```

**You should see:** a line per company such as `03977902 -> 91000090 (c004) recorded`.
**Done when:** every company on your list is recorded (check with Step 4).
**If it goes wrong:**
- `not found, skipped`: the number is wrong. Check leading zeros.
- `Set CH_API_KEY`: see Setup.
- Do not record the same company twice.

---

### Step 4. Validate, and back up the private mapping

**Why:** `validate` counts companies per tag and runs the **leak check** (no real personal names in the committed files). The mapping file is the only link between aliases and real companies; lose it and you cannot tell which company is which.

```powershell
uv run ukvet-evals validate --dataset v0.1
```

**You should see:** `companies` going up, `tags_missing` shrinking toward `{}`.
**Done when:** `tags_missing` is empty and there is no `LEAK` or `ERROR ... LEAK` line.
**Then:** copy `data\raw\eval_mapping.json` somewhere safe and private. It is git-ignored; never commit it.
**If you see LEAK:** stop. Do not commit. Find the file named in the message and fix the anonymisation first.

---

### Step 5. Fix the dev/test split (once)

**Why:** if you could pick which companies are "test" after seeing scores, you would unconsciously tune to them. A salted hash decides the split, and the lock stops anyone changing it.

```powershell
uv run ukvet-evals choose-salt --dataset v0.1
uv run ukvet-evals set-splits --dataset v0.1 --lock
```

**Done when:** each company has `dev` or `test` in `companies.jsonl` (we had 30 dev, 18 test).
**Rule:** run this once, after all companies are recorded and before you have seen any score. New companies added later get their split from the same salt automatically.

---

### Step 6. Golden labels (your own website check)

**Why:** the oracle is code I wrote. If it had the same bug as ukvet, the two would agree and M1 would prove nothing. Golden values come from **you reading the live website**, an independent source. Golden only checks the oracle; it is not scored itself.

Full detail is in `evals/GOLDEN-AND-FLAGS.md`. The short version:

**Option A, reuse the 10 companies already hand-checked on 21 Oct 2026** (what we did):

```powershell
# See which alias is which real company (output is PRIVATE, never commit or paste it)
uv run python scripts/golden_sheet.py

# Write the golden rows for the 10 checked companies
uv run python scripts/golden_from_manual.py --dataset v0.1 --checker FO
```

If the script says a number is "not in your dataset", it prints the exact `record` command. Run it, then rerun the script. Companies you recorded with `--public` (c001 to c003) show their real number in `companies.jsonl`, so `golden_sheet.py` matching 36 of 39 at first is normal.

**Option B, check more companies yourself:**

```powershell
uv run python scripts/golden_entry.py c004 c005 --dataset v0.1 --checker FO
```

Type what the **website** shows. Dates like `30 September 2027`, overdue badges `y`/`n`, `none` if nothing is shown, Enter to skip. The tool reveals the oracle value only after you typed yours, and saves **your** value. If it prints `DIFFERENT`, re-read the page: either you mistyped, the company changed since recording, or you found a real bug.

**Done when:** `uv run ukvet-evals validate --dataset v0.1` shows `golden_companies` equal to the number you checked (10 in our reduced version; the full plan wants 25).
**Honest limit:** with 10, write "10-company golden subset", never "verified on all 48". Do not lower the minimum in `validate` to hide it.

---

### Step 7. Build the answer key

**Why:** this creates `items.jsonl` (432 items) by combining the oracle with your golden rows. Where golden and oracle disagree it prints a **conflict**, which is how you find errors.

```powershell
uv run ukvet-evals build-items --dataset v0.1
```

**You should see:** a count of items and possibly warnings. Warnings about a company being truncated (for example c031 hit the 100-item cap for officers and charges) are expected; skip golden for that company's Q3 and Q6.
**For each conflict:**
1. Re-read the website. A typo in your row is the commonest cause.
2. If the company changed since recording, re-record it or drop that field.
3. If you are sure of your value, open `evals/snapshots/v0.1/<number>.json` and find out why the oracle differs. That is a real finding for the report.

**Done when:** no unexplained conflicts remain.

---

### Step 8. Flag labels

**Why:** M5 needs "which red flags should this company have?". The labels must come from the written definitions in `evals/LABELLING.md`, **before** you look at what the rules produce, otherwise the check is circular.

```powershell
# Create one empty row per company (expected: null)
uv run ukvet-evals label-template --dataset v0.1

# Draft and review labels
uv run python scripts/flag_labeller.py --dataset v0.1 --labeller FO
```

`flag_labeller.py` reads the raw snapshots and applies the written definitions with its own code (it imports nothing from ukvet). For each company it shows the facts and a draft. Press:

- **Enter** accept the draft
- **`none`** expect no flags
- **`s`** skip
- or type a list such as `status:high,charges:low` to replace the draft

Useful options: `--auto` (accept every draft; weaker, see below), `--only c040 c041`, `--diff` (only companies whose saved labels differ from a new draft), `--note "reason"` (stored in the row's notes).

While reviewing, check the definition table in `evals/LABELLING.md`. Examples: a members' voluntary liquidation is `status:medium`; a strike-off proposal is `strike_off:high`; a company under 1 year old is `age:medium`; appointments within 30 days of incorporation and **secretary changes** do not count towards `officer_turnover`.

**Done when:** `validate` shows `flag_labelled` of 20 or more (we labelled all 48).
**Honest limit:** labels are drafted by script and reviewed by one person. Say exactly that. Read at least every company that has several flags. A second labeller on about 20% of companies (filling `second_labeller_expected` without seeing your labels) would add an agreement figure; we did not.

---

### Step 9. Abstention and injection cases

**Why:** M3 checks that when data is missing or the API fails, ukvet says "I can't tell" instead of guessing. We create the cases by deliberately breaking inputs (fault injection). The injection cases are seeded now and scored in Phase 4.

```powershell
uv run ukvet-evals gen-abstention --dataset v0.1
uv run ukvet-evals seed-injection --dataset v0.1
```

`gen-abstention` writes **drafts**. Open `evals\datasets\v0.1\abstention.jsonl` and **read every expectation** (it prints "REVIEW every expectation"). A draft you did not read is not a test.

**Done when:** at least 20 abstention cases and 15 injection cases exist (we had 39 and 15).

---

### Step 10. Strict validation

**Why:** this is the checkpoint before the first score. `--strict` fails if any dataset minimum is not met, so you cannot start with a dataset that is too small.

```powershell
uv run ukvet-evals build-items --dataset v0.1
uv run ukvet-evals validate --dataset v0.1 --strict
```

Minimums: 25 companies, 200 items, 15 per question, 25 golden companies, 20 flag companies, 20 abstention cases, 15 injection cases.

**Expected end state:** `golden_companies` 10 (reduced) or 25 (full); `flag_labelled` 20 or more; remaining warnings only for truncated companies and the golden minimum if you stayed at 10; output ends with `OK`.
**From here on, do not edit labels without a note.**

---

### Step 11. First run on the dev split

**Why:** this is the first real measurement. It uses only the dev companies (test stays unseen) and template mode (no LLM), so it is free and fast.

```powershell
uv run ukvet-evals run --dataset v0.1 --split dev
```

**You should see:** a table of M1 to M5 with a verdict per metric.
**Done when:** it runs. It does not have to be green. **A first run that fails is normal and useful.** Go to Step 13 for failures.

---

### Step 12. Record and replay the LLM answers

**Why:** M2 and M4 measure text the model writes. Calling the model on every CI run would cost money and need a secret. So we call it **once**, save the answers keyed by a hash of the model and prompts, and **replay** them afterwards for free. A cache miss means the prompts changed, so the run exits with code 3.

```powershell
# Record once (needs your Anthropic key in .env; costs a few pence)
uv run ukvet-evals run --dataset v0.1 --split dev --llm record --model claude-haiku-5-5

# Replay as often as you like, free
uv run ukvet-evals run --dataset v0.1 --split dev --llm replay --model claude-haiku-5-5
```

Recorded answers are stored in `evals/llm_cache/claude-haiku-5-5/` and are committed so CI can replay them. Record the other split's answers the same way when you reach Step 15.

**Done when:** replay gives the same numbers as record, with no cache-miss exit.

---

### Step 13. Error analysis (turn failures into fixes)

**Why:** a failing metric is a lead, not an insult. Each failure has one of four causes, and the fix depends on which one:

| Cause | Example from this project | Fix |
|---|---|---|
| Bug in ukvet | wrong value returned | fix the code, add a test |
| Wrong label or oracle | label counted something the rule ignores | fix the label, **write why** |
| Scorer false positive | claim restated a caveat but was counted unsupported (M4 99.6%) | fix the scorer, add a test, **write why** |
| Definition and rule disagree | `officer_turnover` counted secretary changes in the labels but not in the rule | decide which is right, align them, **write why** |

Helper for officer questions (prints roles and dates, no names):

```powershell
uv run python scripts/officer_dates.py c032
```

After relabelling flags, use `--diff` so you only revisit companies whose labels changed:

```powershell
uv run python scripts/flag_labeller.py --dataset v0.1 --labeller FO --diff --note "secretary changes excluded (decision 43)"
```

**Rule:** never "fix" a result by quietly changing a label or the baseline. Every change after seeing dev results goes in the decision log and in the report's "Failures found on dev" table.
**Done when:** all dev metrics meet their targets, and every change is explained in writing.

---

### Step 14. The CI gate (so it cannot get worse unnoticed)

**Why:** a measurement nobody enforces is a one-off. The gate compares a new run to a saved baseline and fails the build if a metric drops. This is metric M12.

Create the baseline from a clean, explained dev run:

```powershell
uv run ukvet-evals gate --dataset v0.1 --update-baseline
```

Check a later run against it:

```powershell
uv run ukvet-evals gate --dataset v0.1
```

The gate fails when: M1 overall drops by more than 1 percentage point; any question falls below the 80% floor; any new field failure appears; M3 drops by more than 2 points or a previously passing case fails; M5 recall drops by more than 2 points; M4 mechanical is below 100%; M2 rises by more than 0.5 points. The baseline ignores `created_at`, `perf` and `judge_rows`.

Exit codes: `0` ok, `1` regression or failed validation, `2` dataset drift, `3` replay miss.

`.github/workflows/evals.yml` runs this on every pull request (job `gate`, Tier 1, no secrets). The manual job `record-llm` is for re-recording LLM answers. Tier 2 (recorded LLM gate) is designed but not enabled.

**Prove the gate works** (required before ticking the "CI blocks regressions" box):
1. Make a branch and deliberately break something (for example make a field mapper return the wrong value).
2. Push and open a PR. CI must go red on the `gate` job.
3. Close the PR without merging. Keep a screenshot or link as evidence.

**Before pushing, run the same checks CI runs:**

```powershell
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
```

---

### Step 15. The final run, including the test split (once)

**Why:** this is the one honest number. Dev results are optimistic because you tuned against them. Test companies were never used to fix anything.

Only do this when everything is finished: all dev fixes done, labels final, scorer final.

```powershell
uv run ukvet-evals run --dataset v0.1 --split all --confirm-test-split "milestone: final baseline" --llm replay --model claude-haiku-5-5
```

The reason string is written to a log. Look at test **once**. If it shows a problem, you may fix it, but report that you did and do not claim the test split as unseen afterwards.
**Done when:** you have the final metrics for all 48 companies with Wilson intervals. Record the git commit hash of this run.

---

### Step 16. Write the report and update the docs

**Why:** numbers without limits are marketing. The report states what was measured, what was not, and what may be claimed.

1. Copy the final results into `docs/eval-report.md`: results table (dev, test, all), failures found and fixes, "what 100% does and does not mean", "what this does not cover", the discipline section.
2. Update the README results table with intervals and set sizes.
3. Update the risk register (`docs/07-risks.md`) for R3, R7, R12, R15, R17, R18, R19.
4. Append decisions to `docs/kickoff/decision-log.md` (for example: secretary changes excluded; scorer treats caveats as support; golden reduced to 10; test split looked at once).
5. Tick `docs/PHASE-3-CHECKLIST.md`.
6. Send the weekly update to AAII.

---

### Step 17. Exit checklist

- [ ] ADR-009 and decision-log entries written
- [ ] Dataset v0.1: at least 25 companies and 200 items (we have 48 and 432)
- [ ] Golden set recorded (10 done, reduced on purpose, written down)
- [ ] Dev/test split fixed; test run once
- [ ] Scorers for M1 to M5 with unit tests
- [ ] At least 20 abstention cases and 20 flag-labelled companies
- [ ] 15 injection cases seeded
- [ ] CI Tier 1 blocks regressions (shown with a deliberately broken PR)
- [ ] Baseline published with misses and causes (`docs/eval-report.md`)
- [ ] README results table and risks updated
- [ ] Leak check passes; no keys or private files committed
- [ ] Weekly update sent

---

## 8. Where results ended up (v0.1, 27 Oct 2026)

48 companies (30 dev, 18 test), 432 items, writer `claude-haiku-5-5`.

| Metric | Target | Result |
|---|---|---|
| M1 field accuracy | >= 90% | 1488/1488, interval [99.7%, 100%] |
| M2 unsupported claims | < 2% | 0/421, interval up to 0.9% |
| M3 abstention | >= 90% | 39/39, interval [91.0%, 100%] |
| M4 citation validity (mechanical) | 100% | 421/421 |
| M5 red-flag recall | >= 85% | 89/89 |
| M7 latency | < 30 s | worst 5.9 s (20 live runs, Phase 2) |
| M8 cost per report | < £0.05 | about £0.0004 |

---

## 9. Honest limits (always include these)

- **100% means the set is easy, not that ukvet is perfect.** It did not find new retrieval bugs. A harder set would.
- **M1 is agreement with an oracle that one person wrote**, checked against the website on 10 companies only.
- **M5 labels** were drafted by a script and reviewed by one person; no second labeller. It measures consistency with the written definitions, not independent expert judgement.
- **M3 cases** come from a dependency table, so they test that the rules follow the table.
- **M2 and M4 are mechanical** (ids, dates, numbers, names, forbidden wording). Whether a cited fact truly supports a sentence, and whether wording is fair, was not measured (no judge). M6 injection is not measured.
- **Frozen snapshots, one writer model.** Live API changes and other models are not covered.

**May claim:** "ukvet matched an independent oracle on 1488 of 1488 fields (99.7% to 100%, Wilson 95%) on a versioned 48-company set; no model-written claim among 421 was unsupported by a mechanical check; all 39 fault-injection cases degraded as specified; 89 of 89 expected red flags were raised; ground truth cross-checked by hand for 10 companies; CI blocks regressions."

**Do not claim:** "100% accurate", accuracy against reality beyond the 10 checked companies, a hallucination rate for sentence meaning, fair wording, or injection resistance.

---

## 10. Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `Set CH_API_KEY` | `.env` missing or not in the repo root |
| `record`: not found, skipped | Wrong company number; keep all 8 characters and leading zeros |
| `validate` shows `LEAK` | Stop, do not commit; fix anonymisation for the named file |
| `tags_missing` not empty | Record more companies with those tags |
| `golden_companies` stuck at 1 | The other companies are not recorded yet; run the printed `record` commands, rerun `golden_from_manual.py`, then `build-items` |
| `golden_sheet.py` matches fewer than all | `--public` companies show their real number in `companies.jsonl`; this is normal |
| Conflict lines from `build-items` | See Step 7 |
| `flag_labeller.py`: snapshot missing | Recording did not finish for that company; record it again |
| Splits are locked | Expected after `set-splits --lock` |
| `run` exits with code 3 | Replay miss: prompts or model changed since recording; re-record (Step 12) |
| `run` exits with code 2 | Dataset drift: snapshots or items changed; rebuild items, review the change |
| `--split all` refuses to run | Pass `--confirm-test-split "reason"`; this is intentional |
| CI ruff or mypy fails | Run `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy` locally and fix before pushing |
| `gate` fails | Read which metric dropped. Real regression: fix the code. Intended change: re-baseline with a decision-log entry, never silently |

---

## 11. The order in one glance

1. `uv sync`, `pytest`, demo run
2. Choose companies and tags
3. `record`
4. `validate` (leaks), back up the mapping
5. `choose-salt`, `set-splits --lock`
6. Golden labels
7. `build-items`, resolve conflicts
8. `label-template`, `flag_labeller.py`
9. `gen-abstention`, `seed-injection`
10. `validate --strict`
11. `run --split dev`
12. LLM `record` then `replay`
13. Error analysis
14. `gate --update-baseline`, prove it with a broken PR
15. Final `run --split all --confirm-test-split "..."` (once)
16. Report and docs
17. Checklist
