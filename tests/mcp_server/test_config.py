import pytest
from ukvet_mcp.config import Settings, load_settings
from ukvet_mcp.errors import ConfigError


def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in list(__import__("os").environ):
        if name.startswith(("CH_", "UKVET_")):
            monkeypatch.delenv(name)


def test_key_loaded_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    _clean_env(monkeypatch)
    monkeypatch.setenv("CH_API_KEY", "abc123")
    assert load_settings(env_file=None).api_key.get_secret_value() == "abc123"


@pytest.mark.parametrize("raw", ['"abc123"', "'abc123'", "  abc123  ", ' "abc123" '])
def test_pasted_quotes_and_whitespace_are_tolerated(
    monkeypatch: pytest.MonkeyPatch, raw: str
) -> None:
    _clean_env(monkeypatch)
    monkeypatch.setenv("CH_API_KEY", raw)
    assert load_settings(env_file=None).api_key.get_secret_value() == "abc123"


def test_missing_key_gives_actionable_message(monkeypatch: pytest.MonkeyPatch) -> None:
    _clean_env(monkeypatch)
    with pytest.raises(ConfigError) as err:
        load_settings(env_file=None)
    message = str(err.value)
    assert "CH_API_KEY" in message
    assert "developer.company-information.service.gov.uk" in message
    assert "Traceback" not in message


def test_key_with_inner_space_rejected_without_echoing_it(monkeypatch: pytest.MonkeyPatch) -> None:
    _clean_env(monkeypatch)
    monkeypatch.setenv("CH_API_KEY", "ab cd")
    with pytest.raises(ConfigError) as err:
        load_settings(env_file=None)
    assert "ab cd" not in str(err.value)


def test_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    _clean_env(monkeypatch)
    s = Settings(api_key="k", _env_file=None)  # type: ignore[call-arg]
    assert s.base_url == "https://api.company-information.service.gov.uk"
    assert s.cache_enabled is True
    assert s.cache_ttl_hours == 24
    assert s.cache_ttl_seconds == 24 * 3600
    assert s.max_attempts == 3
    assert s.max_items == 100
    assert s.effective_rate_limit == 540  # 600 * 0.9


def test_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    _clean_env(monkeypatch)
    monkeypatch.setenv("CH_API_KEY", "k")
    monkeypatch.setenv("UKVET_CACHE_TTL_HOURS", "2")
    monkeypatch.setenv("UKVET_CACHE_ENABLED", "false")
    monkeypatch.setenv("UKVET_MAX_ITEMS", "25")
    s = load_settings(env_file=None)
    assert s.cache_ttl_hours == 2
    assert s.cache_enabled is False
    assert s.max_items == 25


def test_invalid_safety_value_is_a_config_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _clean_env(monkeypatch)
    monkeypatch.setenv("CH_API_KEY", "k")
    monkeypatch.setenv("UKVET_RATE_LIMIT_SAFETY", "1.5")
    with pytest.raises(ConfigError, match="Invalid configuration"):
        load_settings(env_file=None)


def test_secret_is_masked_everywhere() -> None:
    s = Settings(api_key="super-secret-key", _env_file=None)  # type: ignore[call-arg]
    for rendering in (repr(s), str(s), s.model_dump_json(), str(s.api_key)):
        assert "super-secret-key" not in rendering
    assert s.api_key.get_secret_value() == "super-secret-key"
