# ukvet evaluation report: dataset v0.1

Dataset: `v0.1` · companies: 48 · items: 432 (9 questions x 48) · dev/test: 30/18 · final run git `562497e` · as_of: snapshots recorded 24 Oct 2026
Writer model: `claude-haiku-5-5` (recorded answers, replayed) · judge: none · test split looked at: **once**, 27 Oct 2026, reason "milestone: final baseline"

## Results

| Metric | Target | Dev (30 cos) | Test (18 cos)* | All (48 cos) | Verdict |
|---|---|---|---|---|---|
| M1 accuracy (fields) | >= 90% | 100.0% (930/930) | 100.0% (558/558) | 100.0% [99.7%, 100.0%] (1488/1488) | Met |
| M1 worst question | >= 80% each | Q1 to Q9 all 100% | all 100% | all 100% | Met |
| M2 unsupported claims | < 2% | 0.0% (0/265) [0.0%, 1.4%] | 0.0% (0/156) [0.0%, 2.4%] | 0.0% (0/421) [0.0%, 0.9%] | Met on dev and all. On the test split alone the upper bound (2.4%) is above 2%: the set is too small to rule out |
| M3 abstention | >= 90% | 100.0% (25/25) | 100.0% (14/14) | 100.0% (39/39) [91.0%, 100.0%] | Met |
| M4 citation validity, mechanical | 100% | 100.0% (265/265) | 100.0% (156/156) | 100.0% (421/421) [99.1%, 100.0%] | Met |
| M4 semantic (does the cited fact support the sentence) | none | not measured | not measured | not measured | No judge was run |
| M5 red-flag recall | >= 85% | 100.0% (55/55) | 100.0% (34/34) | 100.0% (89/89) [95.9%, 100.0%] | Met |
| M5 precision / severity agreement | tracked | 100% / 100% | 100% / 100% | 100% / 100% [95.9%, 100.0%] | |
| M7 latency, worst of N (live, Phase 2) | < 30 s | worst 5.9 s over 20 runs, 10 companies | | | Met |
| M8 cost per report (live, Phase 2) | < £0.05 | about £0.0004 | | | Met |

\* Test = all minus dev. The counts are additive, so the test-split figures are derived from the two printed runs, not printed separately. Intervals are Wilson 95%.

Narrative: 48 reports, all written by the model, 421 claims, 0 LLM errors, 5 retries. The production checker intervened on 1.4% [0.7%, 3.1%] of first-attempt claims, so it does real work.
M7 and M8 come from the Phase 2 live runs (`claude-haiku-5-5`, 10 companies), not from this replay: replay timings exclude the network.

## Failures found on dev and what was done

The first dev run was not clean. Three findings, all explained and closed before the test split was looked at:

| # | What | Cause | Class | Action |
|---|---|---|---|---|
| 1 | One claim (c033) counted as unsupported (M2) and as an invalid citation (M4: 99.6%) | The strict scorer read a fact's statement and value but not its caveats. The claim restated the `Q8.network` caveat ("the same person can have several IDs") | Scorer false positive | Scorer now counts fact caveats as support. New test: restating a caveat passes, an invented name still fails. **Changed after seeing dev results** (decision 44) |
| 2 | c032: expected `officer_turnover` low, not raised (M5 recall 55/56) | Its only events were secretary changes. The rule ignores secretaries; the label definition counted them | Definition and rule disagreed | Definition changed to match the rule; labels regenerated and reviewed, with notes. **Changed after seeing dev results** (decision 43) |
| 3 | c035: expected `officer_turnover` medium, got low | Two of four events were secretary resignations; same cause as 2 | Same | Same |

No M1 failures, abstention failures or precision failures were found on any split.

## What 100% does and does not mean

- **M1 is agreement with an oracle I wrote.** The oracle is independent of the project code (a test enforces that it imports neither package) and only 10 companies were checked against the live website by hand. M1 shows retrieval and mapping match the oracle, not that every field is true. A 100% score also means this set is not hard enough to find new retrieval bugs.
- **M5 labels were drafted by a script from the written definitions and reviewed by one person.** The rules and the labels both come from the same author, so recall of 100% partly measures consistency. The secretary finding shows the check can still disagree, but I did not use a second labeller.
- **M3 cases were generated from a dependency table**, so they mostly test that the rules follow that table.
- **M2 and M4 are mechanical** (IDs, dates, numbers, names, forbidden wording). Whether a cited fact really supports a sentence, and whether wording is fair, was not measured (no judge, no human read of all 48 reports). Risk R15 stays open for tone and fairness.
- Injection resistance (M6) is not measured: 15 cases are seeded for Phase 4.

## What this does not cover

- Company types not in the set; the set was chosen to cover 19 tags, not sampled at random.
- Live API behaviour: results come from frozen snapshots (recorded 24 Oct 2026).
- One writer model; no model comparison (Phase 5).
- 10 golden companies, not the 25 planned; `validate --strict` still warns about this.
- One labeller; no agreement figure.
- c031 was truncated at the fetch cap (officers and charges), so its Q3 and Q6 values are capped, in both the oracle and the pipeline.

## Discipline

- Dev/test split fixed by a salted hash before any scores were seen, then locked.
- The test split was run once, after all changes. Nothing was changed after seeing test numbers.
- Changes made after seeing dev results: the strict scorer (caveats) and the `officer_turnover` label definition. Both are logged and explained above.
- CI blocks regressions on the dev split in template mode (Tier 1). The recorded-LLM gate (Tier 2) is designed but not enabled.

## What may be claimed

"On a versioned 48-company, 432-item evaluation set, ukvet's retrieval matched an independent oracle on 1488 of 1488 fields (99.7% to 100%, Wilson 95%); no model-written claim among 421 was unsupported by a mechanical check (upper bound 0.9%); all 39 fault-injection cases degraded as specified; and 89 of 89 hand-reviewed expected red flags were raised. Ground truth was cross-checked by hand against the live website for 10 companies. CI blocks regressions."

Do not claim: accuracy against reality beyond the 10 checked companies, a hallucination rate for sentence meaning, fairness of wording, or injection resistance.
