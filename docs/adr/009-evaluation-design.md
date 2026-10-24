# ADR-009: Evaluation design (frozen replay, independent oracle, protected test split)

- **Status:** Accepted
- **Date:** 24 Oct 2026

## Context
Phase 2 gave a manual check (no errors in about 75 values on 10 companies). That is a spot check,
not a measurement. Phase 3 must give repeatable numbers for M1 to M5 that survive scrutiny and
catch regressions. Risks: circular ground truth (the oracle and the system misread the API the same
way), label bias (the author wrote both rules and labels), overfitting to the eval set, small
samples, LLM variation, and personal data in a public dataset.

## Decision
1. **Item = one question about one company** (about 28 companies × Q1 to Q9). Red-flag, abstention
   and injection cases are separate files.
2. **Three tiers of truth.** Golden values read by hand from the website; an oracle that derives
   expected values from raw API JSON and imports neither ukvet package (enforced by a test); rule
   labels written from definitions before running the rules. Oracle and golden must agree, or the
   run stops.
3. **Frozen world.** Anonymised raw responses are recorded once per company with an `as_of` date and
   replayed through the real MCP server and agent graph with a frozen clock. Free, fast, identical
   every run. A small live smoke test stays separate.
4. **Privacy.** Recording anonymises in memory, runs the leak check before writing, and keeps the
   real-to-alias map in git-ignored `data/raw/`. `validate` re-checks every committed snapshot.
5. **Protected test split.** Split = hash of (salt, id). The salt is chosen once to balance a small
   dataset (a plain hash of about 28 ids can be badly lopsided), then locked. Tune on dev only.
   Running test needs `--confirm-test-split "reason"`, which is logged.
6. **Gate on dev, deterministic.** CI replays the dev split in template mode and fails on a new
   field failure, M1 overall drop above 1 point, a category falling through the 80% floor, M3 or M5
   drop above 2 points, any mechanical citation failure, or (when LLM reports exist) M2 rising more
   than 0.5 points. Targets are reported, not gated. Baseline changes only via a PR that says why.
7. **LLM text is recorded, then replayed.** Cache key = hash(model, prompt). A miss fails the run
   ("re-record"), never silently falling back to a template.
8. **Independent citation scorer, stricter than production** (it also checks names). The LLM judge
   is a different model family, calibrated against 20 hand labels, and never gates CI.

## Alternatives considered
| Option | Why not |
|---|---|
| Use the pipeline's own output as ground truth | Circular: proves nothing |
| Live API in CI | Flaky, needs a key, data drifts daily |
| Pure hash split with no salt | Unbalanced at n≈28 |
| Gate on dev and test | Burns the test set on every PR |
| Percentage-only gate | Hides one regression behind unrelated gains; data is deterministic so any new failure is real |

## Consequences
- Every later change (rule, prompt, model) is judged by numbers.
- Replay does not test live API behaviour; keep `scripts/measure.py` and a live smoke test.
- The oracle shares definitions (for example "current officer") with the pipeline; only transformation
  bugs are caught by M1. The golden set is what ties it to the website. Say so when quoting M1.
- The hard work is human: golden labelling, flag labelling, second labeller.
