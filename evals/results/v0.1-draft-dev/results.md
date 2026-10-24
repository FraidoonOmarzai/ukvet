# ukvet evaluation: v0.1-draft draft-1 (dev)

> **Synthetic demo data.** These numbers prove the harness works; they say nothing about ukvet's accuracy.

- git `7c28d01` · tool 0.1.0 · 2026-10-24T14:20:05+00:00
- 17 companies, 153 items · narrative: `none`

## Headline

| Metric | Target | Result (95% interval) | Size | Verdict |
|---|---|---|---|---|
| M1 accuracy (fields) | >= 90% | 100.0% [99.3%, 100.0%] | 527/527 fields | met |
| M1 worst question | >= 80% each | Q1 100.0% | see table | met |
| M2 unsupported claims | < 2% | n/a (no LLM reports) | 0/153 claims, 0 LLM reports | not measured |
| M3 abstention | >= 90% | 100.0% [81.6%, 100.0%] | 17/17 cases | met |
| M4 citation validity (mechanical) | 100% | 100.0% [97.5%, 100.0%] | 153/153 claims | met |
| M5 red-flag recall | >= 85% | 100.0% [86.2%, 100.0%] | 24/24 expected flags | met |

## M1 by question

| Question | Fields correct | Items fully correct |
|---|---|---|
| Q1 | 100.0% [93.0%, 100.0%] (51/51) | 17/17 |
| Q2 | 100.0% [89.8%, 100.0%] (34/34) | 17/17 |
| Q3 | 100.0% [94.7%, 100.0%] (68/68) | 17/17 |
| Q4 | 100.0% [96.4%, 100.0%] (102/102) | 17/17 |
| Q5 | 100.0% [89.8%, 100.0%] (34/34) | 17/17 |
| Q6 | 100.0% [94.7%, 100.0%] (68/68) | 17/17 |
| Q7 | 100.0% [89.8%, 100.0%] (34/34) | 17/17 |
| Q8 | 100.0% [95.7%, 100.0%] (85/85) | 17/17 |
| Q9 | 100.0% [93.0%, 100.0%] (51/51) | 17/17 |

### M1 failures (0)

None.

## M3 abstention: 17/17 passed

All cases passed.

## M5 red flags: 17 labelled, 0 unlabelled (skipped)

Precision 100.0% [86.2%, 100.0%] · severity agreement 100.0% [86.2%, 100.0%]


## Narrative (M2, M4)

17 reports, 0 written by an LLM, 153 claims. Writer needed the checker on n/a of first-attempt claims; 0 LLM errors, 0 retries.

## Timing (replay, no network)

median 29 ms, worst 2630 ms over 17 reports. replay timings exclude network; see scripts/measure.py for live latency.
