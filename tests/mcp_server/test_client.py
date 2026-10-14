import base64
import logging

import httpx
import pytest
import respx
from conftest import FakeClock, make_client
from ukvet_mcp.cache import ResponseCache
from ukvet_mcp.client import CompaniesHouseClient
from ukvet_mcp.config import Settings
from ukvet_mcp.errors import AuthError, InvalidInput, RateLimited, UpstreamError

PATH = "/company/12345678"


async def test_success_sends_basic_auth_with_key_as_username(
    ch_api: respx.MockRouter, client: CompaniesHouseClient
) -> None:
    resp = await client.get(PATH)
    assert resp.status == 200
    assert resp.data is not None
    assert resp.data["company_number"] == "12345678"
    assert resp.from_cache is False
    auth = ch_api.calls.last.request.headers["authorization"]
    assert base64.b64decode(auth.removeprefix("Basic ")) == b"test-key:"


@pytest.mark.parametrize("status", [401, 403])
async def test_auth_failures_raise_and_are_not_retried(
    router: respx.MockRouter, client: CompaniesHouseClient, status: int
) -> None:
    route = router.get(PATH).respond(status)
    with pytest.raises(AuthError) as err:
        await client.get(PATH)
    assert "CH_API_KEY" in str(err.value)
    assert route.call_count == 1


async def test_404_is_returned_not_raised_and_not_retried(
    router: respx.MockRouter, client: CompaniesHouseClient
) -> None:
    route = router.get(PATH).respond(404)
    resp = await client.get(PATH)
    assert (resp.status, resp.data) == (404, None)
    assert route.call_count == 1


async def test_400_raises_invalid_input_without_retry(
    router: respx.MockRouter, client: CompaniesHouseClient
) -> None:
    route = router.get(PATH).respond(400)
    with pytest.raises(InvalidInput):
        await client.get(PATH)
    assert route.call_count == 1


async def test_429_then_success_retries_with_backoff(
    router: respx.MockRouter, client: CompaniesHouseClient, clock: FakeClock
) -> None:
    route = router.get(PATH).mock(
        side_effect=[httpx.Response(429), httpx.Response(200, json={"ok": True})]
    )
    resp = await client.get(PATH)
    assert resp.data == {"ok": True}
    assert route.call_count == 2
    assert 0.5 in clock.sleeps  # first backoff: 0.5 * 2**0


async def test_429_three_times_raises_rate_limited(
    router: respx.MockRouter, client: CompaniesHouseClient
) -> None:
    route = router.get(PATH).respond(429)
    with pytest.raises(RateLimited):
        await client.get(PATH)
    assert route.call_count == 3


async def test_retry_after_header_is_honoured(
    router: respx.MockRouter, client: CompaniesHouseClient, clock: FakeClock
) -> None:
    router.get(PATH).mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "2"}),
            httpx.Response(200, json={}),
        ]
    )
    await client.get(PATH)
    assert 2.0 in clock.sleeps


async def test_500_is_retried_then_succeeds(
    router: respx.MockRouter, client: CompaniesHouseClient
) -> None:
    route = router.get(PATH).mock(
        side_effect=[httpx.Response(500), httpx.Response(502), httpx.Response(200, json={"a": 1})]
    )
    resp = await client.get(PATH)
    assert resp.data == {"a": 1}
    assert route.call_count == 3


async def test_persistent_503_raises_upstream_error(
    router: respx.MockRouter, client: CompaniesHouseClient
) -> None:
    route = router.get(PATH).respond(503)
    with pytest.raises(UpstreamError):
        await client.get(PATH)
    assert route.call_count == 3


async def test_timeout_is_retried_then_succeeds(
    router: respx.MockRouter, client: CompaniesHouseClient
) -> None:
    route = router.get(PATH).mock(
        side_effect=[httpx.ReadTimeout("slow"), httpx.Response(200, json={"a": 1})]
    )
    assert (await client.get(PATH)).data == {"a": 1}
    assert route.call_count == 2


async def test_persistent_timeout_raises_upstream_error(
    router: respx.MockRouter, client: CompaniesHouseClient
) -> None:
    route = router.get(PATH).mock(side_effect=httpx.ConnectTimeout("down"))
    with pytest.raises(UpstreamError) as err:
        await client.get(PATH)
    assert route.call_count == 3
    assert "network error or timeout" in str(err.value)


async def test_non_json_200_raises_upstream_error(
    router: respx.MockRouter, client: CompaniesHouseClient
) -> None:
    router.get(PATH).mock(return_value=httpx.Response(200, text="<html>oops</html>"))
    with pytest.raises(UpstreamError):
        await client.get(PATH)


async def test_unexpected_status_raises_upstream_error_without_retry(
    router: respx.MockRouter, client: CompaniesHouseClient
) -> None:
    route = router.get(PATH).respond(418)
    with pytest.raises(UpstreamError):
        await client.get(PATH)
    assert route.call_count == 1


async def test_low_ratelimit_header_makes_next_request_wait(
    router: respx.MockRouter, client: CompaniesHouseClient, clock: FakeClock
) -> None:
    headers = {"X-Ratelimit-Remain": "1", "X-Ratelimit-Reset": str(clock.now() + 60)}
    router.get(PATH).mock(return_value=httpx.Response(200, json={}, headers=headers))
    router.get("/other").mock(return_value=httpx.Response(200, json={}))
    await client.get(PATH)
    start = clock.now()
    await client.get("/other")
    assert clock.now() - start == pytest.approx(60, abs=1)


# ---- caching ------------------------------------------------------------------------------------


def cached_client(settings: Settings, clock: FakeClock) -> CompaniesHouseClient:
    return make_client(settings, clock, cache=ResponseCache(":memory:", 3600, clock=clock.now))


async def test_cache_hit_avoids_second_http_call(
    router: respx.MockRouter, settings: Settings, clock: FakeClock
) -> None:
    route = router.get(PATH).mock(return_value=httpx.Response(200, json={"a": 1}))
    c = cached_client(settings, clock)
    first = await c.get(PATH)
    second = await c.get(PATH)
    assert route.call_count == 1
    assert (first.from_cache, second.from_cache) == (False, True)
    assert second.data == {"a": 1}
    assert second.retrieved_at == first.retrieved_at  # cached data keeps its ORIGINAL timestamp


async def test_404_no_data_is_cached(
    router: respx.MockRouter, settings: Settings, clock: FakeClock
) -> None:
    route = router.get(PATH).respond(404)
    c = cached_client(settings, clock)
    await c.get(PATH)
    again = await c.get(PATH)
    assert route.call_count == 1
    assert (again.status, again.from_cache) == (404, True)


async def test_errors_are_not_cached(
    router: respx.MockRouter, settings: Settings, clock: FakeClock
) -> None:
    route = router.get(PATH).mock(
        side_effect=[httpx.Response(503)] * 3 + [httpx.Response(200, json={"a": 1})]
    )
    c = cached_client(settings, clock)
    with pytest.raises(UpstreamError):
        await c.get(PATH)
    assert (await c.get(PATH)).data == {"a": 1}
    assert route.call_count == 4


# ---- pagination -----------------------------


def paged(total: int, key: str = "total_results") -> httpx.Response | object:
    def handler(request: httpx.Request) -> httpx.Response:
        start = int(request.url.params["start_index"])
        per = int(request.url.params["items_per_page"])
        items = [{"n": i} for i in range(start, min(start + per, total))]
        return httpx.Response(200, json={"items": items, key: total})

    return handler


async def test_pagination_reads_all_pages(
    router: respx.MockRouter, client: CompaniesHouseClient
) -> None:
    route = router.get(PATH).mock(side_effect=paged(250))
    page = await client.get_paginated(
        PATH, items_key="items", total_key="total_results", max_items=500
    )
    assert len(page.items) == 250
    assert page.total == 250
    assert page.truncated is False
    assert route.call_count == 3
    starts = [int(c.request.url.params["start_index"]) for c in route.calls]
    assert starts == [0, 100, 200]


async def test_pagination_cap_limits_calls_and_flags_truncation(
    router: respx.MockRouter, client: CompaniesHouseClient
) -> None:
    route = router.get(PATH).mock(side_effect=paged(1000))
    page = await client.get_paginated(
        PATH, items_key="items", total_key="total_results", max_items=150
    )
    assert len(page.items) == 150
    assert page.total == 1000
    assert page.truncated is True
    assert route.call_count == 2  # never fetches the other 800 items


async def test_pagination_small_cap_requests_small_pages(
    router: respx.MockRouter, client: CompaniesHouseClient
) -> None:
    route = router.get(PATH).mock(side_effect=paged(1000))
    page = await client.get_paginated(
        PATH, items_key="items", total_key="total_results", max_items=10
    )
    assert len(page.items) == 10
    assert route.calls.last.request.url.params["items_per_page"] == "10"


async def test_pagination_stop_predicate(
    router: respx.MockRouter, client: CompaniesHouseClient
) -> None:
    route = router.get(PATH).mock(side_effect=paged(1000))
    page = await client.get_paginated(
        PATH,
        items_key="items",
        total_key="total_results",
        max_items=500,
        stop_after=lambda items: items[-1]["n"] >= 100,  # true after the 2nd page
    )
    assert route.call_count == 2
    assert page.stopped_by_predicate is True


async def test_pagination_first_page_404(
    router: respx.MockRouter, client: CompaniesHouseClient
) -> None:
    router.get(PATH).respond(404)
    page = await client.get_paginated(
        PATH, items_key="items", total_key="total_count", max_items=50
    )
    assert page.not_found is True
    assert page.items == []


async def test_pagination_without_total_stops_on_short_page(
    router: respx.MockRouter, client: CompaniesHouseClient
) -> None:
    router.get(PATH).mock(return_value=httpx.Response(200, json={"items": [{"n": 1}, {"n": 2}]}))
    page = await client.get_paginated(
        PATH, items_key="items", total_key="total_count", max_items=50
    )
    assert len(page.items) == 2
    assert page.total is None
    assert page.truncated is False


# ---- secrets ----------------------------------------


async def test_api_key_never_appears_in_logs_or_errors(
    router: respx.MockRouter, client: CompaniesHouseClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    router.get("/ok").mock(return_value=httpx.Response(200, json={}))
    router.get("/bad").respond(401)
    router.get("/slow").mock(side_effect=httpx.ReadTimeout("x"))
    await client.get("/ok")
    with pytest.raises(AuthError) as auth_err:
        await client.get("/bad")
    with pytest.raises(UpstreamError) as up_err:
        await client.get("/slow")
    everything = caplog.text + str(auth_err.value) + str(up_err.value)
    assert "test-key" not in everything
    assert base64.b64encode(b"test-key:").decode() not in everything


def test_client_start_up_purges_expired_cache_rows(
    settings: Settings, clock: FakeClock, tmp_path
) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "c.sqlite"
    old = ResponseCache(path, 100, clock=clock.now)
    old.set("stale", 200, {"name": "someone"})
    old.close()
    clock.t += 500  # now long expired
    make_client(settings, clock, cache=ResponseCache(path, 100, clock=clock.now))
    check = ResponseCache(path, 10_000, clock=clock.now)  # long TTL: only a purge could remove it
    assert check.get("stale") is None
