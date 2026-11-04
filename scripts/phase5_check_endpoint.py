"""Smoke-test the configured LLM endpoint BEFORE a full Phase 5 run.

    uv run python scripts/phase5_check_endpoint.py            # 5 rounds
    uv run python scripts/phase5_check_endpoint.py --rounds 10

Reads LLM_* from .env exactly like the agent does. It checks, in order:
  1. the server answers GET <LLM_BASE_URL>/models and lists LLM_MODEL (openai_compatible only);
  2. the real writer returns valid structured output (the NarrativeDraft schema) on a tiny prompt,
     citing only fact ids it was given;
  3. how long a call takes against LLM_TIMEOUT_SECONDS.

Exit codes: 0 all rounds good, 1 some rounds failed (fix serving before a full run), 2 cannot
connect or bad configuration. Costs a few thousand tokens at most.
"""

import argparse
import asyncio
import sys
import time

import httpx
from ukvet_agent.errors import AgentConfigError
from ukvet_agent.llm import LlmSettings, build_writer

SYSTEM = (
    "You write one-sentence statements about a UK company using ONLY the facts given. "
    "Every statement must list the ids of the facts it relies on in fact_ids."
)
USER = (
    "Facts:\n"
    "- Q1.status: ACME LTD (12345678) has status 'active'.\n"
    "- Q2.age: ACME LTD was incorporated on 2 March 2015.\n\n"
    "Write a headline about the status, and one finding about the age."
)
ALLOWED = {"Q1.status", "Q2.age"}


def list_models(base_url: str, key: str | None) -> list[str]:
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    r = httpx.get(base_url.rstrip("/") + "/models", headers=headers, timeout=10)
    r.raise_for_status()
    return [m["id"] for m in r.json().get("data", [])]


async def one_round(settings: LlmSettings) -> tuple[bool, float, str]:
    writer = build_writer(settings)
    assert writer is not None
    start = time.perf_counter()
    try:
        draft = await asyncio.wait_for(writer.write(SYSTEM, USER), settings.timeout_seconds + 5)
    except Exception as exc:  # any failure is a finding here
        return False, time.perf_counter() - start, f"{type(exc).__name__}: {str(exc)[:120]}"
    took = time.perf_counter() - start
    cited = {i for c in [draft.headline, *draft.findings] for i in c.fact_ids}
    if not draft.headline.text.strip():
        return False, took, "empty headline"
    if not cited:
        return False, took, "no fact ids cited"
    if not cited <= ALLOWED:
        return False, took, f"cited ids it was not given: {sorted(cited - ALLOWED)}"
    return True, took, "ok"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--rounds", type=int, default=5)
    args = ap.parse_args()
    settings = LlmSettings()
    if settings.provider == "none":
        print("LLM_PROVIDER is none. Set LLM_PROVIDER, LLM_MODEL (and LLM_BASE_URL) in .env.")
        return 2
    print(
        f"provider={settings.provider} model={settings.model} base_url={settings.base_url} "
        f"timeout={settings.timeout_seconds}s temperature={settings.temperature}"
    )
    if settings.provider == "openai_compatible" and settings.base_url:
        key = settings.api_key.get_secret_value() if settings.api_key else None
        try:
            ids = list_models(settings.base_url, key)
        except httpx.HTTPError as exc:
            print(f"CANNOT REACH the server: {exc}")
            return 2
        print(f"server lists: {ids}")
        if settings.model not in ids:
            print(f"LLM_MODEL '{settings.model}' is not in that list. Use the exact id.")
            return 2
    try:
        build_writer(settings)
    except AgentConfigError as exc:
        print(f"configuration error: {exc}")
        return 2

    good = 0
    times: list[float] = []
    for i in range(1, args.rounds + 1):
        ok, took, why = asyncio.run(one_round(settings))
        good += ok
        times.append(took)
        print(f"round {i}: {'ok  ' if ok else 'FAIL'} {took:5.1f}s  {why}")
    print(
        f"\n{good}/{args.rounds} valid structured answers; "
        f"mean {sum(times) / len(times):.1f}s, slowest {max(times):.1f}s "
        f"(timeout {settings.timeout_seconds:.0f}s)"
    )
    if max(times) > settings.timeout_seconds * 0.8:
        print("Slowest call is close to the timeout: raise LLM_TIMEOUT_SECONDS for BOTH models.")
    if good < args.rounds:
        print(
            "Some rounds failed: fix structured-output serving before a full run (see the guide)."
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
