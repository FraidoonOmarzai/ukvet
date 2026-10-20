"""Agent settings (environment variables / .env). LLM settings live in `llm.py`."""

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", populate_by_name=True
    )

    request_timeout_seconds: float = Field(
        default=45.0,
        gt=0,
        validation_alias=AliasChoices("UKVET_REQUEST_TIMEOUT_SECONDS", "request_timeout_seconds"),
    )
    tool_timeout_seconds: float = Field(
        default=20.0,
        gt=0,
        validation_alias=AliasChoices("UKVET_TOOL_TIMEOUT_SECONDS", "tool_timeout_seconds"),
    )
    max_directors: int = Field(
        default=5,
        ge=1,
        le=20,
        validation_alias=AliasChoices("UKVET_MAX_DIRECTORS", "max_directors"),
    )
    max_verifier_loops: int = Field(
        default=2,
        ge=0,
        le=5,
        validation_alias=AliasChoices("UKVET_MAX_LOOPS", "max_verifier_loops"),
    )
    max_concurrent_reports: int = Field(
        default=4,
        ge=1,
        le=50,
        validation_alias=AliasChoices("UKVET_MAX_CONCURRENT_REPORTS", "max_concurrent_reports"),
    )
    changes_window_days: int = Field(
        default=365,
        ge=30,
        le=1825,
        validation_alias=AliasChoices("UKVET_CHANGES_WINDOW_DAYS", "changes_window_days"),
    )
