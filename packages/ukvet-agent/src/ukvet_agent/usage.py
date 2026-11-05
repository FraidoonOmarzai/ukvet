"""Per-report work counters: tool calls, LLM calls, tokens and cost (metrics M8 and M9).

Always on and fully local: no network, no Langfuse needed. `run_report` starts a recorder for each
report, `TracedTools` counts tool calls, and `UsageCallback` (a LangChain callback attached by the
LLM writer) adds token counts. The totals end up in `Report.usage`.

Cost needs a price per million tokens, which depends on the model you chose. Set both in `.env`
(copy them from your provider's price page, converted to GBP):

    UKVET_PRICE_IN_GBP_PER_MTOK=...
    UKVET_PRICE_OUT_GBP_PER_MTOK=...

Without prices, `cost_gbp` stays `None`. We do not guess prices.
"""

from contextvars import ContextVar, Token
from functools import lru_cache
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from ukvet_agent.schemas import Usage


class UsageSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", populate_by_name=True
    )

    price_in_gbp_per_mtok: float | None = Field(
        default=None,
        ge=0,
        validation_alias=AliasChoices("UKVET_PRICE_IN_GBP_PER_MTOK", "price_in_gbp_per_mtok"),
    )
    price_out_gbp_per_mtok: float | None = Field(
        default=None,
        ge=0,
        validation_alias=AliasChoices("UKVET_PRICE_OUT_GBP_PER_MTOK", "price_out_gbp_per_mtok"),
    )


@lru_cache(maxsize=1)
def usage_settings() -> UsageSettings:
    return UsageSettings()


class UsageRecorder:
    """Mutable counters for ONE report. Shared by reference, so async tasks all add to it."""

    def __init__(self) -> None:
        self.tools: list[str] = []
        self.llm_calls = 0
        self.input_tokens = 0
        self.output_tokens = 0

    def tool_call(self, name: str) -> None:
        self.tools.append(name)

    def llm_call(self, input_tokens: int, output_tokens: int) -> None:
        self.llm_calls += 1
        self.input_tokens += max(0, input_tokens)
        self.output_tokens += max(0, output_tokens)

    def snapshot(self, settings: UsageSettings | None = None) -> Usage:
        s = settings or usage_settings()
        cost: float | None = None
        if s.price_in_gbp_per_mtok is not None and s.price_out_gbp_per_mtok is not None:
            cost = round(
                (self.input_tokens * s.price_in_gbp_per_mtok
                 + self.output_tokens * s.price_out_gbp_per_mtok) / 1_000_000,
                6,
            )  # fmt: skip
        return Usage(
            tool_calls=len(self.tools),
            tools=list(self.tools),
            llm_calls=self.llm_calls,
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            cost_gbp=cost,
        )


_current: ContextVar[UsageRecorder | None] = ContextVar("ukvet_usage", default=None)


def start() -> tuple[UsageRecorder, Token[UsageRecorder | None]]:
    recorder = UsageRecorder()
    return recorder, _current.set(recorder)


def stop(token: Token[UsageRecorder | None]) -> None:
    _current.reset(token)


def current() -> UsageRecorder | None:
    return _current.get()


class UsageCallback(BaseCallbackHandler):
    """LangChain callback that adds one LLM call and its token counts to a recorder.

    It holds the recorder directly (not a context variable) because LangChain may run sync
    callbacks in another thread, where the context variable would not be visible.
    """

    def __init__(self, recorder: UsageRecorder) -> None:
        self._recorder = recorder

    def on_llm_end(self, response: Any, **kwargs: Any) -> None:
        tokens_in = tokens_out = 0
        for generations in getattr(response, "generations", []):
            for generation in generations:
                meta = getattr(getattr(generation, "message", None), "usage_metadata", None)
                if meta:
                    tokens_in += int(meta.get("input_tokens", 0))
                    tokens_out += int(meta.get("output_tokens", 0))
        if tokens_in == 0 and tokens_out == 0:
            usage = (getattr(response, "llm_output", None) or {}).get("token_usage") or {}
            tokens_in = int(usage.get("prompt_tokens", 0))
            tokens_out = int(usage.get("completion_tokens", 0))
        self._recorder.llm_call(tokens_in, tokens_out)
