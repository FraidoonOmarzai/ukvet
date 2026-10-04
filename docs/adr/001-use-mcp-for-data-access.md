# ADR-001: Use MCP for data access

- **Status:** Accepted
- **Date:** 04 Oct 2026

## Context
The agent needs Companies House data. We could call the API directly from agent tools, or put it behind a Model Context Protocol (MCP) server.

## Decision
Expose Companies House data through a standalone MCP server (`ukvet-mcp`), and have the agent consume it as an MCP client.

## Alternatives considered
| Option | Why not |
|---|---|
| Direct Python tools inside the agent | Not reusable by other AI apps; mixes data access with reasoning |
| Use an existing Companies House MCP server | Less control over "no data" handling, caching and fact/source tagging needed for citations; building it is part of the portfolio value |

## Consequences
- The data layer is reusable in Claude Desktop, Cursor and other MCP clients → a second, independently useful deliverable.
- Clean separation: data correctness can be tested without any LLM.
- Extra moving part (MCP transport) to run and test.
