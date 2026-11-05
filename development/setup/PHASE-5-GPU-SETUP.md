# Phase 5 setup log: from choosing the model to a running GPU server

This is what was actually done for ukvet (Phase 5, steps 2 to 4), written so a new developer can
repeat it. Nothing here contains a real key. Replace `<YOUR_KEY>` with your own.

Status when this was written: the model server started on RunPod and accepted every flag; the
final check from the PC (`phase5_check_endpoint.py`) is the last step still to confirm.

---

## 1. The idea in plain words

ukvet needs a language model to write the report text. We compare two:

- an **API model** (Claude), which someone else runs for us, and
- an **open-weight model** (Qwen), whose files are free, but which we must run ourselves.

A downloaded model is only a big file of numbers. To answer questions it must be loaded onto a
**GPU** by a program. That program is **vLLM**. vLLM loads the model and opens a web address that
looks like OpenAI's API. ukvet already speaks that format (`LLM_PROVIDER=openai_compatible`), so
switching models is only a settings change.

```
your PC (ukvet, evals)  --request-->  rented GPU machine (vLLM + Qwen)
        ^                                       |
        +-------------- written text -----------+
```

Your PC does almost all the work (Companies House calls, rules, checking, scoring). The GPU
machine only turns a prompt into text. The model does not make predictions; the facts and red
flags still come from the registry data and the rules.

---

## 2. Choosing the model (reading, 1 to 2 hours)

Four checks, in order:

1. **Structured output / tool calling works in vLLM.** ukvet needs the model to answer in a fixed
   format. If it cannot, every report falls back to the template.
2. **Fits one GPU you can rent.** Rule of thumb: about 2 GB of GPU memory per billion parameters at
   full precision (half if quantised).
3. **A licence you can cite.** Read the "License" line on the model card.
4. **Recent**, so the comparison is fair.

**Decision made:**

| Item | Value |
|---|---|
| Model | `Qwen/Qwen3.6-27B` |
| Size | 27B parameters, dense, no quantisation (bf16) |
| Licence | Apache 2.0 (from the model card) |
| vLLM needed | 0.19.0 or newer |
| Tool-call flag | `--tool-call-parser qwen3_coder` (without it, tool calls fail silently) |
| GPU | one 80 GB GPU (weights are about 54 GB, plus working space) |

Two facts to know about this model:

- **Thinking mode is on by default.** The model writes a long hidden reasoning block first. That
  slows every report and can use up the token limit before the answer starts, which looks like a
  failure. We switch it off for the comparison.
- **Temperature.** The model card suggests 0.7. We use 0 for both models so the comparison is
  fair. Write this in the ADR.

Backup if the 80 GB GPU is unavailable: `Qwen/Qwen3.6-35B-A3B` (mixture of experts). Check its
licence on its own model card first.

Record all of the above in `docs/adr/008-open-weight-serving.md`.

---

## 3. Before spending money

Do everything that does not need the GPU first:

- Finish the API model completely on your PC (dev and test evals, live latency/cost run,
  injection run). Cost: pence. A bug found now is free.
- Install and test the Phase 4 and Phase 5 code (`pytest`, `ruff`, `mypy`).
- Prepare `numbers.txt` with 20 or more real company numbers (same list for both models).
- Prepare the settings files (section 6).
- Generate your API key (section 5).
- Decide a stop rule: for example, "if it is not working after 90 minutes, stop the pod and ask".

---

## 4. Renting the GPU on RunPod

1. Create the account. Add only a small amount of credit (for example 20 to 30 pounds). Do not
   turn on auto-top-up. Set a budget alert if the site offers one.
2. Deploy a pod:
   - **Template:** `vLLM Latest` (runs the official `vllm/vllm-openai:latest` image).
   - **GPU:** 1x A100 SXM (80 GB). Secure Cloud.
   - **Container disk:** 120 GB (the model download is about 54 GB).
   - **HTTP port:** 8000 (the template exposes it as "vLLM Server").
3. **Write the cost log immediately:**

```
Provider: RunPod Secure Cloud (US-MD-1)
GPU: 1x A100 SXM, 16 vCPU, 250 GB RAM
Rate: $1.81/hr total ($1.79 compute + $0.017 storage). It is in US dollars:
      note the USD to GBP rate on the day. M8 needs pounds.
Started: 5 Nov 2026, about 17:59
Stopped: about 20:21 on 5 Nov 2026
Total uptime: 2h 22m. At $1.81 per hour that’s about $4.24 for the whole session, before the USD to GBP conversion.
Version: vLLM 0.33.0, which is above the 0.19.0 minimum for Qwen3.6
```

You need hours x rate for the cost-per-report figure (M8).

---

## 5. Configuring the pod (the important part)

The template starts with a small default model and a **weak default API key** (`sk-` plus the pod
id, which anyone who sees the URL can guess). Change both.

### 5.1 Make your own API key

The key is just a long random password you invent. In PowerShell:

```powershell
-join ((48..57)+(97..122) | Get-Random -Count 40 | % {[char]$_})
```

Store it in a password manager. Never put it in chat, git, or a screenshot.

### 5.2 Edit Pod

Three dots (top of the pod page) > **Edit Pod**. A warning says saving resets the pod and loses its
data. That is fine at this stage.

**Container start command** (use the "+ Start command" box). The vLLM image already runs
`vllm serve`, so you give only the arguments, with the model name first:

```
Qwen/Qwen3.6-27B --host 0.0.0.0 --port 8000 --api-key <YOUR_KEY> --max-model-len 16384 --enable-auto-tool-choice --tool-call-parser qwen3_coder --language-model-only --default-chat-template-kwargs '{"enable_thinking": false}'
```

What each part does:

| Part | Meaning |
|---|---|
| `Qwen/Qwen3.6-27B` | which model to download and serve |
| `--host 0.0.0.0 --port 8000` | listen so the RunPod proxy can reach it |
| `--api-key` | callers must send this key |
| `--max-model-len 16384` | longest prompt+answer; ukvet prompts are small, this saves memory |
| `--enable-auto-tool-choice --tool-call-parser qwen3_coder` | lets the model return structured/tool output |
| `--language-model-only` | skip the image part of the model, freeing memory |
| `--default-chat-template-kwargs '{"enable_thinking": false}'` | thinking off |

**Environment variables:** change only `VLLM_API_KEY`. Replace `sk-$RUNPOD_POD_ID` with your key.
Leave `HF_HOME`, `PUBLIC_KEY` and `JUPYTER_PASSWORD` alone. The key must be identical in three
places:

1. `VLLM_API_KEY` in the pod environment variables,
2. `--api-key` in the start command,
3. `LLM_API_KEY` in your PC settings file.

If they differ, your PC gets "unauthorized" errors.

Click **Save**. The pod restarts and loads the model.

---

## 6. Settings files on your PC

ukvet reads only a file named `.env`. Keep one file per model and copy the one you want over
`.env`:

```powershell
Copy-Item .env .env.claude        # back up the Claude settings once
Copy-Item .env env.qwen           # start the Qwen file from your current .env, then edit it
```

In `env.qwen`, change only the `LLM_*` lines (keep Companies House and other lines as they are):

```
LLM_PROVIDER=openai_compatible
LLM_MODEL=Qwen/Qwen3.6-27B
LLM_BASE_URL=https://<POD_ID>-8000.proxy.runpod.net/v1
LLM_API_KEY=<YOUR_KEY>
LLM_TEMPERATURE=0
LLM_TIMEOUT_SECONDS=60
```

Format rules: no dot after the name, no spaces around `=`, no quotes. Copy the exact base URL from
the pod's **Connect** tab (the proxy address contains the pod id).

Switch models with:

```powershell
Copy-Item env.qwen .env       # use Qwen
Copy-Item .env.claude .env    # back to Claude
```

Use the same `LLM_TEMPERATURE` and `LLM_TIMEOUT_SECONDS` in both files so the comparison is fair.
Add `.env`, `.env.claude`, `env.qwen` to `.gitignore`.

---

## 7. Reading the Logs tab: is it ready?

Open the pod's **Logs** tab and watch.

What you saw, in order, and what it means:

| Log line | Meaning |
|---|---|
| a dictionary showing `model: Qwen/Qwen3.6-27B`, `api_key: ***`, `enable_thinking: False`, `tool_call_parser: qwen3_coder`, `language_model_only: True` | vLLM accepted every setting |
| "You are sending unauthenticated requests to the HF Hub" | harmless for an open model |
| "Resolved architecture: Qwen3_5ForConditionalGeneration" | vLLM recognises the model |
| "Fetching 14 files ... 100%" | model files found/downloaded |
| "running in text-only mode" | `--language-model-only` working |
| `torch ... is deprecated` | harmless warnings |

Then vLLM loads the weights onto the GPU (several minutes). **Ready** looks like:
`Application startup complete` or `Uvicorn running on http://0.0.0.0:8000`.

Also copy the **vLLM version** line from the top of the log into the ADR (the image tag is
`latest`, which changes over time, so the exact version is what you must record).

If it stops with an error, copy the last 20 lines. Common causes: out of GPU memory (lower
`--max-model-len` to 8192), or a flag the installed vLLM does not know (remove only the flag it
names).

---

## 8. Test from your PC

```powershell
Copy-Item env.qwen .env
uv run python scripts/phase5_check_endpoint.py --rounds 5
```

It checks that the server answers and lists your model, that the model returns valid structured
output citing only fact ids it was given, and how long a call takes compared with the timeout.

- **5/5 valid:** go on to the smoke test (guide step 5).
- **Failures:** most likely thinking is still on, a flag is missing, or the key does not match. Read
  the reason printed on each failed round.

---

## 9. Stopping and cost control

- Do the whole GPU session in one go: smoke test, record, evals, live run, injection run.
- When finished, **terminate** the pod (not only Stop). Stop pauses compute but storage can keep
  billing. Check the dashboard that nothing is still running.
- Write the stop time in the cost log. Cost per report (self-hosted) = rate x hours up / reports
  served, shown with how busy the GPU was. Convert dollars to pounds and write the rate used.
- Stop rule: if it is not working after the time you set, stop the pod and ask for help.

---

## 10. Checklist

- [ ] Model chosen and written in ADR-008 (id, size, licence, why)
- [ ] API model fully measured first (free of GPU cost)
- [ ] Key generated and stored safely; same key in 3 places
- [ ] Pod deployed, disk 120 GB, port 8000, start command and key set
- [ ] Cost log started (time, rate, GPU)
- [ ] Logs show the server is ready; vLLM version recorded
- [ ] `phase5_check_endpoint.py` passes
- [ ] `.env`, `.env.claude`, `env.qwen` ignored by git
- [ ] Pod terminated at the end; stop time logged

Honest limits: the flags come from the model card and a third-party serving write-up. The server
accepted them, but how well the model follows ukvet's output schema is only known after the
endpoint check and the smoke test.
