"""Settings, read from environment variables (and an optional `.env` file).

Fails fast with a clear message when the API key is missing. The key is a `SecretStr`, so it is
masked in `repr()`, `str()`, logs and tracebacks.

This code is a configuration manager for your UK Companies House MCP project.
Its job is to load settings (API key, timeouts, caching, rate limits, etc.), validate them,
protect sensitive values, and give a clear error if the configuration is wrong.
Think of it as the place where your application decides: “What settings should I use when I run?”
"""

import math
from pathlib import Path
from typing import Any

from pydantic import AliasChoices, Field, SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from ukvet_mcp.errors import ConfigError

API_KEY_HELP = (
    "CH_API_KEY is not set. Get a free key at "
    "https://developer.company-information.service.gov.uk/ (create an application, then create "
    "a REST key for the LIVE environment), and set CH_API_KEY in your environment or in a "
    ".env file."
)


# choose where the cache lives by default, 
# if the user doesn't override it
def _default_cache_path() -> Path:
    """this builds a path to a local SQLite cache database, e.g. ~/.cache/ukvet/ch_cache.sqlite"""
    return Path.home() / ".cache" / "ukvet" / "ch_cache.sqlite"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # ignore unrecognised entries in the 
        # .env file rather than rejecting the configuration because of them
        populate_by_name=True,
    )

    api_key: SecretStr = Field(validation_alias=AliasChoices("CH_API_KEY", "api_key"))
    # AliasChoices("CH_API_KEY", "api_key") allows the 
    # configuration to be supplied using either name
    base_url: str = Field(
        default="https://api.company-information.service.gov.uk",
        validation_alias=AliasChoices("CH_BASE_URL", "base_url"),
    )
    # How long to wait for an HTTP operation (connect, read, etc.) 
    # before giving up. The default is 20 seconds.
    timeout_seconds: float = Field(
        default=20.0,
        gt=0,
        validation_alias=AliasChoices("UKVET_HTTP_TIMEOUT_SECONDS", "timeout_seconds"),
    )
    # How many times to retry a failed request before giving up. 
    # The default is 3, and the maximum is 6.
    max_attempts: int = Field(
        default=3,
        ge=1,
        le=6,
        validation_alias=AliasChoices("UKVET_MAX_ATTEMPTS", "max_attempts"),
    )
    # Whether to enable caching. The default is True.
    cache_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("UKVET_CACHE_ENABLED", "cache_enabled"),
    )
    # How long to keep cached responses before considering them stale. 
    # The default is 24 hours.
    cache_ttl_hours: float = Field(
        default=24.0,
        gt=0,
        validation_alias=AliasChoices("UKVET_CACHE_TTL_HOURS", "cache_ttl_hours"),
    )
    # Where to store the cache. The default is ~/.cache/ukvet/ch_cache.sqlite.
    cache_path: Path = Field(
        default_factory=_default_cache_path,
        validation_alias=AliasChoices("UKVET_CACHE_PATH", "cache_path"),
    )
    rate_limit_requests: int = Field(
        default=600,
        ge=1,
        validation_alias=AliasChoices("UKVET_RATE_LIMIT_REQUESTS", "rate_limit_requests"),
    )
    # The time window (in seconds) for rate limiting. 
    # The default is 300 seconds (5 minutes).
    rate_limit_window_seconds: int = Field(
        default=300,
        ge=1,
        validation_alias=AliasChoices(
            "UKVET_RATE_LIMIT_WINDOW_SECONDS", "rate_limit_window_seconds"
        ),
    )
    rate_limit_safety: float = Field(
        default=0.9,
        gt=0,
        le=1,
        validation_alias=AliasChoices("UKVET_RATE_LIMIT_SAFETY", "rate_limit_safety"),
    )
    # The maximum number of items to return in a single response. 
    # The default is 100, and the maximum is 500.
    max_items: int = Field(
        default=100,
        ge=1,
        le=500,
        validation_alias=AliasChoices("UKVET_MAX_ITEMS", "max_items"),
    )

    @field_validator(
        "api_key", mode="before"
    )  # tells Pydantic to run this function when validating the API key
    @classmethod
    def _clean_key(cls, value: Any) -> Any:
        """Tolerate pasted quotes/whitespace; reject empty or key-with-spaces."""
        if isinstance(value, SecretStr):
            value = value.get_secret_value()
        if isinstance(value, str):
            value = value.strip().strip("'\"").strip()
            if not value or any(ch.isspace() for ch in value):
                raise ValueError("must be a non-empty key with no spaces")

        return value

    # This calculates how many requests the application should allow 
    # within a rate-limit window after applying a safety margin
    @property
    def effective_rate_limit(self) -> int:
        """Requests allowed per window, after the safety margin."""
        return max(1, math.floor(self.rate_limit_requests * self.rate_limit_safety))

    @property
    def cache_ttl_seconds(self) -> float:
        """convert cache TTL from hours to seconds for use in the cache implementation"""
        return self.cache_ttl_hours * 3600.0


def load_settings(env_file: str | None = ".env") -> Settings:
    """Load settings or raise `ConfigError` with a message that says how to fix it."""
    try:
        return Settings(_env_file=env_file)  # type: ignore[call-arg]
    except ValidationError as err:
        problems: list[str] = []
        for item in err.errors(include_input=False, include_url=False):
            loc = ".".join(str(part) for part in item["loc"])
            if loc in {"CH_API_KEY", "api_key"} and item["type"] == "missing":
                raise ConfigError(API_KEY_HELP) from None
            problems.append(f"{loc}: {item['msg']}")
        raise ConfigError("Invalid configuration: " + "; ".join(problems)) from None


if __name__ == "__main__":
    s = load_settings()

    print(s)
    print("rate limit:", s.effective_rate_limit)
