# ukvet Phase 3: Evals. Complete roadmap

| | |
|---|---|
| Owner | Fraidoon Omarzai |
| Written | 22 Oct 2026 |
| Plan reference | `docs/09-plan.md` (Phase 3 target: 200+ item dataset, M1 to M5 reported, CI gate live), `docs/04-success-metrics.md` |
| Estimated effort | About 10 working days (the plan allows 2 weeks). Every step below is one day of work or less |
| Rule from the plan | Cut scope inside the phase. **Never skip Phase 3** |

---

## 1. Why Phase 3 exists, and what it must prove

Right now you can say "it worked on 10 companies and I found no errors in about 75 values". A hiring manager will ask "how do you know it keeps working, and how accurate is it?". Phase 3 turns your manual check into a **repeatable, versioned measurement**, so every later change (a rule, a prompt, a model) is judged by numbers, not by feel.

Phase 3 is done when you can publish a table of **M1 to M5 against their targets, including misses**, with the dataset size beside each result, and CI blocks changes that make those numbers worse.

**Not in Phase 3:** Langfuse tracing and the prompt-injection score M6 (Phase 4; you only *seed* injection cases now), and the second model comparison (Phase 5).

---

## 2. Where you start (what you already have)

| Already in hand | Use in Phase 3 |
|---|---|
| 10 real companies manually verified (`docs/accuracy-check.md`) | The first 10 "golden" companies |
| Deterministic pipeline: facts (`facts.py`), rules (`redflags.py`), citation checker (`citations.py`) | Each layer can be scored on its own |
| `Deps.clock` and `service.today` can be injected | Freeze "today" so overdue and age results do not drift |
| `scripts/offline_demo.py` serves recorded JSON through the real stack with `respx` | The replay mechanism for snapshots |
| `scripts/record_fixtures.py` + `anonymise.py` | Record and anonymise real responses |
| `scripts/measure.py` | Starting point for the runner |
| Haiku works (20 of 20 narratives) | The first model to evaluate |

### Carry-over fixes to do first (from the audit, `PROJECT_GUIDE.md`)
| Fix | Why it blocks Phase 3 |
|---|---|
| **F2: `citation_stats` records only the last LLM attempt** | M2 and M4 depend on it. Record stats **per attempt**, and count LLM errors separately from checker violations |
| F1: release workflow installs without Streamlit | Not an eval blocker, but a one-line fix; do it now so CI is honest |
| Decide the Google secretary-change flag (open item in the decision log) | Rules should be settled before you label "expected flags" |
| README overclaims Evals and Langfuse | Fix before the repo goes public |

---

## 3. The design decisions (read this before building)

Decide these once, write them in **ADR-009: Evaluation design**, and log them in the decision log.

### D1. What is an "item"?
The plan wants 200+ items with at least 15 per category. Define an item as **one question about one company**:
`28 companies x 9 questions (Q1 to Q9) = 252 items`. On top of that:
- **Q10 red-flag cases:** at least 20 companies with labelled expected flags (M5).
- **Abstention cases:** at least 20 fault-injected runs (M3).
- **Injection cases:** at least 15 adversarial names and texts (seeded now, scored in Phase 4).

### D2. Where does ground truth come from? (the honest answer)
If the "truth" is the Companies House API and your system also reads the API, a shared misunderstanding passes silently. Use three tiers, and say so in the write-up:

| Tier | Source | What it proves |
|---|---|---|
| **Golden** (hand-verified in the browser) | You, on the live website, 25 companies by the end (10 done) | The oracle is right |
| **Oracle** (auto-generated expected values) | A small, separate script that reads the raw API JSON **without using the project's mappers or MCP code** | The pipeline (client, mappers, facts) is right, at scale |
| **Rule labels** | You label expected red flags from the written definitions **before** looking at the rule output | The rules do what a reasonable analyst expects (M5) |

Check the oracle against the golden set. Any disagreement is a bug in the oracle or a label error: fix and log it.

### D3. Freeze the world
- Record each company's **raw API responses once** (anonymised), with an `as_of` date.
- Replay them through the real stack (`respx` + in-memory MCP, as in `offline_demo.py`) with the clock set to `as_of`.
- Result: runs are free, fast, identical every time, and need no API key. This is also what makes CI possible.
- The cost: replay does not test live API behaviour. Keep a small live smoke test (the 10 manual companies) separate.

### D4. Privacy of the eval data
Director names, birth dates and addresses are personal data (UK GDPR; your `06-legal-and-ethics.md`). The dataset is public, so:
- Reuse `scripts/anonymise.py`: people are anonymised; company names too, except large public companies passed with `--public`.
- Keep the **real-number to fake-number mapping** in `data/raw/` (git-ignored) so you can re-record later.
- Never commit raw snapshots.

### D5. Dev and test split (prevents fooling yourself)
- Split companies by a fixed hash: **60% dev, 40% test**, decided once.
- Tune rules and prompts **only on dev**. Look at the test split once per milestone.
- If you ever change something after seeing test results, say so in the write-up.
- Without this, a "90% accuracy" claim is not trustworthy.

### D6. Two tiers of checks in CI
| Tier | Content | When | Cost |
|---|---|---|---|
| **1 (offline)** | Retrieval (M1), rules (M5), abstention (M3), template narrative checks, scorer unit tests | Every PR | Free, about 1 to 2 minutes |
| **2 (LLM)** | M2 and M4 with a real model | Cached replay on PRs; real calls only on manual or scheduled runs | A few pence |

LLM output varies between runs, so Tier 2 **replays recorded responses** keyed by the hash of the prompt and the model. If facts or prompts change, the cache misses and the job tells you to re-record (manually, with your key).

---

## 4. Metrics: exactly how each is computed

| ID | Target | Computed how | Honest caveat |
|---|---|---|---|
| **M1 accuracy** | >= 90% overall, >= 80% in **each** of Q1 to Q9 | Field-level: for each item, compare each checkable field in the pipeline's facts with the oracle (and golden). M1 = correct fields / checked fields, per category and overall. Also report item-level pass rate (all fields right) | Measures retrieval and mapping, so it is rule-based with no LLM involved. Report the field list |
| **M2 hallucination** | < 2% | Over the final narrative's claims: share not supported by the cited facts. Deterministic part: dates, numbers and **names** must appear in the cited facts (stricter than today's checker, which ignores names). Semantic part: LLM judge, hand-checked on a sample | About 250 claims per model run, so 2% is 5 claims: report a confidence interval, not just a point |
| **M3 abstention** | >= 90% | Fault injection: make tools fail (timeouts, 5xx, 404, empty). Expected: the question becomes a **gap**, no fact is invented, and `insufficient_data` appears when 3 or more questions fail with no high flag | Mostly deterministic, because the Verifier is code |
| **M4 citation validity** | 100% | (a) Mechanical: every shown claim cites existing facts whose values match, checked by a separate re-implementation of the checker. (b) Semantic: does the cited fact actually support the sentence (judge + hand sample) | (a) is nearly guaranteed by design, because failing claims are dropped. The real signal is (b). Say so |
| **M5 red-flag recall** | >= 85% | Expected flags (your labels) found by the rules, over all expected flags. **Also report precision** (unexpected flags), because R17 is about unfair flags | You wrote the rules and the labels: reduce bias with D2 and a second labeller on 20% |
| M6 injection | >= 95% | Seed the cases now; score in Phase 4 | |
| M7 to M9 | p95 < 30 s, < £0.05, track calls | Re-measure on the full run | Say "worst of N" if N is small |
| M12 | gate | CI blocks regressions (section 10) | |

**Always show the set size** beside every number (reporting rule 3 in `04-success-metrics.md`).

---

## 5. The layers (what each score tells you when it fails)

Because retrieval is deterministic, a failure points to a specific layer. This is a strong point for the write-up.

| Layer | Question | Failure means |
|---|---|---|
| 1. Retrieval | Do the facts match the oracle? (M1) | Mapper, client or fact-builder bug |
| 2. Rules | Are the right flags raised, and only those? (M5) | Rule threshold or logic problem |
| 3. Abstention | Does it admit missing data? (M3) | Gap or risk-level logic problem |
| 4. Writing | Are the LLM's sentences supported? (M2, M4) | Prompt or model problem |
| 5. Quality (optional) | Is it clear and fair? (judge) | Wording problem |

---

## 6. Repository layout

Make it a workspace package so imports are clean (your `tests/` taught you the cost of `sys.path` tricks):

```
evals/
  pyproject.toml                 # workspace member "ukvet-evals"
  ukvet_evals/
    schema.py                    # item and result models (pydantic)
    snapshot.py                  # record and replay raw API JSON, frozen clock
    oracle.py                    # independent expected-value computation
    scorers/{retrieval,flags,abstention,narrative}.py
    faults.py                    # fault-injecting tool client
    judge.py                     # LLM judge (rubric)
    stats.py                     # Wilson interval, per-category tables
    run.py                       # CLI runner
    report.py                    # results.json and results.md
  datasets/
    v0.1/companies.jsonl         # company list, tags, split, as_of
    v0.1/golden.jsonl            # hand-verified values
    v0.1/flags.jsonl             # expected red flags
    v0.1/abstention.jsonl
    v0.1/injection.jsonl
  snapshots/v0.1/*.json          # anonymised raw API responses (committed)
  baseline.json                  # committed scores the CI gate compares with
  results/                       # run outputs (small; commit only milestone runs)
tests/evals/                     # unit tests for scorers, oracle, stats
```

---

## 7. Dataset specification

### 7.1 Companies (target 28, minimum 25)
Pick companies with **tags**; every tag needs at least 2 companies (3 for the big ones). One company can carry several tags.

| Tag | Min | Why |
|---|---|---|
| large listed plc | 3 | many directors, many appointments, PSC exempt |
| healthy small Ltd | 4 | the normal case, no flags |
| incorporated < 1 year | 3 | age flag, "not recorded" filings |
| 1 to 2 years old | 2 | age boundary |
| dissolved | 3 | status, cessation date |
| liquidation: members' voluntary | 2 | the unfairness you fixed |
| liquidation: creditors' | 2 | must stay HIGH |
| administration / receivership | 2 | other failed statuses |
| active proposal to strike off | 2 | the missing rule you fixed |
| overdue accounts or confirmation statement | 3 | Q4 |
| charges: several outstanding | 2 | Q6 |
| charges: all satisfied | 2 | Q6 |
| corporate PSC | 2 | Q5 |
| no PSC / exempt | 2 | "no data is a fact" |
| LLP, Scottish (SC), Northern Ireland (NI) | 1 each | number formats |
| director with many other appointments | 2 | Q8 and the 5-director cap |
| corporate director or secretary | 2 | role edge cases |
| officer changes in last 12 months | 3 | Q9 |
| registered office changed | 2 | Q9 |

**Your 10 verified companies are the seed.** Find the rest with Companies House search (filter by status) and the `search_company` tool. Record the **real** number in a private file; the dataset stores the anonymised id.

### 7.2 Item format (example)
```json
{
  "id": "c014-Q4",
  "company": "c014",
  "question": "Q4",
  "as_of": "2026-10-21",
  "split": "dev",
  "fields": {
    "accounts.overdue": false,
    "accounts.next_due": "2027-06-30",
    "accounts.last_made_up_to": "2025-09-30",
    "confirmation.overdue": false,
    "confirmation.next_due": "2027-09-25"
  },
  "label_source": "oracle+golden",
  "notes": ""
}
```
Fields per question (start with these): **Q1** status, status detail, cessation date. **Q2** incorporation date, age in days. **Q3** number of current directors, their appointment dates. **Q4** overdue flags and due and last dates. **Q5** number and kind of current PSCs. **Q6** total, outstanding, satisfied counts. **Q7** number of cases, types. **Q8** per checked director: number of other appointments and status counts. **Q9** appointments and resignations in the window, address-change count.

### 7.3 Labelling rules (write them down; they are part of the deliverable)
1. Oracle values come from raw API JSON by code that does not import `ukvet_mcp` or `ukvet_agent`.
2. Golden values are read from the live website page by you, with the date.
3. Expected red flags are labelled **from the written flag definitions**, before you run the rules on that company.
4. Dates are ISO; names are never stored.
5. Any change to a label after seeing results is logged with a reason.
6. Second labeller (an AAII colleague) on 20% of flag labels; report agreement.

---

## 8. The step-by-step roadmap

| Step | Task | Output | Done when | Time |
|---|---|---|---|---|
| **3.0** | **Prerequisites**: fix F2 (per-attempt stats; LLM errors counted separately), F1 (release workflow), decide the Google secretary flag, README honesty fixes | PR merged, tests green | `citation_stats` shows per-attempt data; reproduced case from the audit now shows the first attempt's violations | 0.5 day |
| **3.1** | **ADR-009: evaluation design** (decisions D1 to D6), decision log #37+, risk R18 (label bias) and R19 (overfitting to the dev set) | `docs/adr/009-*.md` | Reviewed once by you the next morning | 0.5 day |
| **3.2** | **Schema and guidelines** (backlog: "Eval dataset schema and guidelines"): `schema.py`, labelling rules, field lists per question | Pydantic models + `evals/README.md` | A sample item validates; rules are written | 0.5 day |
| **3.3** | **Pick the companies**: 28 with tags, split dev/test by hash | `companies.jsonl` | Every tag meets its minimum | 0.5 day |
| **3.4** | **Record snapshots** (anonymised) with `record_fixtures.py` extended for the eval set: all 8 endpoints per company, `as_of` date stored, real to fake map kept private | `snapshots/v0.1/*.json` | A leak check finds no names, birth dates or addresses; replay runs offline | 1 day |
| **3.5** | **Replay harness**: `snapshot.py` serves the JSON through the real MCP and agent with the frozen clock | A function `run_company(id)` returning a `Report` | The 10 manual companies give the same facts as your live reports | 0.5 day |
| **3.6** | **Golden labels**: verify 15 more companies on the website (5 key fields each) | `golden.jsonl` (25 total) | Each row has a date and source | 1 day (hand work) |
| **3.7** | **Oracle** (independent of project code) and **oracle vs golden check** | `oracle.py`, `items.jsonl` generated | Oracle matches golden on every checked field, or each difference is explained and fixed | 1 day |
| **3.8** | **Retrieval scorer (M1)**, per-category table, Wilson intervals, unit tests including a deliberately broken mapper to prove the scorer catches it | `scorers/retrieval.py` | Baseline M1 printed per Q1 to Q9 with set size | 1 day |
| **3.9** | **Red-flag cases and scorer (M5)**: label expected flags, recall and precision, second labeller on 20% | `flags.jsonl`, `scorers/flags.py` | Recall and precision per flag type | 1 day |
| **3.10** | **Abstention cases and scorer (M3)**: `faults.py` injects timeouts, 5xx, 404 and empty results per tool and in combination | `abstention.jsonl`, `scorers/abstention.py` | At least 20 cases; each expected gap and risk level written | 1 day |
| **3.11** | **Runner and results report**: model ID, dataset version, git commit, as_of, split, seed in every result; `results.json` plus a readable `results.md` | `run.py`, `report.py` | One command produces the full report in template mode (no key) | 0.5 day |
| **3.12** | **Narrative scoring (M2, M4)**: stricter name/date/number check, independent re-implementation of the citation checker, per-attempt stats; run Haiku over the dataset (cache the responses) | `scorers/narrative.py` | Per-claim results saved; cost and time per run recorded | 1 day |
| **3.13** | **LLM judge + calibration**: rubric (support, neutrality, clarity); judge from a **different model family** than the writer; hand-judge 20 outputs and report agreement | `judge.py`, agreement number | Agreement reported; the judge never gates CI | 1 day |
| **3.14** | **CI gate** (section 10): Tier 1 on every PR, Tier 2 cached; `baseline.json` | Workflow file, passing and failing demo PRs | A PR that breaks a mapper is blocked; one that does not change scores passes | 1 day |
| **3.15** | **Error analysis and tuning on dev only**: classify every failure (retrieval, mapper, rule, writing, label error); fix the top causes with a test first; re-run dev | Error table in `docs/eval-report.md` | Each failure has a cause; fixes logged | 1 day |
| **3.16** | **Final baseline** (committed version): full run on dev **and** test, every metric vs its target, **including misses** with cause and proposed fix; update README Results, risks R3, R12, R15, R17; decision log | `docs/eval-report.md`, README table | Section 12 checklist is ticked | 1 day |

Total: about 12 working days if nothing slips. If time is tight, cut in this order: judge (3.13), second labeller, scheduled Tier 2 runs. **Do not cut** the dev/test split, the golden check or the CI gate.

---

## 9. Scoring details worth getting right

- **Field comparison:** exact match for dates, counts and booleans. For lists (current directors), compare as sets of (appointed date, role) because names are anonymised.
- **Per-category floor:** M1 must be at least 80% in **each** of Q1 to Q9; an average can hide a failing category.
- **Intervals:** use the Wilson interval for every proportion. With 252 items, a result of 92% still has an interval of about plus or minus 3 points.
- **Q8 and the cap:** the pipeline checks the first 5 directors. The oracle must apply the same cap, otherwise every large company fails. Record the cap in the dataset notes.
- **Flag precision:** list each unexpected flag with the company's tag, so unfair patterns (like the members' voluntary liquidation one) show up.
- **Claim extraction for M2:** for template narrative each finding is one claim; for the LLM each sentence is one claim. Report totals so the percentage can be reproduced.
- **Different judge family:** a model judging its own output tends to approve it.
- **Reproducibility:** every result file records dataset version, git commit, model ID, `as_of`, seed and set size.

---

## 10. The CI regression gate (M12)

**Tier 1, every PR, offline, free:**
1. Replay all dev and test companies in template mode.
2. Compute M1 (overall and per category), M3, M5 recall/precision, template-claim checks.
3. Compare with `evals/baseline.json`. **Fail** the PR if:
   - M1 overall drops by more than 1 percentage point, or any category falls below its floor (80%);
   - M3 or M5 recall drops by more than 2 points;
   - any mechanical citation check fails (must be 100%).
4. Post a short results table as a PR comment.

**Tier 2, LLM:**
- On PRs, replay cached model responses. If the prompt or facts changed (cache miss), the job fails with "re-record needed".
- A manual workflow (secret `LLM_API_KEY`, spending cap on the key) re-records and refreshes M2 and M4.
- Gate: M2 must not rise by more than 0.5 points; the mechanical M4 must stay 100%.

**Updating the baseline** only through a PR that says why, plus a decision log entry. Never edit the baseline to make a red build green.

---

## 11. Results report (what you publish)

```
Dataset v0.1: 28 companies, 252 items (dev 60% / test 40%), 22 red-flag cases, 21 abstention cases
Model: <exact id>, as_of 2026-10-xx, git <sha>

Metric                      Target     Dev      Test     n        Met?
M1 accuracy overall         >= 90%     ..%      ..%      ...      ...
  per category Q1..Q9       >= 80%     table
M2 hallucination            < 2%       ..%      ..%      ... claims
M3 abstention               >= 90%     ..%      ..%      21 cases
M4 citation validity        100%       mech ..% / semantic ..%
M5 red-flag recall          >= 85%     ..%      ..%      ... flags
   red-flag precision       tracked    ..%
M7 latency (worst/p95)      < 30 s     ..
M8 cost per report          < 0.05 GBP ..
```
Rules: report **every** metric including misses; for each miss give the likely cause and the fix; never report only the best run; report the committed version; say what the test split was used for.

---

## 12. Exit checklist (Phase 3 is closed when all are ticked)

- [ ] F2 fixed; per-attempt citation stats recorded
- [ ] ADR-009 written; decisions in the decision log
- [ ] Dataset v0.1: 25+ companies, 200+ items, at least 15 items per question category
- [ ] Golden set (25 companies) verified by hand; oracle agrees with it
- [ ] Dev/test split fixed; test split used once for the final baseline
- [ ] Scorers for M1 to M5 with unit tests (including a broken-mapper test)
- [ ] 20+ abstention cases and 20+ red-flag cases
- [ ] 15+ injection cases seeded for Phase 4
- [ ] CI Tier 1 blocks regressions (shown with a deliberate failing PR)
- [ ] Baseline results published, every metric against its target, misses explained
- [ ] README Results table filled; risks R3, R12, R15, R17 updated; new R18 and R19
- [ ] No personal data in the dataset (leak check passes); no keys committed
- [ ] Weekly update and Friday demo to AAII

---

## 13. Risks specific to Phase 3

| Risk | Mitigation |
|---|---|
| **Circular ground truth**: the oracle and the system misread the API the same way | Golden hand-checked set; oracle independent of project code (D2) |
| **Label bias**: you wrote both the rules and the expected flags | Label from definitions first; second labeller on 20% |
| **Overfitting to the eval set** | Dev/test split; test used once per milestone (D5) |
| **Small samples** | Wilson intervals; say "n"; do not over-read one point |
| **LLM variation** | Cached replay in CI; 3 runs for the baseline; report the spread |
| **Personal data in a public dataset** | Anonymiser, leak check, private mapping file |
| **Cost** | Template mode is free; cache LLM responses; set a spending cap on the key |
| **Scope creep** (judge for everything, huge dataset) | The cut order in section 8; the plan's "cut scope inside the phase" |
| **Snapshots drift from the live API** | Keep the 10-company live smoke test; re-record on API changes |

---

## 14. Mapping to your GitHub backlog (`scripts/backlog.tsv`)

| Existing issue | Roadmap step |
|---|---|
| Eval dataset schema and guidelines | 3.2 |
| Build ground-truth dataset (200+ items) | 3.3 to 3.7 |
| Missing-data and abstention cases | 3.10 |
| Red-flag cases for Q10 | 3.9 |
| Rule-based scorers | 3.8, 3.12 |
| LLM-as-judge for report quality | 3.13 |
| Eval runner and results report | 3.11 |
| Eval regression gate in CI | 3.14 |
| Baseline results | 3.16 |

**Add these issues:** F2 per-attempt stats (3.0), ADR-009 (3.1), golden verification (3.6), error analysis (3.15), snapshot recording and anonymisation (3.4), replay harness (3.5), oracle (3.7). Keep the plan's rule: each issue is one day or less.

---

## 15. What you can claim when Phase 3 is done

Only what the report shows, for example: "On a versioned 28-company, 252-item evaluation set with hand-verified ground truth, the system scored X% field accuracy (per-category minimum Y%), Z% correct abstention and a hallucination rate of W% (95% interval ...), and CI blocks regressions." Also say what the set does **not** cover (company types you did not include, live-API behaviour, only one model). Misses stated plainly are a strength, not a weakness.

---

## 16. First three things to do tomorrow

1. Do step 3.0 (the F2 fix and the one-line release workflow fix) so the numbers you build on are honest.
2. Write ADR-009 from section 3 (30 minutes). It forces the decisions before the code.
3. Start the company list (3.3) in a spreadsheet: for each tag, find the companies. The golden hand-checking (3.6) is the slowest step, so start collecting candidates early.

Say "start 3.0" and I'll build the F2 fix with tests, or "start 3.2" and I'll write the schema, the labelling guide and the project skeleton.

---
---

The full spec is in `PHASE-3-ROADMAP.md`. Below is the order to work in, as the actions you take each day. Your computer is no longer linked to this session, so I can't touch your repo directly. I'll write the code in my workspace copy and send it as zips, as before.

## Day 1: prerequisites and decisions (step 3.0 and 3.1)
1. Create a branch: `git checkout -b phase-3`.
2. Fix F2: record citation stats per attempt, and count LLM errors separately from checker violations (`reporter.py`, around lines 113-120). Write a test first for the case where attempt 1 is bad and attempt 2 is clean.
3. Fix F1: in `release-mcp.yml`, change the install to `uv sync --all-groups --all-packages`.
4. Fix the README (lines 8, 33-34): remove the Evals and Langfuse claims and update the test count.
5. Decide the Google secretary-flag question. I recommend ignoring corporate-secretary changes. Then re-run `uv run pytest`.
6. Write ADR-009 (design decisions D1 to D6 from the roadmap) and add decision-log entries.

Done when CI is green and the ADR is committed.

## Day 2: skeleton and company list (3.2 and 3.3)
1. Create `evals/ukvet_evals/` as a uv workspace member. Add `schema.py` with pydantic models for items, flags, abstention cases and results.
2. Write `evals/README.md` with the labelling rules.
3. Build the company list in a spreadsheet with 28 companies. Every tag in section 7.1 needs its minimum count.
4. Split dev and test with a fixed hash, in code, so it can't drift. Save the result as `companies.jsonl`.

Use Companies House search with a status filter to find the odd cases: dissolved, strike-off proposals, MVL and creditors' liquidation.

## Days 3-4: snapshots and replay (3.4 and 3.5)
1. Extend `record_fixtures.py` to record all 8 endpoints for each company. Store the `as_of` date, and keep the real-to-fake number map in git-ignored `data/raw/`.
2. Run `anonymise.py`, then a leak check. It should grep for director names, birth dates and addresses and find none.
3. Write `snapshot.py`. It serves the JSON through the real stack with `respx`, with the clock frozen at `as_of`, as in `offline_demo.py`.
4. Check: your 10 manual companies must produce the same facts as your live reports.

## Days 5-6: ground truth (3.6 and 3.7)
1. Hand-verify 15 more companies in the browser, 5 key fields each, with the date. This is the slowest step. Start it early in the week, in small sittings.
2. Write `oracle.py`. It must not import `ukvet_mcp` or `ukvet_agent`.
3. Compare the oracle with the golden set. Every difference is either an oracle bug, a label error or a real product bug. Fix it and log it.
4. Generate `items.jsonl` (at least 200 items, 15 or more per Q1 to Q9).

## Day 7: first scores (3.8 and 3.11)
1. Write the retrieval scorer for M1, with per-category tables and Wilson intervals.
2. Add a unit test that breaks a mapper on purpose and proves the score drops.
3. Write `run.py` and `report.py`. They should record the dataset version, git commit, model ID, `as_of`, seed and n.
4. Run `uv run python -m ukvet_evals.run --split dev`. This is your first dev M1 number.

## Day 8: flags and abstention (3.9 and 3.10)
1. Label expected flags from the written definitions before you run the rules on those companies. Get a colleague to label 20% as a check.
2. Score recall and precision. List every unexpected flag.
3. Write `faults.py` (timeouts, 5xx, 404, empty results). Write 20+ abstention cases, each with the expected gap and risk level, then the scorer for M3.

## Day 9: narrative scoring (3.12 and 3.13)
1. Add a stricter claim check (names, dates, numbers) and an independent re-implementation of the citation checker.
2. Run Haiku over the dataset with response caching, and record cost and time.
3. If time allows, add the LLM judge from a different model family, and hand-judge 20 outputs. This is the first thing to cut.

## Day 10: the CI gate (3.14)
1. Commit `baseline.json` from the dev run.
2. Add the Tier 1 workflow: it replays all companies in template mode and fails on the thresholds in section 10.
3. Prove the gate works. Open a PR that breaks a mapper and confirm it is blocked. Open one that changes nothing and confirm it passes.

## Days 11-12: error analysis and baseline (3.15 and 3.16)
1. Classify every dev failure as retrieval, mapper, rule, writing or label error. Fix the top causes test-first, on dev only.
2. Run the final baseline once on dev and test. Don't change anything after seeing the test numbers.
3. Write `docs/eval-report.md` with every metric against its target, including misses, causes and fixes. Fill the README results table and update R3, R12, R15 and R17.
4. Tick the section 12 checklist, push, and send your weekly update to AAII.

## Rules to hold to throughout
- One issue per day or less, as in your plan.
- Commit after each step.
- Never edit a label or the baseline to turn a result green without a log entry saying why.
- Never commit `.env`, raw snapshots or real director names.