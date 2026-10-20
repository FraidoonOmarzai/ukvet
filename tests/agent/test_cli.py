import io
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from agent_helpers import make_deps, scripted_company
from ukvet_agent import cli
from ukvet_agent.graph import Deps
from ukvet_agent.mcp_client import McpToolClient
from ukvet_agent.settings import AgentSettings
from ukvet_mcp import server as mcp_module


@asynccontextmanager
async def mcp_factory() -> AsyncIterator[Deps]:
    async with McpToolClient(mcp_module.mcp, timeout_seconds=10) as tools:
        yield make_deps(tools, AgentSettings(_env_file=None))  # type: ignore[call-arg]


async def test_summary_lines_and_exit_code(mcp_installed: None) -> None:
    out = io.StringIO()
    code = await cli.check(["12345678", "99999999"], deps_factory=mcp_factory, out=out)
    lines = out.getvalue().splitlines()
    assert "ACME TEST LTD" in lines[0] and "medium" in lines[0] and "template" in lines[0]
    assert lines[1].startswith("99999999: ERROR CompanyNotFoundError")
    assert code == 1


async def test_full_output(mcp_installed: None) -> None:
    out = io.StringIO()
    code = await cli.check(["12345678"], full=True, deps_factory=mcp_factory, out=out)
    text = out.getvalue()
    assert code == 0 and "Red flag [medium]: Accounts are overdue" in text
    assert "Gap Q8" in text and "[Q4.accounts]" in text


async def test_json_output(mcp_installed: None) -> None:
    out = io.StringIO()
    await cli.check(["12345678"], as_json=True, deps_factory=mcp_factory, out=out)
    assert json.loads(out.getvalue())["company_number"] == "12345678"


async def test_ambiguous_name_lists_candidates(mcp_installed: None) -> None:
    out = io.StringIO()
    await cli.check(["acme"], deps_factory=mcp_factory, out=out)
    assert "12345678  ACME TEST LTD" in out.getvalue() and "11111111" in out.getvalue()


def test_main_exit_codes(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    @asynccontextmanager
    async def scripted() -> AsyncIterator[Deps]:
        yield make_deps(scripted_company(), AgentSettings(_env_file=None))  # type: ignore[call-arg]

    monkeypatch.setattr(cli, "default_deps", scripted)
    # default arg was bound at definition time, so patch check() to use our factory
    original = cli.check

    async def patched(companies: list[str], **kw: object) -> int:
        return await original(companies, deps_factory=scripted, **kw)  # type: ignore[arg-type]

    monkeypatch.setattr(cli, "check", patched)
    with pytest.raises(SystemExit) as exc:
        cli.main(["12345678"])
    assert exc.value.code == 0
    assert "SCRIPTED LTD" in capsys.readouterr().out


def test_main_reports_config_errors(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.delenv("LLM_MODEL", raising=False)
    with pytest.raises(SystemExit) as exc:
        cli.main(["12345678"])
    assert exc.value.code == 2
    assert "LLM_MODEL" in capsys.readouterr().err
