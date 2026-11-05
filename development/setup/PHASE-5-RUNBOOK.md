# Phase 5 runbook: run both models and compare

Order is chosen so the paid GPU is on for as little time as possible. PowerShell, repo root.
Model A = Claude (API). Model B = Qwen/Qwen3.6-27B (RunPod GPU).

## 0. Before anything (free)

1. **Commit everything first** (Phase 4 + Phase 5 code, no experiment files). All runs below must
   use the SAME git commit and the SAME prompt files. `ukvet-evals compare` warns if they differ.
   ```powershell
   git status          # should be clean for code files
   git rev-parse --short HEAD
   ```
2. Same settings in both env files: `LLM_TEMPERATURE=0` and `LLM_TIMEOUT_SECONDS=60`.
3. `numbers.txt`: 20+ real company numbers, one per line. Same file for both live runs. Never commit it.
4. Set the exact model ids you will use. They must be identical in the run command and the manifest:
   - Claude: the `LLM_MODEL` value in `.env.claude` (call it `<CLAUDE_ID>` below)
   - Qwen: `Qwen/Qwen3.6-27B`
5. Prices for the Claude cost figure: from the Anthropic price page for `<CLAUDE_ID>`, in GBP per
   million tokens (convert USD at the day's rate, write the rate down). Add to `.env.claude`:
   ```
   UKVET_PRICE_IN_GBP_PER_MTOK=<number>
   UKVET_PRICE_OUT_GBP_PER_MTOK=<number>
   ```
6. Cost log for the pod started (start time, $1.81/hr, GPU). Write the USD to GBP rate.

## 1. QWEN, GPU ON (the only paid part)

```powershell
Copy-Item env.qwen .env
uv run python scripts/phase5_check_endpoint.py --rounds 5            # expect 5/5

# 1a. dev split: record + score
uv run ukvet-evals run --dataset v0.1 --split dev --llm record --model Qwen/Qwen3.6-27B --out evals/results/v0.1-dev-open

# 1b. test split, record + score: this is your ONE look at the test split
uv run ukvet-evals run --dataset v0.1 --split test --llm record --model Qwen/Qwen3.6-27B --confirm-test-split "Phase 5 final comparison" --out evals/results/v0.1-test-open

# 1c. live latency run (one at a time, 20+ companies)
uv run python scripts/phase4_metrics.py --file numbers.txt --label open --out evals/results/phase5-live-open

# 1d. injection (record)
uv run ukvet-evals injection --dataset v0.1 --llm record --model Qwen/Qwen3.6-27B --out evals/results/v0.1-injection-open
```
Check after each: no errors, `evals/llm_cache` grew, and the narrative line says almost all reports
were written by the LLM (low template fallback).

**Before you shut the pod,** run the free replays once, to prove nothing is missing (exit code 3
= a recording is missing and you would need the GPU again):
```powershell
uv run ukvet-evals run --dataset v0.1 --split dev --llm replay --model Qwen/Qwen3.6-27B --out evals/results/v0.1-dev-open-replay
uv run ukvet-evals run --dataset v0.1 --split test --llm replay --model Qwen/Qwen3.6-27B --confirm-test-split "Phase 5 replay check, same recording as the final look" --out evals/results/v0.1-test-open-replay
uv run ukvet-evals injection --dataset v0.1 --llm replay --model Qwen/Qwen3.6-27B --out evals/results/v0.1-injection-open-replay
```
The numbers must equal the recording runs.

## 2. SHUT DOWN THE GPU

- Write the stop time in the cost log, then **terminate** the pod (not just Stop).
- Note the live-run window: open `evals/results/phase5-live-open/metrics.json`, field `run`
  (`started`, `finished`). The hours between them are what you use for the self-hosted cost.

## 3. CLAUDE (no GPU, pence)

```powershell
Copy-Item .env.claude .env

# 3a. dev
uv run ukvet-evals run --dataset v0.1 --split dev --llm record --model claude-haiku-5-5 --out evals/results/v0.1-dev-api

# 3b. test (second model, same single look for the comparison)
uv run ukvet-evals run --dataset v0.1 --split test --llm record --model claude-haiku-5-5 --confirm-test-split "Phase 5 final comparison" --out evals/results/v0.1-test-api

# 3c. live latency + cost (same numbers.txt)
uv run python scripts/phase4_metrics.py --file numbers.txt --label api --out evals/results/phase5-live-api

# 3d. injection
uv run ukvet-evals injection --dataset v0.1 --llm record --model claude-haiku-5-5 --out evals/results/v0.1-injection-api
```
If you already recorded Claude on dev/test in Phase 3/4 with the same prompt text, use `--llm replay`
for 3a and 3b instead (a miss exits 3: then record). Do not change `reporter_system.md`: it changes
the cache key and invalidates recordings.

## 4. Build the comparison table

```powershell
uv run ukvet-evals validate --dataset v0.1                        # before committing llm_cache
uv run ukvet-evals compare --init                 # creates evals/comparison.json
```
Open `evals/comparison.json` and fill in (no keys in it):

| Field | Claude entry | Qwen entry |
|---|---|---|
| `label` | `Claude (API)` | `Qwen3.6-27B (self-hosted)` |
| `kind` | `api` | `self-hosted` |
| `model_id` | `<CLAUDE_ID>` (exact) | `Qwen/Qwen3.6-27B` |
| `hardware` | leave empty | `1x A100 SXM 80GB, RunPod Secure Cloud, vLLM <version from log>, bf16, thinking off` |
| `gpu_gbp_per_hour` | not used | 1.81 USD converted to GBP (write the rate in `notes`) |
| `gpu_hours` | not used | hours of the live-run window (`finished` minus `started`), e.g. 0.15 |
| `results` | `evals/results/v0.1-test-api/results.json` | `evals/results/v0.1-test-open/results.json` |
| `live` | `evals/results/phase5-live-api/metrics.json` | `evals/results/phase5-live-open/metrics.json` |
| `injection` | `evals/results/v0.1-injection-api/injection.json` | `evals/results/v0.1-injection-open/injection.json` |
| `notes` | thinking off, timeout 60, temp 0 | same + whole-session GPU spend in GBP, USD to GBP rate used |

Note on Qwen cost: `gpu_hours` = the live-run window, so the figure is GPU time needed for those
reports, with no idle time. Put the whole-session spend in `notes` too. Say which one you quote.

```powershell
uv run ukvet-evals compare            # writes docs/results.md and docs/results.json
```
It refuses unfair comparisons (different dataset or split, template-only run, wrong model id) and
prints warnings above the table (different commit, over 10% template fallback, fewer than 20 live
runs, missing runs). Fix what it says and run again.

## 5. Finish by hand

In `docs/results.md` write the three empty sections: **Failure analysis** (read 5 to 10 failing or
fallback cases per model), **Trade-offs** (accuracy, cost, latency, control), **Recommendation**
(one paragraph, supported by the table). Then:

- decision log: models and why, test split looked at once (date, reason), thinking off, temperature 0,
  cost method, USD to GBP rate
- fill `docs/adr/008-open-weight-serving.md` (vLLM version, GPU, flags, hours, price)
- `docs/07-risks.md`: R13 outcome; update the total spend
- README status: Phase 5 complete + link to `docs/results.md`
- do not commit: `.env*`, `env.qwen`, `numbers.txt`, `evals/results/phase5-live-*`
- `git tag phase-5-complete`
