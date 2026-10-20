"""Helpers shared by agent tests (importable as `agent_helpers`)."""

from datetime import UTC, datetime
from typing import Any

from ukvet_agent.graph import Deps
from ukvet_agent.llm import NarrativeDraft
from ukvet_agent.mcp_client import ToolOutcome
from ukvet_agent.schemas import Claim
from ukvet_agent.settings import AgentSettings

NOW = datetime(2026, 3, 4, 12, 0, tzinfo=UTC)


class FakeWriter:
    """Scripted narrative writer. Each call pops the next response (draft or exception)."""

    model_name = "fake-model"

    def __init__(self, *responses: NarrativeDraft | Exception) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, str]] = []

    async def write(self, system: str, user: str) -> NarrativeDraft:
        self.calls.append((system, user))
        item = self.responses.pop(0) if self.responses else self.responses_default()
        if isinstance(item, Exception):
            raise item
        return item

    @staticmethod
    def responses_default() -> NarrativeDraft:
        return NarrativeDraft(headline=Claim(text="", fact_ids=[]))


def draft(headline: tuple[str, list[str]], *findings: tuple[str, list[str]]) -> NarrativeDraft:
    return NarrativeDraft(
        headline=Claim(text=headline[0], fact_ids=headline[1]),
        findings=[Claim(text=t, fact_ids=ids) for t, ids in findings],
    )


class ScriptedTools:
    """ToolClient that returns canned outcomes by tool name (for unit tests without MCP)."""

    def __init__(self, outcomes: dict[str, ToolOutcome | list[ToolOutcome]]) -> None:
        self.outcomes = {k: (list(v) if isinstance(v, list) else [v]) for k, v in outcomes.items()}
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def call(self, name: str, arguments: dict[str, Any]) -> ToolOutcome:
        self.calls.append((name, arguments))
        queue = self.outcomes.get(name)
        if not queue:
            return ToolOutcome(ok=False, error=f"{name} not scripted")
        return queue.pop(0) if len(queue) > 1 else queue[0]

    async def ping(self) -> int:
        return 8


def make_deps(tools: Any, settings: AgentSettings, writer: Any = None) -> Deps:
    return Deps(tools=tools, settings=settings, writer=writer, clock=lambda: NOW)


def make_fact(fact_id: str, statement: str, **value: Any) -> Any:
    """A Fact whose checkable dates/numbers are derived from its statement, like the real ones."""
    from ukvet_agent.schemas import Fact
    from ukvet_agent.text import fact_tokens

    tokens = fact_tokens(statement)
    return Fact(
        id=fact_id,
        question_id=fact_id.split(".")[0],
        statement=statement,
        value=value,
        dates=sorted(tokens.dates),
        numbers=sorted(tokens.numbers),
    )


SRC = {"endpoint": "e", "url": "https://x/y", "retrieved_at": "2026-03-04T00:00:00Z"}


def ok(data: dict[str, Any], found: bool = True) -> ToolOutcome:
    return ToolOutcome(ok=True, found=found, data=data, source=SRC)


def fail(msg: str = "boom", retryable: bool = False) -> ToolOutcome:
    return ToolOutcome(ok=False, error=msg, retryable=retryable)


def scripted_company(**overrides: ToolOutcome | list[ToolOutcome]) -> ScriptedTools:
    """A healthy one-director company served from canned outcomes (no MCP, no HTTP)."""
    profile = {
        "company_number": "12345678",
        "company_name": "SCRIPTED LTD",
        "status": "active",
        "date_of_creation": "2015-01-01",
        "date_of_cessation": None,
        "age_days": 4000,
        "age_years": 11.0,
        "accounts": {"next_due": "2026-12-31", "overdue": False, "last_made_up_to": "2025-03-31"},
        "confirmation_statement": {
            "next_due": "2026-09-01",
            "overdue": False,
            "last_made_up_to": "2025-08-18",
        },
    }
    director = {
        "name": "DIR ONE",
        "officer_id": "ID1",
        "role": "director",
        "appointed_on": "2015-01-01",
        "resigned_on": None,
        "is_active": True,
    }
    outcomes: dict[str, ToolOutcome | list[ToolOutcome]] = {
        "get_company_profile": ok(profile),
        "get_officers": ok({"items": [director]}),
        "get_persons_with_significant_control": ok(
            {"items": [{"name": "OWNER", "is_corporate": False, "natures_of_control": []}]}
        ),
        "get_charges": ok({"outstanding_count": 0}, found=False),
        "get_insolvency": ok({}, found=False),
        "get_filing_history": ok({"items": []}),
        "get_officer_appointments": ok({"items": []}),
    }
    outcomes.update(overrides)
    return ScriptedTools(outcomes)
