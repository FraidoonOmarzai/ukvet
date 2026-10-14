"""The real `python -m ukvet_mcp` process: stdout hygiene, fail-fast config, --check, handshake."""

import os
import subprocess
import sys
from pathlib import Path

import httpx
import pytest
import respx
from conftest import EXPECTED_TOOLS
from mcp.client import Client
from mcp.client.stdio import StdioServerParameters
from ukvet_mcp import __version__
from ukvet_mcp.__main__ import main


def clean_env(**extra: str) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("CH_", "UKVET_"))}
    env.update(extra)
    return env


def test_missing_key_fails_fast_on_stderr_with_exit_code_2(tmp_path: Path) -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "ukvet_mcp"],
        capture_output=True,
        text=True,
        cwd=tmp_path,  # no .env here
        env=clean_env(),
        timeout=30,
        check=False,
    )
    assert proc.returncode == 2
    assert "CH_API_KEY" in proc.stderr
    assert proc.stdout == ""  # stdout is reserved for the MCP protocol
    assert "Traceback" not in proc.stderr


def test_version_flag() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "ukvet_mcp", "--version"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert proc.returncode == 0
    assert proc.stdout.strip() == f"ukvet-mcp {__version__}"


async def test_real_stdio_handshake_lists_tools(tmp_path: Path) -> None:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "ukvet_mcp"],
        cwd=tmp_path,
        env=clean_env(CH_API_KEY="test-key", UKVET_CACHE_ENABLED="false"),
    )
    async with Client(params) as c:
        tools = await c.list_tools()
    assert {t.name for t in tools.tools} == EXPECTED_TOOLS


def test_check_succeeds_with_valid_key(
    monkeypatch: pytest.MonkeyPatch,
    router: respx.MockRouter,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CH_API_KEY", "test-key")
    monkeypatch.setenv("UKVET_CACHE_ENABLED", "false")
    router.get("/search/companies").mock(
        return_value=httpx.Response(
            200,
            json={
                "total_results": 1,
                "items": [{"title": "TESCO PLC", "company_number": "00445790"}],
            },
        )
    )
    assert main(["--check"]) == 0
    captured = capsys.readouterr()
    assert "OK" in captured.err
    assert captured.out == ""


def test_check_reports_bad_key_without_traceback(
    monkeypatch: pytest.MonkeyPatch,
    router: respx.MockRouter,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CH_API_KEY", "wrong-key")
    monkeypatch.setenv("UKVET_CACHE_ENABLED", "false")
    router.get("/search/companies").respond(401)
    assert main(["--check"]) == 1
    err = capsys.readouterr().err
    assert "rejected the API key" in err
    assert "wrong-key" not in err
    assert "Traceback" not in err


def test_check_without_key_returns_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    for name in list(os.environ):
        if name.startswith(("CH_", "UKVET_")):
            monkeypatch.delenv(name)
    assert main(["--check"]) == 2
    assert "CH_API_KEY" in capsys.readouterr().err
