"""Planner: turn the user's input into a company number and a question plan.

Deterministic. A company number is used directly; a name is searched, and the planner either
selects an unambiguous match or asks the user to choose (never guesses between lookalikes).
"""

import re
from typing import Any

from ukvet_agent.errors import CompanyNotFoundError, InvalidRequest, UpstreamUnavailable
from ukvet_agent.mcp_client import ToolClient
from ukvet_agent.schemas import ALL_QUESTIONS, Candidate, NeedsSelection
from ukvet_agent.text import sanitise_registry_text

MAX_QUERY_CHARS = 200
MAX_CANDIDATES = 10
_NUMBER = re.compile(r"^([A-Z]{0,2})(\d{1,8})$")
_SUFFIXES = {"limited", "ltd", "plc", "llp", "lp", "cic", "cio"}


def looks_like_number(text: str) -> bool:
    return bool(_NUMBER.match(text.strip().upper().replace(" ", "")))


def canonical_number(text: str) -> str:
    """'1234567' -> '01234567', 'sc123456' -> 'SC123456' (total length 8)."""
    match = _NUMBER.match(text.strip().upper().replace(" ", ""))
    if not match:
        raise InvalidRequest(f"'{text}' is not a valid company number")
    prefix, digits = match.groups()
    return prefix + digits.zfill(8 - len(prefix))


def normalise_name(name: str) -> str:
    """Lower-case, '&' -> 'and', punctuation removed, trailing ltd/limited/plc dropped."""
    words = re.sub(r"[^a-z0-9 ]+", " ", name.lower().replace("&", " and ")).split()
    while words and words[-1] in _SUFFIXES:
        words.pop()
    return " ".join(words)


def _clean_request(raw: object) -> str:
    text = sanitise_registry_text(raw, MAX_QUERY_CHARS + 1)
    if not text:
        raise InvalidRequest("Enter a company name or number")
    if len(text) > MAX_QUERY_CHARS:
        raise InvalidRequest(f"Input is too long (max {MAX_QUERY_CHARS} characters)")
    return text


def _candidate(hit: dict[str, Any]) -> Candidate:
    return Candidate(
        company_number=str(hit["company_number"]),
        name=sanitise_registry_text(hit.get("name")),
        status=hit.get("status"),
        company_type=hit.get("company_type"),
        date_of_creation=hit.get("date_of_creation"),
        address_snippet=sanitise_registry_text(hit.get("address_snippet") or "") or None,
    )


async def plan_node(state: dict[str, Any], tools: ToolClient) -> dict[str, Any]:
    query = _clean_request(state.get("request"))

    if looks_like_number(query):
        return {
            "company_number": canonical_number(query),
            "company_name": None,
            "plan": ALL_QUESTIONS,
        }

    outcome = await tools.call("search_company", {"query": query, "limit": MAX_CANDIDATES})
    if not outcome.ok:
        raise UpstreamUnavailable(sanitise_registry_text(outcome.error or "Search failed", 300))
    hits = outcome.data.get("items", []) if outcome.found else []
    if not hits:
        raise CompanyNotFoundError(f"No company found matching '{query}'")

    chosen: dict[str, Any] | None = None
    if len(hits) == 1:
        chosen = hits[0]
    else:
        wanted = normalise_name(query)
        exact = [h for h in hits if normalise_name(str(h.get("name", ""))) == wanted]
        if len(exact) == 1:
            chosen = exact[0]

    if chosen is not None:
        return {
            "company_number": str(chosen["company_number"]),
            "company_name": sanitise_registry_text(chosen.get("name")),
            "plan": ALL_QUESTIONS,
        }

    selection = NeedsSelection(
        query=query,
        message=(
            f"{len(hits)} companies match '{query}'. Choose one by company number "
            "so the report covers the right company."
        ),
        candidates=[_candidate(h) for h in hits[:MAX_CANDIDATES]],
    )
    return {"result": selection}
