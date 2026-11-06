# Phase 5: Model comparison (roadmap and step-by-step guide)

Audience: a new junior developer. Read Part 1 first. Every step says what to do, how, and why.
Commands are PowerShell, run from the repo root (`C:\Users\44787\Desktop\ukvet`).

---

## Part 1. What Phase 5 is and why it exists

**Goal (from `docs/09-plan.md`):** evidence-based model choice. **Exit criteria:** a comparison
table is published in `docs/results.md`. Target: Week 6.

**The question:** ukvet works with a frontier API model. Does an open-weight model (one you can
host yourself) do the same job well enough, at what cost, and how fast?

**Why it matters to an employer:** "I picked a model because I measured it" beats "I used GPT/Claude
because it was easy". It also shows you can serve a model yourself (vLLM, GPUs, cost per report).

**Why it is cheap to do:** ADR-003 made the model a config change (`LLM_PROVIDER`, `LLM_MODEL`,
`LLM_BASE_URL`). Phase 3 gave you the dataset and scorers. Phase 4 gave you latency, cost and
injection measurement. Phase 5 is mostly *running the same tests again with a different model* and
writing down the honest result. It is not a rewrite.

**The backlog has three issues** (`scripts/backlog.tsv`):
1. Serve an open-weight model (OpenAI-compatible endpoint, e.g. vLLM). Record model ID and hardware.
2. Run full evals on both models. Same dataset version. Record M1, M2, M4, M7, M8.
3. Comparison table and analysis in `docs/results.md`.

I add two small steps around them (a smoke test, and the M6 injection run for both models) because
they stop you wasting GPU money and they make the comparison more honest.

**Risk R13 (in `docs/07-risks.md`):** the open-weight model may be too weak. That is fine. This is
a comparison, not a requirement. A clear "it was worse, here is by how much and why" is a good
result. Do not tune the open model until it wins; do not hide a bad number.

---

## Part 2. The five rules that make the comparison fair

Break one of these and the table is meaningless. Write them on a sticky note.

1. **Same dataset version, same split, same code commit.** Note the git commit and dataset version
   in the results.
2. **Same prompt and same checker for both models.** If you change `reporter_system.md` for one
   model, you changed the experiment. (The LLM cache key includes the prompt, so a prompt change
   also invalidates recordings.)
3. **Same settings:** temperature 0 (or the same low value) for both, one report at a time.
4. **Look at the test split once**, with `--confirm-test-split "reason"`, and log it in the
   decision log. Do all debugging on `dev`.
5. **Report failures next to the scores.** See the trap below.

### The trap: fallback hides a bad model

If the model returns broken output, ukvet falls back to the deterministic template. A template
report is *accurate and cited by construction*, so a model that fails every time can still score
M1, M2 and M4 near-perfect. Always report, for each model:

- **template fallback rate** (share of reports not written by the LLM),
- **retries** and **claims dropped** by the citation checker,
- the scores **over LLM-written reports only**, as well as overall.

Phase 4's `perf.py` already counts `llm_reports`, `template_fallbacks`, `llm_retries` and
`claims_dropped`. The M6 runner reports `narrative_source` too. Use them.

---

## Part 3. Step by step

### Step 1. Freeze the starting point (30 min)
**Do:** make sure Phase 4 is merged. Create a branch `phase-5`. Note the current
git commit (`git rev-parse --short HEAD`), dataset version (`v0.1`), and the API model you used in
Phases 3 and 4 (the exact model ID string).
**Why:** the comparison is only valid for one commit and one dataset. Write them in
`docs/results.md` later, so start a scratch note now.

```powershell
git checkout main
git pull
git checkout -b phase-5
```

**What codes added and updated:**
```bash
evals/src/ukvet_evals
  \---- compare.py
  \---- perf.py
  \---- phase4_cli.py
  \---- phase5_cli.py

scripts/phase4_metrics.py
scripts/phase5_check_endpoint.py

tests/evals/test_phase5_compare.py
```

### Step 2. Pick the open-weight model (1-2 hours, reading)
**Do:** choose ONE model. Criteria, in order: (a) supports tool calling or JSON-schema structured
output in vLLM, (b) fits on one GPU you can rent, (c) has a licence you can cite, (d) recent enough
to be a fair contender. A model in the 7B-32B class is realistic. Check the current Hugging Face
model cards and vLLM supported-models list yourself; do not trust a blog post from months ago.
**Record:** model ID, parameter count, quantisation (if any), licence, and why you chose it.
**Why:** structured output reliability is the thing ukvet depends on (ADR-003 flagged it as
unknown). A model that cannot follow the schema will fall back to the template every time.

**Check:** `development/setup/PHASE5-STEP-2-DECISION.md`

### Step 3. Get a GPU (1-2 hours, then it costs money)
**Options:**
- **A (recommended, matches the backlog):** rent one GPU by the hour (RunPod, Lambda, Vast.ai, or
  a cloud GPU instance). Run vLLM yourself.
- **B (fallback, label it clearly):** a hosted open-weight endpoint (Together, Groq, OpenRouter).
  Cheaper and quicker, but you do not control hardware, so M7 and M8 describe *that provider*, not
  "open-weight model on your GPU". Say so in the table.
- **Not suitable for M7:** Ollama on a laptop CPU. Fine for a smoke test, meaningless as a latency
  number.

**Cost control (do this first):** set a budget alert, note the £ per hour, and **write down the
time you start and stop**. You need hours x rate for M8. Always shut the instance down. A forgotten
GPU costs more than the whole rest of the project (the brief's target is under £100 total).

### Step 4. Serve the model with vLLM (backlog issue 1) (half a day)
**Do:**
1. On the GPU box install vLLM and start the OpenAI-compatible server for your model. Enable
   tool-calling or structured output as the model's card and the vLLM docs describe for that model
   (flags differ per model, so read the docs for your version).
2. Protect it: an API key, firewall, or an SSH tunnel. Do not leave an open endpoint on the internet.
3. Test from your PC with `curl` or Python (`/v1/models`, then one chat completion).
4. Record: model ID, vLLM version, GPU type and count, quantisation, context length, start command.
   Put this in `docs/adr/008-open-weight-serving.md` (short ADR).

**Point ukvet at it** in `.env` (never commit it):
```
LLM_PROVIDER=openai_compatible
LLM_MODEL=<exact model id from /v1/models>
LLM_BASE_URL=http://<host>:8000/v1
LLM_API_KEY=<the key you set, or any placeholder if none>
LLM_TEMPERATURE=0
LLM_TIMEOUT_SECONDS=60
```
**Why the timeout:** the default is 15 seconds. A self-hosted model can be slower, a timeout looks
like a failure, and ukvet quietly falls back to the template. Raise it for BOTH models so the
timeout is not what decides the winner, and keep M7 as the place where slowness is measured.

> One more detail: ukvet only reads a file named .env, so it won’t pick up env.qwen automatically. When you’re ready to test the Qwen model, copy it over .env, for example Copy-Item .env .env.cluade to back up your API settings, then Copy-Item env.qwen .env. Copy .env.cluade back afterwards when you want to use the API model again.

**Note:** Deep descriptions from step2-4(`development/setup/PHSAE-5-GPU-SETUP.md`)

### Step 5. Smoke test before spending real money (1 hour)
**Do:** generate 5 to 10 real reports with the open model:
```powershell
uv run python scripts/phase4_metrics.py 00445790 03977902 --out evals/results/phase5-smoke
```
Open `metrics.md`. Check: how many reports were LLM-written vs template? Any retries, dropped
claims, timeouts? Read two reports by hand.
**Decision:** if nearly everything falls back to the template, fix serving (structured output
flags, timeout, context length) BEFORE the full run. If the model is genuinely bad at the schema,
that is a result, not a bug: record it and continue.
**Why:** a full run is hundreds of calls. Find the setup mistakes on ten.

### Step 6. Record the open-model answers (backlog issue 2, part 1) (half a day)

Phase 3 evals replay recorded LLM answers (the cache is keyed by model, system prompt and user
prompt), so each model needs its own recording, made once.
```powershell
uv run ukvet-evals run --dataset v0.1 --split dev --llm record --model <open-model-id>
```
**Check:** no errors, a `evals/llm_cache` entry per call, and the fallback rate looks like Step 5.
Commit the cache files only if your repo policy allows (they contain model output about
anonymised snapshots, not secrets; run `ukvet-evals validate` first).

### Step 7. Run the full evals for both models (backlog issue 2, part 2) (half a day)
Run each model on the same split with replay. First `dev` for debugging:
```powershell
uv run ukvet-evals run --dataset v0.1 --split dev --llm replay --model <api-model-id>  --out evals/results/v0.1-dev-api
uv run ukvet-evals run --dataset v0.1 --split dev --llm replay --model <open-model-id> --out evals/results/v0.1-dev-open
```
Then the **final numbers on the test split, once**, for both models, with the reason logged:
```powershell
uv run ukvet-evals run --dataset v0.1 --split test --llm replay --model <api-model-id>  --confirm-test-split "Phase 5 final comparison" --out evals/results/v0.1-test-api
uv run ukvet-evals run --dataset v0.1 --split test --llm replay --model <open-model-id> --confirm-test-split "Phase 5 final comparison" --out evals/results/v0.1-test-open
```
(If you have not yet recorded the API model on the test split, record first with `--llm record`.
Replay needs a recording; a miss exits with code 3.)

Collect, per model, with 95% intervals (the harness already prints Wilson intervals):
M1 overall and per category Q1-Q9, M2, M4, plus fallback rate, retries and claims dropped.
**Why per category:** an average can hide a category that fails badly (rule in `04-success-metrics.md`).

### Step 8. Measure latency and cost live (M7, M8) (half a day)
Replay timings exclude the network, so M7 and M8 need LIVE runs, as in Phase 4:
```powershell
uv run python scripts/phase4_metrics.py --file numbers.txt --out evals/results/phase5-live-open
```
Use the same 20+ company numbers for both models, run them one at a time, and note the time of day
and network. 20+ runs, otherwise the p95 is labelled "weak".

- **API model cost:** tokens x price. Set `UKVET_PRICE_IN_GBP_PER_MTOK` and
  `UKVET_PRICE_OUT_GBP_PER_MTOK` from the provider's price page.
- **Self-hosted cost per report:** (GPU £/hour x hours the server was up during the measured run)
  divided by reports served. State the utilisation: a GPU that serves one report at a time is
  mostly idle, so this figure is high; say that, and do not present it as the best case. If you
  also want a "full utilisation" estimate, label it an estimate and show the arithmetic.
- Hosted open-weight endpoint (Step 3 option B): use that provider's token prices.

### Step 9. Re-run M6 injection for both models (1 hour, cheap)
```powershell
uv run ukvet-evals injection --dataset v0.1 --llm record --model <open-model-id>
uv run ukvet-evals injection --dataset v0.1 --llm replay --model <open-model-id> --out evals/results/v0.1-injection-open
```
**Why:** a weaker model may follow injected text more often. It is one more column that employers
care about, and it costs pence. Same rules as Phase 4: do not change defences between models.

**Note:** `setup/PHASE-5-RUNBOOK.md` for deeper explanation.

### Step 10. Optional ablation: ReAct baseline (cut this if you are behind)
ADR-007 says Phase 5 *can* add a ReAct (model-chooses-tools) baseline to show what the
deterministic researcher buys you. It is real work and not in the three backlog issues. Do it only
if Steps 1-9 are finished with days to spare. Otherwise write it down as `v2` in the backlog.

### Step 11. Read the failures, not just the numbers (half a day)
For each model, open 5 to 10 failing or fallback cases. Group them: schema errors, timeouts,
dropped claims, wrong fact, injection. This is the "why" that makes the analysis worth reading, and
it is what interviewers will ask about.

### Step 12. Publish the comparison (backlog issue 3) (half a day)
Create or update `docs/results.md` with:

1. **Setup:** git commit, dataset version, split, prompts unchanged, temperature, timeout, date.
2. **The table** (format from `04-success-metrics.md` section 5, plus honest extras):

| Model | M1 | M2 | M4 | p95 latency (M7) | Cost/report (M8) | LLM-written share | M6 |
|---|---|---|---|---|---|---|---|
| API model `<id>` | | | | | | | |
| Open-weight `<id>` on `<GPU>` | | | | | | | |

3. **Per-category M1** for both models.
4. **Failure analysis** (Step 11).
5. **Trade-offs:** accuracy vs cost vs latency vs control (data stays on your box, no per-token
   fee, but you pay for idle GPU and run it yourself). Say which you would use for what.
6. **Limitations:** one open-weight model, one run, 20+ latency samples, dataset size, anonymised
   snapshots, no human grading of fairness (risk R15), hardware-specific latency.
7. **Recommendation:** one paragraph, supported by the table.

### Step 13. Close the loop (1 hour)
- Add decision-log rows: which models and why; the test split viewed once (date and reason); any
  prompt or config difference; the cost method.
- Update `docs/07-risks.md`: R13 (was the open model too weak?), and update the project cost figure
  in the brief with your real spend.
- Update the root `README.md` status (Phase 5 complete) and add the table or a link to it.
- Tag a commit: `git tag phase-5-complete`.
- **Shut down the GPU.** Confirm it in the provider dashboard.

---

## Part 4. Timeline (about 3 to 4 working days)

| Day | Steps | Output |
|---|---|---|
| 1 | 1-4 | model chosen, GPU served, ADR-008 |
| 2 | 5-7 | smoke test passed, both models recorded and scored |
| 3 | 8-9, 11 | live M7/M8, M6 for both, failure notes |
| 4 | 12-13 | `docs/results.md` published, logs updated, GPU off |

If you slip: drop Step 10 first, then M6 (Step 9). Never drop the per-category M1, the fallback
rate or the test-split log.

## Part 5. Definition of done (checklist)

- [ ] Open-weight model served; model ID, hardware and version recorded (ADR-008)
- [ ] Same dataset version, split, prompt, temperature for both models
- [ ] M1 (overall and per category), M2, M4 reported with intervals for both
- [ ] M7 and M8 from live runs (20+ reports each), cost method written down
- [ ] Fallback rate, retries and dropped claims shown next to the scores
- [ ] Test split looked at once, logged in the decision log
- [ ] `docs/results.md` has the table, failure analysis, trade-offs, limitations, recommendation
- [ ] R13 and the cost figure updated; README status updated
- [ ] No secrets or private data committed; `ukvet-evals validate` passes
- [ ] GPU instance shut down

## Part 6. Common mistakes

| Mistake | What happens | Fix |
|---|---|---|
| Timeout left at 15 s | Open model looks "bad" because everything fell back | Raise it for both models |
| Comparing overall M1 only | A failing category is hidden | Report per category |
| Editing the prompt for the open model | Unfair, and the cache is invalidated | Same prompt for both |
| Looking at the test split while debugging | Test is no longer unseen | Debug on dev only |
| Latency from replay | No network, wrong number | Use live runs |
| Forgetting the GPU | A surprise bill | Alert, stop time, shut down |
| Reporting cost without utilisation | Self-hosting looks falsely cheap or expensive | State utilisation |
