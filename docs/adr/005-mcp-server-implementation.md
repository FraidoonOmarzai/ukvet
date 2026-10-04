# ADR-005: MCP server implementation

- **Status:** Accepted
- **Date:** 04 Oct 2026

## Context
We need to implement the MCP server in a way that is standard, easy to install, and testable.

## Decision
- Python, using the **official MCP Python SDK** (FastMCP-style decorators).
- **stdio** transport first (works with Claude Desktop and Cursor); HTTP transport later if needed.
- HTTP client: `httpx` (async), with retries and backoff, and a token-bucket rate limiter.
- Tools return **structured results** that include the source endpoint, so every fact can be cited.
- Published to PyPI as `ukvet-mcp`, runnable with `uvx ukvet-mcp`.

## Alternatives considered
| Option | Why not |
|---|---|
| TypeScript SDK | Rest of the stack is Python; existing skills are Python |
| Build MCP protocol handling by hand | No benefit; error-prone |

## Consequences
- One language across the project.
- Must track MCP SDK version changes — pin versions.
