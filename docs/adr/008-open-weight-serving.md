# ADR-008: Serving the open-weight model for the Phase 5 comparison

| Field | Value |
|---|---|
| Status | Accepted |
| Date | 5 November 2026 |
| Related | ADR-003 (LLM abstraction), ADR-007 (deterministic researcher), risk R13 |

## Context

Phase 5 compares one frontier API model (Claude) with one open-weight model on the same dataset
version, split, prompt and git commit. The open-weight model must be reachable through an
OpenAI-compatible endpoint so that ukvet needs only a settings change
(`LLM_PROVIDER=openai_compatible`), as ADR-003 intended. The comparison measures M1, M2, M4, M6,
M7 and M8.

## Decision

Serve **Qwen/Qwen3.6-27B** with vLLM on one rented GPU on RunPod, and point ukvet at it through
the pod's HTTPS proxy.

### The model

| Item | Value |
|---|---|
| Model (Hugging Face id) | `Qwen/Qwen3.6-27B` |
| Size | 27B parameters, dense |
| Quantisation | none (bf16) |
| Licence | Apache 2.0 (from the model card) |
| Context served | 16,384 tokens (native 262,144; ukvet prompts are small) |
| Why this model | Passed four checks: structured output and tool calling are supported in vLLM; fits one rentable 80 GB GPU; a permissive licence I can cite; recent (2026). A dense model is simpler to serve and explain than the mixture-of-experts alternatives |

### The hardware and software

| Item | Value |
|---|---|
| Provider | RunPod, Secure Cloud, region US-MD-1 |
| GPU | 1x NVIDIA A100 SXM (80 GB), 16 vCPU, 250 GB RAM |
| Container disk | 120 GB |
| Price | $1.81 per hour ($1.79 compute + $0.017 storage) = £1.35 per hour (about 0.75 USD to GBP, 5 Nov 2026) |
| Serving software | vLLM, run from the RunPod "vLLM Latest" template (image `vllm/vllm-openai:latest`) |
| vLLM version | 0.33.0 (the image tag was `latest`, so the version from the log is what counts; Qwen3.6 needs 0.19.0 or newer) |
| Pod started / stopped | 5 Nov 2026, about 17:59 to about 20:21 (2 h 22 m, about £3.20). Live latency run: 0.168 h, 30 reports. Pod terminated afterwards |

### How it was started

Container start command in RunPod's Edit Pod (the vLLM image already runs `vllm serve`, so only the
arguments are given; the key is not recorded here):

```
Qwen/Qwen3.6-27B --host 0.0.0.0 --port 8000 --api-key <KEY> --max-model-len 16384 \
  --enable-auto-tool-choice --tool-call-parser qwen3_coder --language-model-only \
  --default-chat-template-kwargs '{"enable_thinking": false}'
```

| Setting | Why |
|---|---|
| `--enable-auto-tool-choice --tool-call-parser qwen3_coder` | required for structured / tool output with this model; without the parser, tool calls fail silently |
| `--language-model-only` | skips the image part of the model, freeing GPU memory |
| `--default-chat-template-kwargs '{"enable_thinking": false}'` | **thinking is on by default** for this model; it adds a long hidden reasoning block that slows each report and can use the token limit before the answer starts. Switched off for the comparison |
| `--max-model-len 16384` | enough for ukvet's prompts; saves memory |

Environment variables: `VLLM_API_KEY` set to my own key (the template default, `sk-` plus the pod
id, is guessable and was replaced). `HF_HOME` left as the template set it.

### How ukvet connects

```
LLM_PROVIDER=openai_compatible
LLM_MODEL=Qwen/Qwen3.6-27B
LLM_BASE_URL=https://<pod-id>-8000.proxy.runpod.net/v1
LLM_TEMPERATURE=0
LLM_TIMEOUT_SECONDS=60
```

Same temperature and timeout as the Claude run, so neither the timeout nor sampling decides the
winner. The model card suggests temperature 0.7 for non-thinking use; 0 was used for fairness, and
any repetition in outputs may come from that.

### Access control

The endpoint is reachable through RunPod's public proxy URL, so the API key is the only protection.
It is a long random key, stored in a password manager and in git-ignored env files, and it was never
committed. The pod is terminated at the end of the experiment.

## Checks done

- `scripts/phase5_check_endpoint.py`: the server listed the model; structured answers were valid
  (3 of 5 rounds at first; the 2 failures were a bug in the check script, which used a new event
  loop per round, not the server; the script was fixed).
- Smoke test (`phase4_metrics.py`, 2 real companies): 2 of 2 reports written by the LLM, 0 template
  fallbacks, 0 retries, 0 dropped claims; 24.1 s and 19.5 s per report, almost all of it the model
  writing (about 20 s for about 550 output tokens). Too few runs to judge M7.

## Alternatives considered

| Option | Why not |
|---|---|
| Hosted open-weight endpoint (Together, Groq, OpenRouter) | cheaper and faster to set up, but latency and cost would then describe that provider, not self-hosting. Kept as a labelled fallback only |
| Ollama on a laptop | fine for a smoke test, meaningless as a latency number |
| `Qwen/Qwen3.6-35B-A3B` (mixture of experts) | fits a smaller GPU when quantised, but its licence was not stated on the page I read and its tool calling was very new; kept as a backup |
| A docker-compose file for vLLM | RunPod already runs the container from the template, so compose added nothing here; removed |

## Consequences

- The recordings in `evals/llm_cache` belong to this model id and the current prompt text. Editing
  `reporter_system.md` invalidates them.
- Self-hosted cost per report depends on how long the GPU is billed. The comparison uses the hours
  of the live latency run (no idle time) and records the whole-session spend separately; both are
  stated next to the number in `docs/results.md`.
- One open-weight model, one run each. Results describe this model on this hardware with thinking
  off; they do not transfer to other models, GPUs or settings.
- The endpoint was publicly reachable behind a key during the experiment. Anyone repeating this
  should use a long random key and shut the pod down when finished.
