# Companies House fixtures

Used by the offline tests (`tests/mcp_server/`). CI never needs an API key or network access.

Every file looks like:
```json
{"_meta": {...}, "request": {"path": "/company/12345678"}, "status": 200, "body": {...}}
```

**Files marked `"synthetic": true` are hand-written** to match the documented response shape: fake
companies ("ACME TEST LTD", "GONE TEST LTD") and fake people ("DIRECTOR A"). They intentionally
include personal-data fields (date of birth, address, nationality) so tests can prove the mappers
drop them.

Real recordings: run `uv run python scripts/record_fixtures.py` (needs `CH_API_KEY`). The script
anonymises people and (except allow-listed large public companies) company identities before
saving. Never commit anything from `data/raw/`.
