"""Entry point: `ukvet-mcp` (stdio MCP server), `ukvet-mcp --check`, `ukvet-mcp --version`.

IMPORTANT: a stdio MCP server must never write anything but protocol messages to stdout.
All human-readable output (errors, logs) goes to stderr.
"""

import argparse
import asyncio
import logging
import os
import sys

from ukvet_mcp import __version__
from ukvet_mcp.config import load_settings
from ukvet_mcp.errors import ConfigError, UkvetError


def _configure_logging() -> None:
    level = os.environ.get("UKVET_LOG_LEVEL", "WARNING").upper()
    logging.basicConfig(
        stream=sys.stderr,
        level=getattr(logging, level, logging.WARNING),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


async def _check() -> int:
    from ukvet_mcp.server import build_service

    settings = load_settings()
    service = build_service(settings)
    try:
        result = await service.search_company("tesco", limit=1)
    finally:
        await service.aclose()
    print(
        f"OK: authenticated with Companies House (search returned {result.data.returned} result).",
        file=sys.stderr,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ukvet-mcp", description="MCP server for UK Companies House data."
    )
    parser.add_argument("--version", action="version", version=f"ukvet-mcp {__version__}")
    parser.add_argument("--check", action="store_true", help="verify the API key works, then exit")
    args = parser.parse_args(argv)
    _configure_logging()

    try:
        if args.check:
            return asyncio.run(_check())
        settings = load_settings()
    except (ConfigError, UkvetError) as err:
        print(f"ukvet-mcp: {err}", file=sys.stderr)
        return 2 if isinstance(err, ConfigError) else 1

    from ukvet_mcp.server import build_service, mcp, set_service

    set_service(build_service(settings))
    mcp.run(transport="stdio")
    return 0


if __name__ == "__main__":
    sys.exit(main())
