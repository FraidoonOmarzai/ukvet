"""Typed errors.

Every message is written to be read by an LLM *and* a human: say what happened and what to do
next. Messages never contain the API key, raw response bodies or stack traces.

Note: "no data" (e.g. a company with no charges) is NOT an error. It is a valid, empty result.
"""


class UkvetError(Exception):
    """Base class for all expected errors. `str(err)` is safe to show to a model or a user."""


class ConfigError(UkvetError):
    """Configuration is missing or invalid (raised at start-up, never from a tool call)."""


class InvalidInput(UkvetError):
    """The caller supplied something malformed, e.g. a bad company number."""


class AuthError(UkvetError):
    """Companies House rejected the API key (HTTP 401/403)."""

    def __init__(self, status: int) -> None:
        super().__init__(
            f"Companies House rejected the API key (HTTP {status}). Check that CH_API_KEY is a "
            "REST key for the LIVE environment, has no extra spaces, and has finished activating."
        )
        self.status = status


class CompanyNotFound(UkvetError):
    """No company exists with that number."""

    def __init__(self, company_number: str) -> None:
        super().__init__(
            f"Company {company_number} was not found at Companies House. Check the number, or "
            "use search_company to find the company by name."
        )
        self.company_number = company_number


class OfficerNotFound(UkvetError):
    """No officer exists with that ID."""

    def __init__(self, officer_id: str) -> None:
        super().__init__(
            f"Officer {officer_id} was not found. Officer IDs come from the officer_id field "
            "returned by get_officers; do not guess them."
        )
        self.officer_id = officer_id


class RateLimited(UkvetError):
    """Companies House kept returning HTTP 429 after all retries."""

    def __init__(self) -> None:
        super().__init__(
            "Companies House rate limit reached (600 requests per 5 minutes) and retries were "
            "exhausted. Wait a minute and try again."
        )


class UpstreamError(UkvetError):
    """Companies House returned a server error, timed out, or sent an unexpected response."""
