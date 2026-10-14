import os
import sys
from pathlib import Path

import pytest
from conftest import FakeClock
from ukvet_mcp.cache import ResponseCache, make_key


def make(clock: FakeClock, ttl: float = 100.0, enabled: bool = True) -> ResponseCache:
    return ResponseCache(":memory:", ttl, enabled=enabled, clock=clock.now)


def test_key_is_stable_regardless_of_param_order() -> None:
    assert make_key("/x", {"b": 2, "a": 1}) == make_key("/x", {"a": 1, "b": 2})
    assert make_key("/x") == "/x"
    assert make_key("/x", {"a": 1}) != make_key("/x", {"a": 2})


def test_miss_then_hit(clock: FakeClock) -> None:
    cache = make(clock)
    assert cache.get("k") is None
    cache.set("k", 200, {"a": 1})
    hit = cache.get("k")
    assert hit is not None
    assert (hit.status, hit.body, hit.stored_at) == (200, {"a": 1}, clock.now())


def test_valid_no_data_404_is_cached(clock: FakeClock) -> None:
    cache = make(clock)
    cache.set("k", 404, None)
    hit = cache.get("k")
    assert hit is not None
    assert hit.status == 404
    assert hit.body is None


@pytest.mark.parametrize("status", [400, 401, 429, 500, 503])
def test_errors_are_never_cached(clock: FakeClock, status: int) -> None:
    cache = make(clock)
    with pytest.raises(ValueError, match="never be cached|must not be cached"):
        cache.set("k", status, None)
    assert cache.get("k") is None


def test_entries_expire_after_ttl(clock: FakeClock) -> None:
    cache = make(clock, ttl=100)
    cache.set("k", 200, {"a": 1})
    clock.t += 99
    assert cache.get("k") is not None
    clock.t += 1
    assert cache.get("k") is None


def test_purge_expired_removes_only_old_rows(clock: FakeClock) -> None:
    cache = make(clock, ttl=100)
    cache.set("old", 200, {})
    clock.t += 150
    cache.set("new", 200, {})
    assert cache.purge_expired() == 1
    assert cache.get("old") is None
    assert cache.get("new") is not None


def test_disabled_cache_stores_nothing_and_creates_no_file(
    clock: FakeClock, tmp_path: Path
) -> None:
    path = tmp_path / "sub" / "c.sqlite"
    cache = ResponseCache(path, 100, enabled=False, clock=clock.now)
    cache.set("k", 200, {"a": 1})
    assert cache.get("k") is None
    assert cache.purge_expired() == 0
    assert not path.exists()


def test_persists_across_instances(clock: FakeClock, tmp_path: Path) -> None:
    path = tmp_path / "c.sqlite"
    first = ResponseCache(path, 100, clock=clock.now)
    first.set("k", 200, {"a": 1})
    first.close()
    second = ResponseCache(path, 100, clock=clock.now)
    hit = second.get("k")
    assert hit is not None
    assert hit.body == {"a": 1}


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions")
def test_cache_file_is_private(clock: FakeClock, tmp_path: Path) -> None:
    path = tmp_path / "c.sqlite"
    ResponseCache(path, 100, clock=clock.now).set("k", 200, {})
    assert (os.stat(path).st_mode & 0o777) == 0o600


def test_clear(clock: FakeClock) -> None:
    cache = make(clock)
    cache.set("k", 200, {})
    cache.clear()
    assert cache.get("k") is None
