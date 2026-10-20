"""Agent-level errors, each mapped to an HTTP status by the API layer."""


class AgentError(Exception):
    http_status = 500


class InvalidRequest(AgentError):
    http_status = 422


class CompanyNotFoundError(AgentError):
    http_status = 404


class UpstreamUnavailable(AgentError):
    http_status = 503


class ReportTimeout(AgentError):
    http_status = 504


class AgentConfigError(Exception):
    """Start-up configuration problem (e.g. missing LLM model)."""
