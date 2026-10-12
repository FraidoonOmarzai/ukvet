"""SQLite response cache with a TTL (ADR-004).

- Caches successful (200) and valid "no data" (404) responses. Errors are NEVER cached.
- Short-lived by design: director names are personal data (docs/06-legal-and-ethics.md).
- Can be disabled; when disabled, no file is created.
- Synchronous on purpose: local SQLite calls take well under a millisecond.
"""

import contextlib
import json
import sqlite3
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

CACHEABLE_STATUSES = frozenset({200, 404})


def make_key(path: str, params: Mapping[str, Any] | None = None) -> str:
    query = urlencode(sorted((str(k), str(v)) for k, v in (params or {}).items()))
    return f"{path}?{query}" if query else path


@dataclass(frozen=True)
class CachedResponse:
    status: int
    body: dict[str, Any] | None
    stored_at: float  # unix time the data was fetched from Companies House


class ResponseCache:
    def __init__(
        self,
        path: Path | str,
        ttl_seconds: float,
        *,
        enabled: bool = True,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._path = str(path)
        self._ttl = ttl_seconds
        self.enabled = enabled
        self._clock = clock
        self._lock = threading.Lock()
        self._conn: sqlite3.Connection | None = None

    def _connect(self) -> sqlite3.Connection:
        if self._conn is None:
            if self._path != ":memory:":
                file = Path(self._path)
                file.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(self._path, check_same_thread=False)
            conn.execute(
                "CREATE TABLE IF NOT EXISTS cache ("
                "key TEXT PRIMARY KEY, status INTEGER NOT NULL, body TEXT, stored_at REAL NOT NULL)"
            )
            conn.commit()
            if self._path != ":memory:":
                with contextlib.suppress(OSError):  # e.g. Windows
                    Path(self._path).chmod(0o600)
            self._conn = conn
        return self._conn

    def get(self, key: str) -> CachedResponse | None:
        if not self.enabled:
            return None
        with self._lock:
            conn = self._connect()
            row = conn.execute(
                "SELECT status, body, stored_at FROM cache WHERE key = ?", (key,)
            ).fetchone()
            if row is None:
                return None
            status, body, stored_at = row
            if self._clock() - stored_at >= self._ttl:
                conn.execute("DELETE FROM cache WHERE key = ?", (key,))
                conn.commit()
                return None
            return CachedResponse(status, json.loads(body) if body else None, stored_at)

    def set(self, key: str, status: int, body: dict[str, Any] | None) -> None:
        if status not in CACHEABLE_STATUSES:
            raise ValueError(
                f"HTTP {status} must not be cached (errors are never cached)"
            )
        if not self.enabled:
            return
        with self._lock:
            conn = self._connect()
            conn.execute(
                "INSERT OR REPLACE INTO cache (key, status, body, stored_at) VALUES (?, ?, ?, ?)",
                (
                    key,
                    status,
                    json.dumps(body) if body is not None else None,
                    self._clock(),
                ),
            )
            conn.commit()

    def purge_expired(self) -> int:
        """Delete expired rows (call at start-up so old personal data doesn't linger)."""
        if not self.enabled:
            return 0
        with self._lock:
            conn = self._connect()
            cur = conn.execute(
                "DELETE FROM cache WHERE ? - stored_at >= ?", (self._clock(), self._ttl)
            )
            conn.commit()
            return cur.rowcount

    def clear(self) -> None:
        if not self.enabled:
            return
        with self._lock:
            conn = self._connect()
            conn.execute("DELETE FROM cache")
            conn.commit()

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None
