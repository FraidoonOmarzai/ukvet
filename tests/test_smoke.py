"""Smoke tests: packages install and import. Replaced by real tests from Phase 1."""

import ukvet_agent
import ukvet_mcp
from ukvet_mcp.__main__ import main


def test_packages_import() -> None:
    assert ukvet_mcp.__version__
    assert ukvet_agent.__version__


def test_mcp_entrypoint_runs(capsys) -> None:  # type: ignore[no-untyped-def]
    main()
    assert "ukvet-mcp" in capsys.readouterr().out
