# Phase 5, Step 2: model decision (filled in)

Paste the table into `docs/adr/008-open-weight-serving.md`.

| Item | Value |
|---|---|
| Model (HF id) | `Qwen/Qwen3.6-27B` |
| Parameters / quantisation | 27B dense, no quantisation (bf16) |
| Licence | Apache 2.0 (per the Hugging Face model card) |
| Context | 262,144 native; we serve 8192 to 16384 (ukvet prompts are small) |
| Serving software | vLLM, version 0.19.0 or newer (needed for the Qwen3.6 architecture); pin the exact tag you use |
| Hardware | one 80 GB GPU (27B in bf16 is about 54 GB of weights, plus room for the KV cache). Record the GPU type, provider and price per hour when you rent it |
| Structured output / tool flags | `--enable-auto-tool-choice --tool-call-parser qwen3_coder` (the model card and a serving write-up both say the parser is required for tool calls, otherwise they fail silently); thinking switched OFF (see below) |
| Why this model | Passed the four checks: supports tool calling and structured output in vLLM; fits one rentable 80 GB GPU; permissive licence I can cite; recent (2026). Dense 27B is simpler to serve and to explain than the mixture-of-experts alternatives |

## Two things to know before you serve it
1. **Thinking mode is on by default.** It makes the model write a long hidden reasoning block
   first. That inflates latency (M7) and tokens, and ukvet's default `LLM_MAX_TOKENS=1200` could be
   used up before the JSON answer starts, which would look like a model failure. Turn thinking off
   for this comparison and say so in the ADR. The model card does this per request with
   `chat_template_kwargs {"enable_thinking": false}`. ukvet's writer does not send that today, so
   either set it as a server default (check `vllm serve --help` for `--default-chat-template-kwargs`
   on your vLLM version) or tell me and I will add an `LLM_EXTRA_BODY` setting to the writer.
2. **Temperature.** The card recommends 0.7 for non-thinking use; we keep `LLM_TEMPERATURE=0` for
   both models so the comparison is fair. Note this in the ADR. If outputs look repetitive, that is
   the reason.
 
## `docker/vllm/vllm.env` (copy of the example, filled in; never commit)
```
VLLM_TAG=<pin a stable vLLM release >= 0.19.0 from the vLLM releases page>
MODEL=Qwen/Qwen3.6-27B
VLLM_API_KEY=<long random string>
HF_TOKEN=
MAX_MODEL_LEN=16384
DTYPE=auto
VLLM_EXTRA_ARGS=--enable-auto-tool-choice --tool-call-parser qwen3_coder --language-model-only --default-chat-template-kwargs {"enable_thinking":false}
```
If compose mangles the quotes in the last line, run vLLM directly on the GPU box instead:
```
docker run --gpus all --ipc=host -p 127.0.0.1:8000:8000 -v hf-cache:/root/.cache/huggingface \
  vllm/vllm-openai:<tag> --model Qwen/Qwen3.6-27B --api-key <key> --max-model-len 16384 \
  --enable-auto-tool-choice --tool-call-parser qwen3_coder --language-model-only \
  --default-chat-template-kwargs '{"enable_thinking": false}'
```
Flag names come from the model card and a serving write-up and are NOT tested by me. If vLLM
rejects one, run `vllm serve --help` and tell me the error.

## Your `.env` on your PC
```
LLM_PROVIDER=openai_compatible
LLM_MODEL=Qwen/Qwen3.6-27B
LLM_BASE_URL=http://127.0.0.1:8000/v1
LLM_API_KEY=<same key>
LLM_TEMPERATURE=0
LLM_TIMEOUT_SECONDS=60
```
Then run `uv run python scripts/phase5_check_endpoint.py`. If it says the structured answers are
invalid, thinking is probably still on or the tool parser flag is missing.

## Backup if 80 GB GPU is too expensive or unavailable
`Qwen/Qwen3.6-35B-A3B` (mixture of experts, 3B active, so faster) fits a 24 GB card in a
quantised form, but the page I read did not state its licence and the serving write-up said its
tool calling was only days old. Check the licence on its card before using it.
