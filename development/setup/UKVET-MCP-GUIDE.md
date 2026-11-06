# ukvet-mcp: how it was built, how to run it, plug it into Claude Desktop, and publish it

Written for a junior developer. Everything here comes from the real files in
`packages/ukvet-mcp` and from `development/phases/phase-01-mcp.md` and `.github/workflows/release-mcp.yml`.
PowerShell, repo root `C:\Users\44787\Desktop\ukvet`.

---

## 1. What ukvet-mcp is (in plain words)

An **MCP server** is a small program that gives an AI app (Claude Desktop) a set of **tools** it
can call. `ukvet-mcp` gives Claude 8 tools that read **official UK Companies House data**:

| Tool | Question it answers |
|---|---|
| `search_company` | Which company has this name? (returns company numbers) |
| `get_company_profile` | Is it active? How old? Are filings overdue? |
| `get_officers` | Who are the directors and secretaries? |
| `get_officer_appointments` | What other companies has this director run? |
| `get_persons_with_significant_control` | Who owns or controls it (PSC)? |
| `get_charges` | Is there debt secured on the company's assets? |
| `get_insolvency` | Any liquidation, administration, etc.? |
| `get_filing_history` | What has been filed recently? Address changes? |

How the pieces talk to each other:

```
Claude Desktop  --(MCP over stdio)-->  ukvet-mcp  --(HTTPS + your API key)-->  Companies House API
   (asks)                              (this code)                              (official data)
```

"stdio" means Claude Desktop starts `ukvet-mcp` as a child process and talks to it through
its input/output. That is why the server must **never print anything to stdout except protocol
messages**; all logs and errors go to stderr (it is written in `__main__.py`).

---

## 2. What is in the code (all files under `packages/ukvet-mcp/src/ukvet_mcp/`)

The code is split into small layers. Each layer does one job, and the layers above only use the
layers below:

```
server.py        the 8 tools Claude sees (thin: just calls service)
   |
service.py       the logic: "what does 'no charges' mean?", computed facts
   |
mappers.py       turns raw Companies House JSON into our clean models
client.py        talks HTTP: auth, retries, rate limit, cache, pagination
   |
rate_limit.py / cache.py / config.py / errors.py / models.py / normalise.py / filing_codes.py
```

| File | What it does | Why it exists |
|---|---|---|
| `__init__.py` | holds `__version__ = "0.1.0"` | one place for the version; the release workflow checks it |
| `config.py` | reads settings from environment variables (`CH_API_KEY`, timeouts, cache, limits) with `pydantic-settings` | fails fast with a clear message if the key is missing. The key is a `SecretStr` so it never shows in logs |
| `errors.py` | our own error types: `ConfigError`, `AuthError`, `InvalidInput`, `RateLimited`, `UpstreamError` | so errors turn into short readable messages for the AI, not stack traces |
| `models.py` | `pydantic` models for every result, and the `ToolResult` wrapper `{found, data, source, notes}` | every answer carries a source link and a retrieved time, so facts are citable |
| `normalise.py` | cleans company numbers (e.g. zero-pads `445790` to `00445790`) | users and AI give numbers in many shapes |
| `filing_codes.py` | maps filing form codes (like `AD01`) to plain English | filings are unreadable codes otherwise |
| `rate_limit.py` | **sliding-window rate limiter** | Companies House allows 600 requests per 5 minutes; this can never exceed that in any window (ADR-006) |
| `cache.py` | SQLite cache with a 24 h time-to-live | fewer API calls and faster answers. Errors are never cached. Director names are personal data, so the cache is short-lived (ADR-004) |
| `client.py` | the HTTP client: adds your key, limits rate, retries 429/5xx with backoff, caps pagination, maps status codes to errors | all network risk is in one file |
| `mappers.py` | raw Companies House JSON to our models | isolates the messy external format |
| `service.py` | the real logic. For example a 404 on "insolvency" is checked against the company profile, so "no insolvency record" is never claimed for a company that does not exist. Also computes company age, status counts and outstanding-charge counts | "no data" is a valid answer, not an error; and the AI should not do arithmetic |
| `server.py` | defines the 8 tools with `@mcp.tool()`, plus the server instructions | the **tool descriptions are the prompt**: Claude chooses tools from those words |
| `__main__.py` | the command `ukvet-mcp` (`--check`, `--version`, or start the server) | the entry point that Claude Desktop launches |

Packaging files:

- `pyproject.toml` (in `packages/ukvet-mcp`): name `ukvet-mcp`, version, dependencies (`httpx`,
  `mcp`, `pydantic`, `pydantic-settings`), and the line
  `[project.scripts] ukvet-mcp = "ukvet_mcp.__main__:main"`, which creates the `ukvet-mcp`
  command. Build backend: `hatchling`.
- `README.md` and `LICENSE` (MIT) in the same folder. **The README is what people see on PyPI.**
- Root `pyproject.toml`: a **uv workspace**. One repo, several packages (`ukvet-mcp`,
  `ukvet-agent`, `ukvet-evals`, `ui`), one shared environment, shared lint/type/test settings.

Data minimisation (UK GDPR): the server deliberately does **not** return dates of birth, home
addresses, nationality or occupation of directors.

---

## 3. How it was built (the order, with the commands)

You do not need to redo this, it is here so you can explain it in an interview.

1. **Start the workspace** (once):
   ```powershell
   uv init            # then edit pyproject.toml into a workspace
   uv sync --all-groups
   ```
2. **Get a Companies House API key** (free): create an application at
   https://developer.company-information.service.gov.uk/ and add a **REST** key for the **live**
   environment. Put it in `.env` at the repo root (git-ignored):
   ```
   CH_API_KEY=your-key
   ```
3. **Build bottom-up, test each layer** (this is the PR order from the Phase 1 guide):

   | Step | Files | Tests |
   |---|---|---|
   | foundation | `config.py`, `errors.py`, `models.py`, `normalise.py`, `filing_codes.py` | `tests/mcp_server/` |
   | client | `rate_limit.py`, `cache.py`, `client.py` | tests with `respx` (fake HTTP) |
   | mappers + service | `mappers.py`, `service.py` | tests using recorded fixtures |
   | tools | `server.py`, `__main__.py` | server + entry point tests |
   | fixtures | `scripts/anonymise.py`, `scripts/record_fixtures.py` | real responses recorded then anonymised |
   | release | version `0.1.0`, README, LICENSE, `release-mcp.yml` | |

4. **Run the quality checks after every step** (section 4 below).
5. **Try it for real**: the MCP Inspector, then Claude Desktop (sections 5 and 6).
6. **Publish** (section 7).

---

## 4. How you know it is ready

Run these from the repo root. All must pass before you plug it in or publish.

```powershell
uv sync --all-groups                       # install everything
uv run ruff check .                        # lint: no errors
uv run ruff format --check .               # formatting
uv run mypy                                # strict type check: Success
uv run pytest                              # all tests pass, coverage >= 80%
uv run ukvet-mcp --version                 # prints: ukvet-mcp 0.0.1
$env:CH_API_KEY="your-key"; uv run ukvet-mcp --check
                                           # prints: OK: authenticated with Companies House ...
```

What each tells you:

- `ruff` / `mypy`: code style and types are clean.
- `pytest`: the logic works against fake and recorded data (no internet needed).
- `--version`: the command exists and the version is what you expect.
- `--check`: your **real** API key works against the **real** Companies House API. If this fails
  the Claude Desktop connection will fail too.

If `--check` prints a message about `CH_API_KEY`, the key is missing or has spaces/quotes in it.
If it says 401/403 the key is wrong or is a "test" key instead of a "live" key.

Optional but recommended: look at the tools with the **MCP Inspector** (needs Node.js):

```powershell
npx @modelcontextprotocol/inspector uv run ukvet-mcp
```

A browser page opens. Click "Tools", pick one, enter a company number (for example `00445790`),
run it, and compare the answer with the Companies House website.

---

## 5. Plug it into Claude Desktop (local development version)

This is the version you are using now, and it is correct. It runs the code **from your repo**, so
any change you make to the code is picked up after a restart.

1. Open the config file: in Claude Desktop go to **Settings > Developer > Edit Config**, or open
   `%APPDATA%\Claude\claude_desktop_config.json` directly.
2. The `mcpServers` block goes **inside** the outer `{ }` of the file (your snippet was a fragment;
   the whole file must be valid JSON, with no comma after the last item):

```json
{
  "mcpServers": {
    "ukvet": {
      "command": "C:\\Users\\44787\\.local\\bin\\uv.exe",
      "args": [
        "run",
        "--directory",
        "C:\\Users\\44787\\Desktop\\ukvet",
        "ukvet-mcp"
      ],
      "env": {
        "CH_API_KEY": "paste-your-key-here"
      }
    }
  }
}
```

Why it looks like this:

- `command`: the full path of `uv.exe`, because Claude Desktop does not always have your PATH.
- `args`: `uv run --directory <repo> ukvet-mcp` means "go to the repo, run the `ukvet-mcp` command
  from the workspace".
- `env.CH_API_KEY`: the key is passed to the server. Double backslashes `\\` are required in JSON.
- If you already have other servers in the file, add `"ukvet": { ... }` next to them with a comma.

3. **Fully quit Claude Desktop** (right-click the tray icon > Quit, not just close the window) and
   open it again.
4. Check it loaded: open a new chat; the tools/connectors menu should list `ukvet` with 8 tools.
5. Test with a real question:
   > Check company 00445790: is it active, who are the current directors, any outstanding charges,
   > any recent address change?

   Watch which tools Claude calls. If it uses the wrong tool or asks silly questions, improve that
   tool's docstring in `server.py` (the descriptions are the prompt), save, and restart Claude
   Desktop.

If it does not appear or shows an error:

| Symptom | Fix |
|---|---|
| No `ukvet` in the list | the JSON is invalid (missing brace, trailing comma) or you did not fully quit |
| "Server disconnected" | open the log: `%APPDATA%\Claude\logs\mcp-server-ukvet.log` and read the last lines |
| Log says `CH_API_KEY is not set` | the `env` block is missing or misspelt (exact name `CH_API_KEY`) |
| Log says 401 / 403 | key wrong, or not a live REST key |
| Log says `uv` not found | the `command` path is wrong. Run `where.exe uv` in PowerShell and copy it |
| Works in PowerShell, not in Claude | run `uv run --directory C:\Users\44787\Desktop\ukvet ukvet-mcp` yourself; it should sit silently waiting (that is correct, stop it with Ctrl+C) |

Keep your API key **out of chat, screenshots and git**. The config file is on your PC only. If a
key was ever pasted somewhere public, create a new one in the Companies House developer site.

### Later: the published version (after PyPI release)

Anyone else, and you after the release, can use the published package instead of the repo. No
clone needed:

```json
"ukvet": {
  "command": "uvx",
  "args": ["ukvet-mcp"],
  "env": { "CH_API_KEY": "paste-your-key-here" }
}
```

(If `uvx` is not found by Claude Desktop, use the full path, for example
`C:\\Users\\44787\\.local\\bin\\uvx.exe`.) Use this form in the README quickstart and the demo GIF.

---

## 6. Before you publish: checklist

- [ ] Section 4 commands all pass.
- [ ] `YOUR_GITHUB_USERNAME` replaced with your real GitHub username in
      `packages/ukvet-mcp/pyproject.toml` (the three `[project.urls]` links) and in
      `packages/ukvet-mcp/README.md`. Otherwise PyPI shows broken links, and a released version
      can never be edited.
- [ ] Version decided. It exists in **two** places, and they must be identical:
      `packages/ukvet-mcp/pyproject.toml` (`version = "0.0.1"`) and
      `packages/ukvet-mcp/src/ukvet_mcp/__init__.py` (`__version__ = "0.0.1"`).
- [ ] The package README contains the registry ownership line (needed for the MCP registry in
      Phase 6, and it cannot be added to a version after upload):
      `<!-- mcp-name: io.github.<your-github-user>/ukvet-mcp -->`
- [ ] README has no secrets; the demo GIF comment is either filled or removed.
- [ ] Everything is committed and pushed, CI is green.

Your PyPI page currently shows **0.0.1** only. PyPI never lets you re-upload a version, so
0.0.1 is the next one. If anything is wrong after upload, the fix is 0.1.1, not an overwrite.

---

## 7. Publish to PyPI, step by step

How it works: you do not use a password or token. PyPI trusts a specific GitHub workflow
(**Trusted Publishing**). When you push a tag named `ukvet-mcp-v0.0.1`, the workflow
`.github/workflows/release-mcp.yml` runs the tests, checks the tag matches `__version__`, builds
the package and uploads it.

Since you already published 0.0.1, the one-off setup (pending publisher on PyPI, the `pypi`
environment on GitHub) should already exist. Check it quickly:

1. **PyPI**: log in at https://pypi.org > Your projects > `ukvet-mcp` > **Manage** >
   **Publishing**. You should see a publisher with: owner = your GitHub user, repository =
   `ukvet`, workflow = `release-mcp.yml`, environment = `pypi`.
2. **GitHub**: your repo > **Settings** > **Environments**: `pypi` (and `testpypi`) exist.
3. If either is missing, create it using the details above (this is the "one-off setup" in
   `docs/10-phase-1-guide.md`, section 6).

### 7a. Optional dry run on TestPyPI (recommended if anything changed in the workflow)

1. GitHub > **Actions** > **Release ukvet-mcp** > **Run workflow** > target `testpypi` > Run.
2. When green, test from a clean folder:
   ```powershell
   cd $env:TEMP
   uvx --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ ukvet-mcp --version
   ```
   It should print `ukvet-mcp 0.0.1`. (TestPyPI also needs a publisher set up on
   https://test.pypi.org. If you never did that, skip the dry run; the real release below runs
   the same tests and checks.)

### 7b. The real release

1. Make sure you are on `main`, up to date, with everything committed:
   ```powershell
   git status --short          # nothing listed
   git pull
   ```
2. Create and push the tag. The name must be exactly `ukvet-mcp-v` plus the version:
   ```powershell
   git tag ukvet-mcp-v0.0.1
   git push origin ukvet-mcp-v0.0.1
   ```
3. Watch it: GitHub > **Actions** > **Release ukvet-mcp**. Jobs: `build` (tests, tag check,
   build), then `publish-pypi`. If the `pypi` environment requires approval, click **Review
   deployments** > approve.
4. If the tag check fails ("Tag ... does not match package version"), the version in
   `__init__.py` differs from the tag. Fix the version, commit, delete the tag
   (`git tag -d ukvet-mcp-v0.0.1; git push origin :refs/tags/ukvet-mcp-v0.0.1`), and tag again.
   Nothing was uploaded in this case.

### 7c. Test the published package like a stranger would

```powershell
cd $env:TEMP
uvx ukvet-mcp --version       # expect: ukvet-mcp 0.0.1
$env:CH_API_KEY="your-key"
uvx ukvet-mcp --check         # expect: OK: authenticated ...
```

If `uvx` still gives 0.0.1, wait a minute (index delay) and retry with `uvx --refresh ukvet-mcp --version`.

Then switch Claude Desktop to the `uvx` config from the end of section 5, quit and reopen Claude
Desktop, and ask the same company question again. Also look at
https://pypi.org/project/ukvet-mcp/ and check the version, the README and the links.

### 7d. After PyPI: GitHub release and registry

- GitHub release: `gh release create ukvet-mcp-v0.0.1 --title "v0.0.1" --notes "See CHANGELOG.md"`
- MCP registry listing: Step 8 of `docs/PHASE-6-README.md`.

---

## 8. For other people: using the published ukvet-mcp

This is what a new user does after you release it. The text is written so you can paste it into
`packages/ukvet-mcp/README.md` (replace its Claude Desktop-only install section). Nothing here
needs your repo; it works from PyPI. (Not yet tested from a fresh machine: do the clean-machine
test in Phase 6 before you publish this text.)

### What every user needs

- A free **Companies House API key**: create an application at
  https://developer.company-information.service.gov.uk/ and add a **REST** key for the **live**
  environment. Everyone uses their own key (limit: 600 requests per 5 minutes per key).
- **Python 3.11 or newer** if they use pip; **uv** if they use uvx.

### Option A. In Claude Desktop, Cursor or VS Code (no coding)

1. Install `uv` once. Windows: `winget install --id=astral-sh.uv -e` (other systems:
   https://docs.astral.sh/uv/).
2. Check the key (PowerShell):
   ```powershell
   $env:CH_API_KEY="your-key"; uvx ukvet-mcp --check     # expect: OK: authenticated ...
   ```
   (macOS/Linux: `CH_API_KEY=your-key uvx ukvet-mcp --check`)
3. Add this inside `mcpServers` in the app's MCP config (Claude Desktop on Windows:
   `%APPDATA%\Claude\claude_desktop_config.json`, or Settings > Developer > Edit Config):
   ```json
   {
     "mcpServers": {
       "ukvet": {
         "command": "uvx",
         "args": ["ukvet-mcp"],
         "env": { "CH_API_KEY": "your-key" }
       }
     }
   }
   ```
4. Fully quit and reopen the app. `ukvet` appears with 8 tools.

What happens: the app starts `uvx ukvet-mcp`. `uvx` downloads the package from PyPI on first run
and runs it in an isolated cache (nothing is added to your Python). It does not auto-update:
refresh with `uvx --refresh ukvet-mcp`, or pin a version: `"args": ["ukvet-mcp==0.0.1"]`.

Windows tip: if the app cannot find `uvx`, put the full path in `command`. Find it with
`where.exe uvx` (usually `C:\\Users\\<you>\\.local\\bin\\uvx.exe`, with double backslashes in JSON).

### Option B. In your own Python project or agent (pip)

1. Install into your project's environment:
   ```powershell
   python -m venv .venv
   .venv\Scripts\activate
   pip install ukvet-mcp
   ```
2. Set your key: `$env:CH_API_KEY="your-key"` (this terminal only), or put
   `CH_API_KEY=your-key` in a `.env` file in the folder where your agent runs.
3. Check: `ukvet-mcp --check` (expect `OK: authenticated ...`).
4. Your agent starts the server as a subprocess and calls its tools over stdio (the same thing
   Claude Desktop does). Using the MCP Python SDK (check the current SDK docs for exact names):
   ```python
   import os, sys
   from mcp import ClientSession, StdioServerParameters
   from mcp.client.stdio import stdio_client

   params = StdioServerParameters(
       command=sys.executable,  # the venv's Python: no PATH problems
       args=["-m", "ukvet_mcp"],
       env={"CH_API_KEY": os.environ["CH_API_KEY"]},
   )

   async with stdio_client(params) as (read, write):
       async with ClientSession(read, write) as session:
           await session.initialize()
           tools = await session.list_tools()  # the 8 tools, with descriptions
           result = await session.call_tool("search_company", {"query": "tesco", "limit": 3})
   ```
5. Connect it to your LLM: pass the tool names, descriptions and input schemas from
   `list_tools()` to the model as its tool list. When the model asks for a tool, run
   `session.call_tool(...)` and send the result back. Frameworks do this wiring for you
   (for LangGraph: `langchain-mcp-adapters`; the OpenAI Agents SDK also has MCP support).

Points to know:
- Pass the key explicitly in `env`. The MCP client does not forward every variable of your shell
  to the subprocess, so a key set in the shell can silently go missing.
- Use `sys.executable -m ukvet_mcp` instead of the bare `ukvet-mcp` command: it guarantees the
  same environment where you ran `pip install`.
- Upgrade with `pip install -U ukvet-mcp`.
- The supported interface is the MCP tools. The Python modules are installed too, but they are
  not a documented public API and can change.

### Things to say in the README for every user

- Data is official Companies House data, up to 24 hours old (cached), read-only.
- No person search; no dates of birth or home addresses are returned.
- Not legal or financial advice. Not affiliated with or endorsed by Companies House.
- Contains public sector information licensed under the Open Government Licence v3.0.

---

## 9. Quick command reference

| Goal | Command |
|---|---|
| Install everything | `uv sync --all-groups` |
| Lint / format / types / tests | `uv run ruff check .` / `uv run ruff format --check .` / `uv run mypy` / `uv run pytest` |
| Check the key works | `uv run ukvet-mcp --check` |
| Print the version | `uv run ukvet-mcp --version` |
| Try the tools in a browser | `npx @modelcontextprotocol/inspector uv run ukvet-mcp` |
| Run the server by hand (waits silently) | `uv run ukvet-mcp` |
| Release | `git tag ukvet-mcp-v0.0.1; git push origin ukvet-mcp-v0.0.1` |
| Verify the release | `uvx ukvet-mcp --version` |

Settings you can add to the `env` block (all optional; defaults are fine): `UKVET_LOG_LEVEL`
(for example `INFO`), `UKVET_CACHE_ENABLED` (`false` turns the cache off), `UKVET_CACHE_TTL_HOURS`
(default 24), `UKVET_MAX_ITEMS` (default 100).
