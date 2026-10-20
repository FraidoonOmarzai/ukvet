"""Pure helpers that turn an API report into display text (no Streamlit imports)."""

from typing import Any

CH_COMPANY_URL = "https://find-and-update.company-information.service.gov.uk/company/{number}"

RISK_LABELS = {
    "low": ("🟢", "LOW risk"),
    "medium": ("🟠", "MEDIUM risk"),
    "high": ("🔴", "HIGH risk"),
    "insufficient_data": ("⚪", "INSUFFICIENT DATA"),
}
SEVERITY_ICONS = {"high": "🔴", "medium": "🟠", "low": "🟡", "info": "🔵"}


def company_url(number: str) -> str:
    return CH_COMPANY_URL.format(number=number)


def risk_label(level: str) -> str:
    icon, text = RISK_LABELS.get(level, ("⚪", level.upper()))
    return f"{icon} {text}"


def severity_icon(severity: str) -> str:
    return SEVERITY_ICONS.get(severity, "•")


def cite(fact_ids: list[str]) -> str:
    """'[Q4.accounts, Q6.charges]' appended to a claim; empty if it cites nothing."""
    return f"[{', '.join(fact_ids)}]" if fact_ids else ""


def claim_markdown(claim: dict[str, Any]) -> str:
    text = str(claim.get("text", "")).replace("$", r"\$")
    ref = cite(list(claim.get("fact_ids", [])))
    return f"{text} `{ref}`" if ref else text


def narrative_note(report: dict[str, Any]) -> str:
    """Be explicit about how the wording was produced."""
    stats = report.get("citation_stats", {})
    if report.get("narrative_source") == "llm":
        dropped = stats.get("claims_dropped", 0)
        extra = f"; {dropped} unsupported statement(s) removed" if dropped else ""
        return (
            f"Wording written by an AI model ({report.get('model')}) and checked against the "
            f"records{extra}."
        )
    return (
        "Wording generated from templates (no AI model used). Every statement is a recorded fact."
    )


def fact_sources(fact: dict[str, Any]) -> list[tuple[str, str]]:
    """(endpoint, url) pairs, de-duplicated, for display under each fact."""
    seen: dict[str, str] = {}
    for src in fact.get("sources", []):
        seen.setdefault(str(src.get("url")), str(src.get("endpoint")))
    return [(endpoint, url) for url, endpoint in seen.items()]


def candidate_label(candidate: dict[str, Any]) -> str:
    bits = [str(candidate.get("name", "")), f"#{candidate.get('company_number')}"]
    if candidate.get("status"):
        bits.append(str(candidate["status"]))
    if candidate.get("date_of_creation"):
        bits.append(f"inc. {candidate['date_of_creation']}")
    return " · ".join(bits)
