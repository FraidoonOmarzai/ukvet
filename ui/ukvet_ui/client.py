"""Thin HTTP client for the ukvet API. Turns every failure into a readable `ApiError`."""

from typing import Any

import httpx

DEFAULT_TIMEOUT = 60.0  # the API enforces its own 45 s deadline; leave headroom


class ApiError(Exception):
    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


_FALLBACK = {
    404: "No company was found.",
    422: "That input is not valid. Enter a company name or an 8-character company number.",
    503: "A data source is temporarily unavailable. Please try again in a moment.",
    504: "The report took too long to generate. Please try again.",
}


def request_report(
    api_url: str,
    company: str,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    http: httpx.Client | None = None,
) -> dict[str, Any]:
    """POST /v1/reports. Returns the JSON body (a report or a needs_selection answer)."""
    own = http is None
    client = http or httpx.Client(timeout=timeout)
    try:
        response = client.post(f"{api_url.rstrip('/')}/v1/reports", json={"company": company})
    except httpx.TimeoutException:
        raise ApiError("The request timed out. Please try again.") from None
    except httpx.HTTPError:
        raise ApiError(f"Cannot reach the ukvet API at {api_url}. Is it running?") from None
    finally:
        if own:
            client.close()

    if response.status_code == 200:
        body: dict[str, Any] = response.json()
        return body
    message = ""
    try:
        detail = response.json()
        message = str(detail.get("message") or "") if isinstance(detail, dict) else ""
        if response.status_code == 422 and not message:
            message = _FALLBACK[422]
    except ValueError:
        pass
    raise ApiError(
        message or _FALLBACK.get(response.status_code, "Something went wrong."),
        response.status_code,
    )
