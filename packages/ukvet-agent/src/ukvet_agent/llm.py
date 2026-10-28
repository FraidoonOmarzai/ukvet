"""LLM access: a tiny provider-agnostic writer on top of LangChain chat models.

The Reporter is the ONLY place an LLM is used. It has no tools and returns a structured
`NarrativeDraft` that the citation checker validates before anything is shown. With
`LLM_PROVIDER=none` (the default) no LLM is called and the report uses a deterministic template.

Providers:
  openai             OpenAI API (LLM_MODEL, LLM_API_KEY)
  anthropic          Anthropic API (LLM_MODEL, LLM_API_KEY)
  openai_compatible  any OpenAI-style endpoint, e.g. Groq, Together, OpenRouter, vLLM, Ollama
                     (LLM_MODEL, LLM_BASE_URL, LLM_API_KEY if required)
"""

from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from ukvet_agent.errors import AgentConfigError
from ukvet_agent.schemas import Claim
from ukvet_agent.tracing import get_tracer
from ukvet_agent.usage import UsageCallback
from ukvet_agent.usage import current as current_usage


class NarrativeDraft(BaseModel):
    headline: Claim
    findings: list[Claim] = Field(default_factory=list)


class NarrativeWriter(Protocol):
    model_name: str

    async def write(self, system: str, user: str) -> NarrativeDraft: ...


class LlmSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="LLM_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    provider: Literal["none", "openai", "anthropic", "openai_compatible"] = "none"
    model: str | None = None
    api_key: SecretStr | None = None
    base_url: str | None = None
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int = Field(default=1200, ge=100, le=8000)
    timeout_seconds: float = Field(default=15.0, gt=0)


class LangChainNarrativeWriter:
    """Wraps any LangChain chat model that supports structured output."""

    def __init__(self, chat_model: Any, model_name: str) -> None:
        self.model_name = model_name
        self._structured = chat_model.with_structured_output(NarrativeDraft)

    async def write(self, system: str, user: str) -> NarrativeDraft:
        messages = [("system", system), ("human", user)]
        callbacks: list[Any] = list(get_tracer().llm_callbacks())
        recorder = current_usage()
        if recorder is not None:
            callbacks.append(UsageCallback(recorder))
        if callbacks:
            result = await self._structured.ainvoke(messages, config={"callbacks": callbacks})
        else:
            result = await self._structured.ainvoke(messages)
        if isinstance(result, NarrativeDraft):
            return result
        return NarrativeDraft.model_validate(result)


def build_writer(settings: LlmSettings) -> NarrativeWriter | None:
    """Return a writer for the configured provider, or None for template-only mode."""
    if settings.provider == "none":
        return None
    if not settings.model:
        raise AgentConfigError(f"LLM_MODEL is required when LLM_PROVIDER={settings.provider}")
    key = settings.api_key.get_secret_value() if settings.api_key else None
    common: dict[str, Any] = {
        "max_tokens": settings.max_tokens,
        "timeout": settings.timeout_seconds,
    }
    if settings.temperature is not None:
        common["temperature"] = settings.temperature

    if settings.provider == "anthropic":
        if not key:
            raise AgentConfigError("LLM_API_KEY is required when LLM_PROVIDER=anthropic")
        from langchain_anthropic import ChatAnthropic

        chat: Any = ChatAnthropic(model_name=settings.model, api_key=SecretStr(key), **common)
    else:
        from langchain_openai import ChatOpenAI

        if settings.provider == "openai" and not key:
            raise AgentConfigError("LLM_API_KEY is required when LLM_PROVIDER=openai")
        if settings.provider == "openai_compatible" and not settings.base_url:
            raise AgentConfigError("LLM_BASE_URL is required when LLM_PROVIDER=openai_compatible")
        chat = ChatOpenAI(
            model=settings.model,
            api_key=SecretStr(key or "not-needed"),
            base_url=settings.base_url,
            **common,
        )
    return LangChainNarrativeWriter(chat, settings.model)
