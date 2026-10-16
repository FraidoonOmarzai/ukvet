# Connecting `ukvet-mcp` to Claude Desktop on Windows

**Status: Claude Desktop connection is working.**

This guide records the steps used to test the local `ukvet-mcp` MCP server with MCP Inspector and connect it to Claude Desktop on Windows.

## Overview

`ukvet-mcp` exposes UK Companies House operations as MCP tools. The server uses **stdio** communication, so running it directly in a terminal may appear to do nothing: it is waiting for an MCP client to communicate with it.

Workflow:

1. Run the automated tests.
2. Connect to the server using MCP Inspector.
3. Manually test the tools.
4. Add the server to Claude Desktop's configuration.
5. Restart Claude Desktop and verify the integration.

## 1. Confirm tests pass

From the project root, run:

```powershell
uv run pytest
```

Recorded test result:

```text
168 passed, 1 skipped
Required test coverage of 80.0% reached. Total coverage: 92.95%
```

The suite also passed with Wi-Fi disabled during this test run, helping confirm that it did not require a live network connection in that environment.

## 2. Find the project and `uv` paths

Open PowerShell in the project root—the folder containing the workspace `pyproject.toml`—and run:

```powershell
(Get-Location).Path
(Get-Command uv).Source
```

The first command prints the project root. The second prints the full path to `uv.exe`. Keep both paths for the configuration.

## 3. Test with MCP Inspector

From the project root, run:

```powershell
npx @modelcontextprotocol/inspector uv run ukvet-mcp
```

Inspector should open in a browser. Use the connection toggle on the `uv` server card.

A successful connection means the server shows as connected and its tools are available. The eight tools are:

1. `search_company`
2. `get_company_profile`
3. `get_officers`
4. `get_officer_appointments`
5. `get_persons_with_significant_control`
6. `get_charges`
7. `get_insolvency`
8. `get_filing_history`

Test the tools with suitable inputs. For example, search for a real company, use its company number with `get_company_profile` and `get_officers`, then use an `officer_id` from the officers result with `get_officer_appointments`.

When using the Inspector command above, Inspector launches the server process for the test. Avoid starting a second copy unnecessarily.

## 4. Open Claude Desktop's configuration

On Windows:

1. Open Claude Desktop.
2. Go to **Settings → Developer → Edit Config**.
3. This opens `claude_desktop_config.json`.

Alternatively, press `Win + R` and enter:

```text
%APPDATA%\Claude
```

The configuration file is normally:

```text
%APPDATA%\Claude\claude_desktop_config.json
```

If the file already contains other MCP servers, preserve them and add the `ukvet` entry inside the existing `mcpServers` object. Do not create a duplicate `mcpServers` key.

## 5. Add the local server configuration

Use this JSON as a template:

```json
{
  "mcpServers": {
    "ukvet": {
      "command": "C:\\PATH\\TO\\uv.exe",
      "args": [
        "run",
        "--directory",
        "C:\\PATH\\TO\\YOUR\\ukvet-project",
        "ukvet-mcp"
      ],
      "env": {
        "CH_API_KEY": "YOUR_COMPANIES_HOUSE_API_KEY"
      }
    }
  }
}
```

Replace the placeholders with your actual values:

- `C:\\PATH\\TO\\uv.exe`: the full path printed by `(Get-Command uv).Source`.
- `C:\\PATH\\TO\\YOUR\\ukvet-project`: the project root printed by `(Get-Location).Path`.
- `YOUR_COMPANIES_HOUSE_API_KEY`: your Companies House API key.

JSON paths use doubled backslashes (`\\`). Use your actual paths, not the placeholders. If your project uses a different environment variable name, use the name defined in its configuration; this setup uses `CH_API_KEY`.

### Keep the API key secret

- Do not commit a config file containing the key to Git.
- Do not share screenshots or logs that reveal the key.
- Do not put the key in the `args` list.
- Keep the key in the `env` section.

If `mcpServers` already has entries, merge the `ukvet` object into it without removing the existing entries.

## 6. Save and restart Claude Desktop

1. Save `claude_desktop_config.json`.
2. Fully quit Claude Desktop. If it remains open in the Windows system tray, quit it there too.
3. Reopen Claude Desktop.
4. Check **Settings → Developer** for the server status or startup logs.

Claude Desktop launches the server as a separate process, so the executable path, project directory and environment need to be correct.

## 7. Verify the connection

Try this prompt in Claude Desktop:

> Search Companies House for a real UK company and tell me its company number and current status. Use the UKVET tools and do not guess if information is unavailable.

Then try:

- “Who are the current officers of this company?”
- “Does this company have any charges?”
- “Show me its recent filing history.”

Check that Claude calls the relevant tools and that the answers match the tool results. For important claims, compare them with the official Companies House website.

## Troubleshooting

### `uv run ukvet-mcp` appears to hang

This can be normal for a stdio MCP server: it waits for an MCP client. Stop the standalone process with `Ctrl+C` and test through Inspector:

```powershell
npx @modelcontextprotocol/inspector uv run ukvet-mcp
```

### Claude Desktop does not connect

Check that:

- The JSON is valid and contains only one `mcpServers` key.
- `command` points to the real `uv.exe` path.
- `--directory` points to the project root.
- `ukvet-mcp` is available in that project environment.
- `CH_API_KEY` is correct and not blank.
- Claude Desktop was fully restarted after saving.
- Developer logs do not show a startup error.

If it works in Inspector but not Claude Desktop, check the paths and environment variables because the two applications may start the process with different environments.

Never share your API key when asking for help. Remove secrets from logs before posting them.

## Summary

The local `ukvet-mcp` server is now connected to Claude Desktop. The key configuration details are the absolute path to `uv.exe`, the project root passed to `--directory`, and the `CH_API_KEY` environment variable. Since the server uses stdio, it is launched and controlled by the MCP client rather than acting like a standalone web server.
