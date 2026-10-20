from typing import Any

import pytest
from pydantic import SecretStr
from ukvet_agent.errors import AgentConfigError
from ukvet_agent.llm import LangChainNarrativeWriter, LlmSettings, NarrativeDraft, build_writer


def settings(**kw: Any) -> LlmSettings:
    return LlmSettings(_env_file=None, **kw)  # type: ignore[call-arg]


def test_default_is_template_only() -> None:
    assert build_writer(settings()) is None


@pytest.mark.parametrize(
    ("kw", "needle"),
    [
        ({"provider": "openai"}, "LLM_MODEL"),
        ({"provider": "openai", "model": "m"}, "LLM_API_KEY"),
        ({"provider": "anthropic", "model": "m"}, "LLM_API_KEY"),
        ({"provider": "openai_compatible", "model": "m"}, "LLM_BASE_URL"),
    ],
)
def test_misconfiguration_fails_fast(kw: dict[str, Any], needle: str) -> None:
    with pytest.raises(AgentConfigError, match=needle):
        build_writer(settings(**kw))


def test_builds_each_provider_without_network() -> None:
    for kw in (
        {"provider": "openai", "model": "gpt-x", "api_key": SecretStr("k")},
        {"provider": "anthropic", "model": "claude-x", "api_key": SecretStr("k")},
        {
            "provider": "openai_compatible",
            "model": "llama",
            "base_url": "http://localhost:11434/v1",
        },
    ):
        writer = build_writer(settings(**kw))
        assert writer is not None and writer.model_name == kw["model"]


def test_api_key_is_not_leaked_in_repr() -> None:
    assert "secret-value" not in repr(settings(api_key=SecretStr("secret-value")))


class FakeChat:
    def __init__(self, result: Any) -> None:
        self.result = result
        self.seen: list[Any] = []

    def with_structured_output(self, schema: type) -> "FakeChat":
        assert schema is NarrativeDraft
        return self

    async def ainvoke(self, messages: list[Any]) -> Any:
        self.seen = messages
        return self.result


async def test_writer_accepts_model_or_dict() -> None:
    payload = {"headline": {"text": "h", "fact_ids": ["Q1.status"]}, "findings": []}
    for result in (NarrativeDraft.model_validate(payload), payload):
        chat = FakeChat(result)
        out = await LangChainNarrativeWriter(chat, "m").write("sys", "usr")
        assert out.headline.text == "h"
        assert chat.seen == [("system", "sys"), ("human", "usr")]


async def test_writer_rejects_malformed_output() -> None:
    with pytest.raises(ValueError, match="headline"):
        await LangChainNarrativeWriter(FakeChat({"findings": []}), "m").write("s", "u")
