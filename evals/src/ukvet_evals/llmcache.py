"""Record/replay cache for LLM calls, so CI can re-score LLM output without calling an LLM.

Key = sha256(model + system prompt + user prompt). Any change to the facts, the prompt or the model
changes the key, which is exactly when a recorded answer stops being valid. In `replay` mode a miss
is NOT silently turned into a template report: the writer records it and the runner fails with
"re-record needed".
"""

import hashlib
import json
import re
from pathlib import Path
from typing import Literal

from ukvet_agent.llm import NarrativeDraft, NarrativeWriter

CacheMode = Literal["replay", "record"]


class CacheMiss(Exception):
    """A recorded LLM answer is missing for this exact prompt."""


def cache_key(model: str, system: str, user: str) -> str:
    return hashlib.sha256(f"{model}\n--\n{system}\n--\n{user}".encode()).hexdigest()


def safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name)


class JsonCache:
    def __init__(self, root: Path, namespace: str) -> None:
        self.dir = root / safe(namespace)

    def path(self, key: str) -> Path:
        return self.dir / f"{key}.json"

    def get(self, key: str) -> dict[str, object] | None:
        p = self.path(key)
        if not p.exists():
            return None
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None

    def put(self, key: str, value: dict[str, object]) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path(key).write_text(
            json.dumps(value, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
        )


class CachingWriter:
    """NarrativeWriter wrapper: replay recorded drafts, or record live ones."""

    def __init__(
        self, cache_root: Path, mode: CacheMode, model_name: str, inner: NarrativeWriter | None
    ) -> None:
        if mode == "record" and inner is None:
            raise ValueError(
                "record mode needs a real writer (set LLM_PROVIDER/LLM_MODEL/LLM_API_KEY)"
            )
        self.model_name = model_name
        self._cache = JsonCache(cache_root, model_name)
        self._mode = mode
        self._inner = inner
        self.misses: list[str] = []
        self.hits = 0
        self.live_calls = 0

    async def write(self, system: str, user: str) -> NarrativeDraft:
        key = cache_key(self.model_name, system, user)
        hit = self._cache.get(key)
        if hit is not None:
            self.hits += 1
            return NarrativeDraft.model_validate(hit["draft"])
        if self._mode == "replay" or self._inner is None:
            self.misses.append(key)
            raise CacheMiss(key)
        draft = await self._inner.write(system, user)
        self.live_calls += 1
        self._cache.put(key, {"model": self.model_name, "draft": draft.model_dump(mode="json")})
        return draft
