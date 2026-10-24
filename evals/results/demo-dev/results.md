# ukvet evaluation: demo demo-1 (dev)

> **Synthetic demo data.** These numbers prove the harness works; they say nothing about ukvet's accuracy.

- git `d544d0a` · tool 0.1.0 · 2026-10-24T13:10:01+00:00
- 4 companies, 36 items · narrative: `none`

## Headline

| Metric | Target | Result (95% interval) | Size | Verdict |
|---|---|---|---|---|
| M1 accuracy (fields) | >= 90% | 100.0% [97.0%, 100.0%] | 124/124 fields | met |
| M1 worst question | >= 80% each | Q1 100.0% | see table | met |
| M2 unsupported claims | < 2% | n/a (no LLM reports) | 0/36 claims, 0 LLM reports | not measured |
| M3 abstention | >= 90% | 100.0% [51.0%, 100.0%] | 4/4 cases | met |
| M4 citation validity (mechanical) | 100% | 100.0% [90.4%, 100.0%] | 36/36 claims | met |
| M5 red-flag recall | >= 85% | 100.0% [64.6%, 100.0%] | 7/7 expected flags | met |

## M1 by question

| Question | Fields correct | Items fully correct |
|---|---|---|
| Q1 | 100.0% [75.8%, 100.0%] (12/12) | 4/4 |
| Q2 | 100.0% [67.6%, 100.0%] (8/8) | 4/4 |
| Q3 | 100.0% [80.6%, 100.0%] (16/16) | 4/4 |
| Q4 | 100.0% [86.2%, 100.0%] (24/24) | 4/4 |
| Q5 | 100.0% [67.6%, 100.0%] (8/8) | 4/4 |
| Q6 | 100.0% [80.6%, 100.0%] (16/16) | 4/4 |
| Q7 | 100.0% [67.6%, 100.0%] (8/8) | 4/4 |
| Q8 | 100.0% [83.9%, 100.0%] (20/20) | 4/4 |
| Q9 | 100.0% [75.8%, 100.0%] (12/12) | 4/4 |

### M1 failures (0)

None.

## M3 abstention: 4/4 passed

All cases passed.

## M5 red flags: 4 labelled, 0 unlabelled (skipped)

Precision 100.0% [64.6%, 100.0%] · severity agreement 100.0% [64.6%, 100.0%]


## Narrative (M2, M4)

4 reports, 0 written by an LLM, 36 claims. Writer needed the checker on n/a of first-attempt claims; 0 LLM errors, 0 retries.

## Timing (replay, no network)

median 26 ms, worst 2458 ms over 4 reports. replay timings exclude network; see scripts/measure.py for live latency.
