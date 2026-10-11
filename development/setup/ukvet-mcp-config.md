# Configuration

The configuration module manages application settings for ukvet. It loads values from environment variables and an optional `.env` file, validates them, and provides clear errors when the configuration is invalid.

## Why we use it

- Centralises application settings in one `Settings` class.
- Loads configuration from environment variables and a `.env` file.
- Keeps the Companies House API key masked using Pydantic's `SecretStr`.
- Validates settings such as HTTP timeouts, retry attempts, cache TTL, and rate limits.
- Provides default values for optional settings.
- Calculates derived values such as the effective rate limit and cache TTL in seconds.
- Fails fast with a helpful error message when the API key is missing or settings are invalid.

## Configuration sources

- Environment variables, such as `CH_API_KEY`.
- An optional `.env` file for local development.
- Default values defined in the `Settings` class.

Environment variables take precedence over values in the `.env` file.

## Important settings

| Setting | Default | Purpose |
|---|---|---|
| `CH_API_KEY` | Required | Companies House API authentication |
| `CH_BASE_URL` | Companies House API URL | API endpoint base URL |
| `UKVET_HTTP_TIMEOUT_SECONDS` | `20.0` | HTTP timeout in seconds |
| `UKVET_MAX_ATTEMPTS` | `3` | Maximum retry attempts |
| `UKVET_CACHE_ENABLED` | `true` | Enables or disables caching |
| `UKVET_CACHE_TTL_HOURS` | `24.0` | Cache lifetime in hours |
| `UKVET_CACHE_PATH` | `~/.cache/ukvet/ch_cache.sqlite` | SQLite cache database path |
| `UKVET_RATE_LIMIT_REQUESTS` | `600` | Configured requests per rate-limit window |
| `UKVET_RATE_LIMIT_WINDOW_SECONDS` | `300` | Rate-limit window in seconds |
| `UKVET_RATE_LIMIT_SAFETY` | `0.9` | Safety margin applied to the request limit |
| `UKVET_MAX_ITEMS` | `100` | Maximum items allowed by the relevant application logic |

## Common commands

Load settings in Python:

```python
from ukvet_mcp.config import load_settings

settings = load_settings()

timeout = settings.timeout_seconds
api_key = settings.api_key.get_secret_value()
```

Load settings without a `.env` file:

```python
settings = load_settings(env_file=None)
```

## Validation and security

- Pydantic validates configuration values when `Settings` is created.
- `SecretStr` masks the API key in common string representations.
- The API key validator removes surrounding whitespace and quotes and rejects empty keys or keys containing whitespace.
- Invalid settings raise a `ConfigError` with a helpful message.
- API keys should not be committed to version control or written to logs.

## Derived settings

- `effective_rate_limit` calculates the request limit after applying the safety margin.
- `cache_ttl_seconds` converts the configured cache lifetime from hours to seconds.

## Error handling

The `load_settings()` function catches Pydantic `ValidationError` exceptions and converts them into the project's `ConfigError`.

A missing API key produces instructions for obtaining and configuring a Companies House API key. Other invalid settings produce a message identifying the relevant configuration fields.

## Key files

- `ukvet_mcp/config.py` — settings, defaults, validation, and loading.
- `ukvet_mcp/errors.py` — custom configuration error definitions.
- `.env` — optional local configuration file; should not be committed if it contains secrets.
- `.env.example` — recommended template documenting the environment variables required for local development.

## Run the module itself
Add a block at the bottom of `cofig.py`:
```python
if __name__ == "__main__":
    s = load_settings()
    print(s)
    print("rate limit:", s.effective_rate_limit)
```
Then run it as a module:
```bash
uv run python -m ukvet_mcp.config
```