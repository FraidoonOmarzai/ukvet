"""Packaging sanity: both packages import and the code version matches the package metadata."""

from importlib.metadata import version

import ukvet_agent
import ukvet_mcp


def test_packages_import() -> None:
    assert ukvet_mcp.__version__
    assert ukvet_agent.__version__


def test_code_version_matches_package_metadata() -> None:
    assert version("ukvet-mcp") == ukvet_mcp.__version__
