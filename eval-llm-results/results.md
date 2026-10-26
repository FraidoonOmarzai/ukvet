# ukvet evaluation: v0.1 v0.1 (dev)

- git `ed8f416` · tool 0.1.0 · 2026-10-26T19:09:09+00:00
- 30 companies, 270 items · narrative: `replay` / claude-haiku-5-5

## Headline

| Metric | Target | Result (95% interval) | Size | Verdict |
|---|---|---|---|---|
| M1 accuracy (fields) | >= 90% | 100.0% [99.6%, 100.0%] | 930/930 fields | met |
| M1 worst question | >= 80% each | Q1 100.0% | see table | met |
| M2 unsupported claims | < 2% | 0.4% [0.1%, 2.1%] | 1/265 claims, 30 LLM reports | met |
| M3 abstention | >= 90% | 100.0% [86.7%, 100.0%] | 25/25 cases | met |
| M4 citation validity (mechanical) | 100% | 99.6% [97.9%, 99.9%] | 264/265 claims | **MISSED** |
| M5 red-flag recall | >= 85% | 98.2% [90.5%, 99.7%] | 55/56 expected flags | met |

## M1 by question

| Question | Fields correct | Items fully correct |
|---|---|---|
| Q1 | 100.0% [95.9%, 100.0%] (90/90) | 30/30 |
| Q2 | 100.0% [94.0%, 100.0%] (60/60) | 30/30 |
| Q3 | 100.0% [96.9%, 100.0%] (120/120) | 30/30 |
| Q4 | 100.0% [97.9%, 100.0%] (180/180) | 30/30 |
| Q5 | 100.0% [94.0%, 100.0%] (60/60) | 30/30 |
| Q6 | 100.0% [96.9%, 100.0%] (120/120) | 30/30 |
| Q7 | 100.0% [94.0%, 100.0%] (60/60) | 30/30 |
| Q8 | 100.0% [97.5%, 100.0%] (150/150) | 30/30 |
| Q9 | 100.0% [95.9%, 100.0%] (90/90) | 30/30 |

### M1 failures (0)

None.

## M3 abstention: 25/25 passed

All cases passed.

## M5 red flags: 30 labelled, 0 unlabelled (skipped)

Precision 100.0% [93.5%, 100.0%] · severity agreement 98.2% [90.4%, 99.7%]

- MISSED `officer_turnover` for c032 (many-appointments-director)
- SEVERITY officer_turnover for c035: expected medium, got low

## Narrative (M2, M4)

30 reports, 30 written by an LLM, 265 claims. Writer needed the checker on 0.8% [0.2%, 2.7%] of first-attempt claims; 0 LLM errors, 2 retries.
- c033 [llm]: name or term not in cited facts: IDs — “Across the 2 current directors checked, 50 other companies were found, of which 6 are dissolved; the directors' other appointments may be incomplete because the same person can hold several officer ID”

## Timing (replay, no network)

median 29 ms, worst 2721 ms over 30 reports. replay timings exclude network; see scripts/measure.py for live latency.
