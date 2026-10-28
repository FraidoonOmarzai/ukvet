"""Optional Langfuse tracing (Phase 4). Does nothing unless keys are set.

One trace per report, one span per graph node, one span per tool call, and every LLM call with
its token counts (through Langfuse's LangChain callback). Rules:

* OFF by default. With no `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY`, `get_tracer()` returns a
  no-op tracer, so tests, CI and anyone without a Langfuse account are unaffected.
* If the `langfuse` package is not installed, we log one warning and carry on untraced.
* PRIVACY: prompts contain director names. `UKVET_TRACE_CONTENT=redacted` (the default) sends no
  inputs, outputs or metadata to Langfuse at all: only names, timings, token counts and costs.
  Set `UKVET_TRACE_CONTENT=full` only on a private project, with a short retention period.
* Tracing can never break a report: SDK errors are logged and swallowed.
"""

import logging
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager, nullcontext
from typing import Any, Literal, Protocol

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from ukvet_agent import usage
from ukvet_agent.mcp_client import ToolClient, ToolOutcome

log = logging.getLogger("ukvet_agent.tracing")


class TraceSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", populate_by_name=True
    )

    public_key: SecretStr | None = Field(
        default=None, validation_alias=AliasChoices("LANGFUSE_PUBLIC_KEY", "public_key")
    )
    secret_key: SecretStr | None = Field(
        default=None, validation_alias=AliasChoices("LANGFUSE_SECRET_KEY", "secret_key")
    )
    host: str | None = Field(
        default=None,
        validation_alias=AliasChoices("LANGFUSE_HOST", "LANGFUSE_BASE_URL", "host"),
    )
    content: Literal["redacted", "full"] = Field(
        default="redacted", validation_alias=AliasChoices("UKVET_TRACE_CONTENT", "content")
    )

    @property
    def configured(self) -> bool:
        return self.public_key is not None and self.secret_key is not None


class SpanHandle(Protocol):
    def fail(self, message: str) -> None: ...


class Tracer(Protocol):
    enabled: bool

    def report(self, request: str) -> AbstractContextManager[Any]: ...
    def node(self, name: str) -> AbstractContextManager[Any]: ...
    def tool(self, name: str, arguments: dict[str, Any]) -> AbstractContextManager[Any]: ...
    def llm_callbacks(self) -> list[Any]: ...
    def flush(self) -> None: ...


class NoopTracer:
    """The default. Every method does nothing and costs nothing."""

    enabled = False

    def report(self, request: str) -> AbstractContextManager[Any]:
        return nullcontext()

    def node(self, name: str) -> AbstractContextManager[Any]:
        return nullcontext()

    def tool(self, name: str, arguments: dict[str, Any]) -> AbstractContextManager[Any]:
        return nullcontext()

    def llm_callbacks(self) -> list[Any]:
        return []

    def flush(self) -> None:
        return None


class _Handle:
    def __init__(self, span: Any) -> None:
        self._span = span

    def fail(self, message: str) -> None:
        try:
            self._span.update(level="WARNING", status_message=message[:200])
        except Exception:  # tracing must never break a report
            log.debug("could not mark span as failed", exc_info=True)


def _mask_everything(*, data: Any, **_: Any) -> str:
    return "[redacted]"


class LangfuseTracer:
    enabled = True

    def __init__(self, settings: TraceSettings) -> None:
        from langfuse import Langfuse  # imported here so the package stays optional

        kwargs: dict[str, Any] = {
            "public_key": settings.public_key.get_secret_value() if settings.public_key else None,
            "secret_key": settings.secret_key.get_secret_value() if settings.secret_key else None,
        }
        if settings.host:
            kwargs["base_url"] = settings.host
        if settings.content == "redacted":
            kwargs["mask"] = _mask_everything
        self._client = Langfuse(**kwargs)

    @contextmanager
    def _observation(self, name: str, kind: str) -> Iterator[_Handle | None]:
        try:
            cm = self._client.start_as_current_observation(name=name, as_type=kind)  # type: ignore[call-overload]
            span = cm.__enter__()
        except Exception:
            log.warning("tracing: could not start span %s", name, exc_info=True)
            yield None
            return
        try:
            yield _Handle(span)
        except BaseException as exc:
            try:
                cm.__exit__(type(exc), exc, exc.__traceback__)
            except Exception:
                log.debug("tracing: span exit failed", exc_info=True)
            raise
        else:
            try:
                cm.__exit__(None, None, None)
            except Exception:
                log.debug("tracing: span exit failed", exc_info=True)

    def report(self, request: str) -> AbstractContextManager[Any]:
        return self._observation("ukvet.report", "agent")

    def node(self, name: str) -> AbstractContextManager[Any]:
        return self._observation(f"node.{name}", "chain")

    def tool(self, name: str, arguments: dict[str, Any]) -> AbstractContextManager[Any]:
        return self._observation(f"tool.{name}", "tool")

    def llm_callbacks(self) -> list[Any]:
        try:
            from langfuse.langchain import CallbackHandler

            return [CallbackHandler()]
        except Exception:
            log.warning(
                "tracing: LangChain callback unavailable; LLM calls untraced", exc_info=True
            )
            return []

    def flush(self) -> None:
        try:
            self._client.flush()
        except Exception:
            log.debug("tracing: flush failed", exc_info=True)


_tracer: Tracer | None = None


def build_tracer(settings: TraceSettings | None = None) -> Tracer:
    s = settings or TraceSettings()
    if not s.configured:
        return NoopTracer()
    try:
        return LangfuseTracer(s)
    except ImportError:
        log.warning("LANGFUSE_* keys are set but the 'langfuse' package is not installed")
    except Exception:
        log.warning("tracing disabled: could not start Langfuse", exc_info=True)
    return NoopTracer()


def get_tracer() -> Tracer:
    global _tracer
    if _tracer is None:
        _tracer = build_tracer()
        if _tracer.enabled:
            log.info("Langfuse tracing is ON")
    return _tracer


def set_tracer(tracer: Tracer | None) -> None:
    """Install a tracer (tests), or None to rebuild from the environment on next use."""
    global _tracer
    _tracer = tracer


def flush_tracer() -> None:
    """Send buffered traces. Call before the process exits (short CLI runs would lose them)."""
    if _tracer is not None:
        _tracer.flush()


class TracedTools:
    """Wraps a ToolClient: counts every call for `Report.usage` and opens a span per call."""

    def __init__(self, inner: ToolClient, tracer: Tracer | None = None) -> None:
        self._inner = inner
        self._tracer = tracer

    async def ping(self) -> int:
        return await self._inner.ping()

    async def call(self, name: str, arguments: dict[str, Any]) -> ToolOutcome:
        recorder = usage.current()
        if recorder is not None:
            recorder.tool_call(name)
        tracer = self._tracer or get_tracer()
        with tracer.tool(name, arguments) as span:
            outcome = await self._inner.call(name, arguments)
            if not outcome.ok and span is not None and hasattr(span, "fail"):
                span.fail(outcome.error or "tool call failed")
        return outcome
