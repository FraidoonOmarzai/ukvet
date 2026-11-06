# Phase 6: Launch (roadmap and step-by-step)

Goal in one line: make ukvet public, installable, honest and findable, then tell people about it.

Exit criteria (from `docs/09-plan.md`): **v0.1.0 released; listed in MCP registries; two articles
published; CV and LinkedIn updated with real metrics.** Planned time: about one week.

Why this phase matters: until now only you can see the work. A hiring manager will judge ukvet in
about two minutes: the README, whether `uvx ukvet-mcp` works, and whether the numbers are real.
Phase 6 is about making those two minutes go well.

PowerShell, repo root, `uv run` as before. Replace `<github-user>` with your GitHub username.

---

## Rules that apply to everything in this phase (from `docs/06-legal-and-ethics.md`)

1. **Real numbers only.** Every figure in the README, articles, CV and LinkedIn comes from
   `docs/results.md` or `docs/eval-report.md`. No rounding up, no "about 99%".
2. **Say what failed.** Claude's `inj-016` weakness, the fallback bug, the 18-report test split.
   Honesty is the selling point of this project.
3. **OGL attribution line** (Contains public sector information licensed under the Open Government
   Licence v3.0) must be in the README.
4. **Never imply Companies House endorses or runs ukvet.** Add: "Not affiliated with or endorsed by
   Companies House."
5. **No real trace links, no screenshots showing company or person names** (decision #52). Use
   anonymised or fixture companies in the GIF and articles.
6. **No hosted public demo.** It is outside the MVP and is a review trigger in the legal doc.
   Docker one-command setup is the demo.
7. **No secrets.** Check before making anything public (Step 1).

---

## Step 0. Preconditions (30 minutes)

```powershell
git status --short                      # clean
git tag --list                          # phase-5-complete should exist
git log --oneline -5
uv run pytest -q
uv run ruff check .
uv run mypy
```

- Phase 5 committed and tagged, CI green on the latest commit on GitHub (Actions tab).
- The first green CI run also closes risk R16 (the Docker image build). Note it in `docs/07-risks.md`.
- **Is `ukvet-mcp` already on PyPI?** Open https://pypi.org/project/ukvet-mcp/ . 404 = free. If it
  exists and is yours, PyPI will not let you upload the same version again (see Step 5).
- Also check https://test.pypi.org/project/ukvet-mcp/ .

## Step 1. Pre-launch audit (2 hours, do not skip)

Once the repo is public, anything in git history is public forever.

1. **Secrets in history.** Install and run gitleaks (or `git log -p | Select-String "sk-|api_key|LLM_API_KEY"`):
   ```powershell
   winget install gitleaks.gitleaks
   gitleaks detect --source . --log-opts="--all"
   ```
   If a real key was ever committed: rotate (revoke and re-create) that key. Rewriting history is
   a last resort; rotating is the real fix.
2. **Ignored files.** `.gitignore` must contain `.env`, `.env.claude`, `env.qwen`, `numbers.txt`,
   `evals/results/phase5-live-*`, `data/raw`. Check: `git ls-files | Select-String "\.env|numbers|raw"` prints nothing.
3. **Fixtures anonymised.** `uv run ukvet-evals validate --dataset v0.1` says OK. Spot-check three
   snapshot files: names are `TEST COMPANY nnn`, no real people.
4. **No trace links or real names** in `docs/` (search for `langfuse`, `http`, and any real company
   name you used during demos).
5. **Your own details.** Decide what email and name appear in `pyproject.toml` (authors) and the
   licence. Use what you are happy to have public.

## Step 2. Test the README on a clean machine (1-2 hours)

A README that has never been followed by someone else is usually broken. Use a fresh folder (or a
second PC, or a clean VM) and follow **only** what the README says:

```powershell
cd $env:TEMP; git clone https://github.com/<github-user>/ukvet ukvet-clean; cd ukvet-clean
```

Walk through the quickstart exactly as written: Docker one-command setup (`docker compose up`),
then adding the MCP server to Claude Desktop, then asking Q1 from the question set. Every place
you hesitate or have to guess is a README bug: fix it in the real repo.

## Step 3. Finish the README (half a day)

The README is the product page. Order matters (top = most important):

1. Title, one-sentence description, badges (CI, PyPI, licence, Python version).
2. **Demo GIF** (`docs/demo.gif`, 20 to 40 seconds): Claude Desktop answering a due-diligence
   question using ukvet-mcp. Use a fixture/anonymised company or a well-known large company, never a
   private individual. Record with ScreenToGif or Windows Game Bar; keep it under 5 MB.
3. **Quickstart** in 3 commands or fewer: `uvx ukvet-mcp` for the MCP server, the Claude Desktop
   JSON snippet, `docker compose up` for the agent.
4. **What it is** (3 bullets) and **architecture diagram** (one picture, from `docs/11-system-design.md`).
5. **Results table** copied from `docs/results.md` (real numbers: M1 100%; M2 0/156 vs 1/154;
   M4 156/156 vs 153/154; M6 96.7% vs 100%; p95 6.6 s vs 24.2 s; cost £0.00058 vs £0.0076 per
   report). One sentence on the recommendation, link to the full file.
6. **Limitations** (honest list): 18-report test split, one open-weight model, rule-based scorers,
   `inj-016` open follow-up, not legal/financial advice.
7. **Attribution and disclaimer**: OGL v3.0 line; "Not affiliated with or endorsed by Companies
   House"; MIT licence.
8. **Docs table** with links. **Remove the stray `...` row** in "Project documents".

Check every link by clicking it on GitHub, not in your editor.

## Step 4. Changelog and versions (30 minutes)

Decide and write down (decision log):

| Item | Decision to make |
|---|---|
| ukvet-mcp version | `0.0.1` (already in pyproject) |
| ukvet-agent version | currently `0.0.1`|
| Git tags | the PyPI workflow triggers on `ukvet-mcp-v0.0.1`. The GitHub release can be the same tag. Do **not** also create a separate `v0.0.1` tag unless you want two |

Create `CHANGELOG.md` (Keep a Changelog style):

```markdown
# Changelog

## [0.0.1] - 2026-11-xx
### Added
- ukvet-mcp: 8 read-only Companies House tools over MCP (stdio).
- ukvet-agent: LangGraph due-diligence agent with deterministic facts, rules, citations.
- ukvet-evals: dataset v0.1, scorers for M1/M2/M4/M6, model comparison.
### Known limitations
- See README "Limitations".
```

If you change a version, change it in `pyproject.toml` **before** tagging. Tags are not editable
in practice.

## Step 5. Publish ukvet-mcp to PyPI (2-3 hours first time)

Uses Trusted Publishing, which needs no token. Set-up (once), from the Phase 1 guide:

1. On **pypi.org** > Account > Publishing > add a **pending publisher**: project `ukvet-mcp`,
   owner `<github-user>`, repo `ukvet`, workflow `release-mcp.yml`, environment `pypi`.
2. Same on **test.pypi.org** with environment `testpypi`.
3. GitHub repo > Settings > Environments: create `pypi` and `testpypi`. Add yourself as required
   reviewer on `pypi` (a safety brake).

**Before the first upload**, add the registry verification line to the README that PyPI will show
(this must be in the published package README, and an uploaded version can never be changed):

```markdown
<!-- mcp-name: io.github.<github-user>/ukvet-mcp -->
```

Check `packages/ukvet-mcp/pyproject.toml` `readme = "README.md"` points to the file that has this
line (a package-level README, not only the repo root).

**Dry run (TestPyPI):** GitHub > Actions > "release-mcp" > Run workflow > target `testpypi`. Then
on a clean shell:

```powershell
uvx --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ ukvet-mcp --version
```

**Real release:**

```powershell
git tag ukvet-mcp-v0.0.1
git push origin ukvet-mcp-v0.0.1
```

Approve the `pypi` environment in Actions. When it finishes:

```powershell
uvx ukvet-mcp --version        # from a different folder, ideally another machine
```

If the name was already taken or a version was already uploaded, PyPI refuses with a 400/403.
You then bump to `0.1.1` (do not try to overwrite). Mistake budget: expect one failed attempt.

## Step 6. GitHub release (30 minutes)

```powershell
gh release create ukvet-mcp-v0.0.1 --title "v0.0.1" --notes-file CHANGELOG.md
```

(or via the GitHub web UI: Releases > Draft new release > choose the tag > paste the 0.0.1
changelog section). Attach nothing large; link to `docs/results.md` in the notes.

## Step 7. Repo hygiene and discoverability (1 hour)

- Repo **description** (one line) and **topics**: `mcp`, `mcp-server`, `companies-house`,
  `langgraph`, `llm-evaluation`, `due-diligence`, `python`.
- **Social preview image** (Settings > Social preview): a simple 1280x640 image with the name and
  one line.
- Add `LICENSE` (MIT), `SECURITY.md` (how to report a problem, short), `CONTRIBUTING.md` (how to
  run tests, 10 lines) and 2 issue templates (bug, question). Keep them short.
- Turn on **Discussions** only if you will check them. Otherwise leave off.
- Pin the repo on your GitHub profile.

## Step 8. List the MCP server in registries (half a day)

Procedure below was checked against the official docs on 5 Nov 2026
(https://modelcontextprotocol.io/registry/quickstart and
https://modelcontextprotocol.io/registry/package-types). The registry is marked **preview**, so if
a command differs from what you see, trust the live docs.

### 8a. Official MCP Registry

The registry only stores metadata; it checks that the PyPI package belongs to you through the
`mcp-name:` line you added in Step 5. So **PyPI must be published first**.

1. Install the CLI (Windows PowerShell) Install the publisher tool. Run this in a folder outside the repo, such as Downloads::
   ```powershell
   $arch = if ([System.Runtime.InteropServices.RuntimeInformation]::ProcessArchitecture -eq "Arm64") { "arm64" } else { "amd64" }
   Invoke-WebRequest -Uri "https://github.com/modelcontextprotocol/registry/releases/latest/download/mcp-publisher_windows_$arch.tar.gz" -OutFile "mcp-publisher.tar.gz"
   tar xf mcp-publisher.tar.gz mcp-publisher.exe; rm mcp-publisher.tar.gz
   # move mcp-publisher.exe to a folder on your PATH (not into the repo)
   mcp-publisher --help
   ```
2. In `packages/ukvet-mcp` create `server.json` (run `mcp-publisher init` to generate a template,
   then edit):
   ```json
   {
     "$schema": "https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json",
     "name": "io.github.<github-user>/ukvet-mcp",
     "title": "ukvet: UK Companies House",
     "description": "Read-only UK Companies House tools for due diligence: profile, officers, PSC, charges, filings, insolvency.",
     "repository": { "url": "https://github.com/<github-user>/ukvet", "source": "github" },
     "version": "0.0.1",
     "packages": [
       {
         "registryType": "pypi",
         "identifier": "ukvet-mcp",
         "version": "0.0.1",
         "transport": { "type": "stdio" },
         "environmentVariables": [
           { "name": "COMPANIES_HOUSE_API_KEY", "description": "Your free Companies House API key",
             "isRequired": true, "isSecret": true, "format": "string" }
         ]
       }
     ]
   }
   ```
   Use the real environment variable name your server reads (check `packages/ukvet-mcp` settings).
   The `name` must match the `mcp-name:` line exactly. With GitHub login the name **must** start
   with `io.github.<github-user>/` (lower/upper case as your GitHub name).
3. Log in and publish:
   ```powershell
   mcp-publisher login github      # opens a device-code page; enter the code
   mcp-publisher publish
   ```
4. Verify:
   ```powershell
   curl "https://registry.modelcontextprotocol.io/v0.1/servers?search=io.github.<github-user>/ukvet-mcp"
   ```
   Troubleshooting from the docs: "Registry validation failed for package" = the `mcp-name:` line
   is missing from the **published** PyPI README (needs a new PyPI version, so get it right in
   Step 5); "Invalid or expired token" = log in again; "no permission" = name prefix does not match
   your GitHub username.
5. Optional later: automate with GitHub Actions
   (https://modelcontextprotocol.io/registry/github-actions.md). Not needed for launch.

### 8b. Other directories (30 minutes each, optional but useful)

Submit once each. Their forms change, so follow their own pages:

| Directory | How |
|---|---|
| Smithery (smithery.ai) | sign in with GitHub, add the server from your repo |
| Glama (glama.ai/mcp/servers) | usually indexes GitHub automatically; claim the listing |
| PulseMCP (pulsemcp.com) | has a submit form; also pulls from the official registry |
| mcp.so | submit form |
| awesome-mcp-servers (GitHub) | open a pull request adding one line under the right category; follow its CONTRIBUTING rules |

Keep a list of each submission and its link (you will want it for the 30-day review).

## Step 9. Article 1: building ukvet (1-2 days)

Platform: Medium (plan), optionally cross-post to dev.to. Length 1,200 to 1,800 words. Outline:

1. **Hook**: the question ("can an AI agent do UK company due diligence and prove it?") and the
   answer in one honest line.
2. **What it does** with the GIF.
3. **Architecture**: MCP server, deterministic facts and rules, LLM only writes the wording,
   citation checker. One diagram.
4. **Three decisions and why** (pick from the decision log): deterministic researcher (ADR-007),
   LLM abstraction (ADR-003), the test split looked at once.
5. **What went wrong** (this is the best part): the 30 silent template fallbacks caused by the
   `temperature` 400 error; the event-loop bug in the check script; thinking mode on by default.
6. **What I would do differently**; link to the repo.

Do not include real company names or Langfuse links. Use the OGL line and the "not affiliated" line
at the bottom.

## Step 10. Article 2: what the evals revealed (1-2 days)

1. **Why evals** (accuracy that is measured, not claimed). Explain M1, M2, M4, M6 in plain words.
2. **The numbers**: the results table from `docs/results.md`.
3. **The comparison**: Claude Haiku 5.5 vs self-hosted Qwen3.6-27B. Accuracy tied within noise;
   Claude about 3.7x faster at p95 and about 13x cheaper per report; the self-hosted figure is a
   best case (GPU time of the live run only). Whole experiment about £3.20 of GPU.
4. **Misses**: `inj-016` on Claude; the derived-year mismatch between checker and scorer (c007);
   say which items you verified and which are still open.
5. **Honest limits**: 18 test reports, one model each, one run.
6. **What next**: defend `inj-016`, larger test split.

Before publishing, run the two verification commands from the Phase 5 close-out (c007's
`date_of_creation`, the `CANARY-A16` cache lines) and make the sentences match what you find.

## Step 11. CV and LinkedIn (1-2 hours)

Only claims you can show. Template for the CV (adapt, keep numbers exact):

> **ukvet**: UK Companies House due-diligence agent (MCP server + LangGraph agent + eval harness).
> Published `ukvet-mcp` to PyPI and the MCP registry. Built a 156-claim citation-checked eval
> harness; compared Claude Haiku 5.5 with self-hosted Qwen3.6-27B (p95 6.6 s vs 24.2 s; £0.00058 vs
> £0.0076 per report). Two write-ups published.

On LinkedIn: add the repo under Projects/Featured, post once with the GIF and a link to article 1
(or 2), and say what you learned, not "excited to announce". Do not claim users or downloads you do
not have.

## Step 12. After launch: record adoption (M13 to M16)

The plan sets no targets, only honest reporting. Create `docs/adoption.md` with a table and fill
it at **launch day** and again at **launch + 30 days**:

| Metric | Source | Launch | +30 days |
|---|---|---|---|
| M13 PyPI downloads | pypistats.org/packages/ukvet-mcp | | |
| M14 GitHub stars / forks | repo page | | |
| M15 external issues / PRs | repo Issues | | |
| M16 Medium reads | Medium stats | | |

Add a calendar reminder for day 30. Then set README status to "Phase 6 complete: v0.1.0 released"
and tag nothing further.

---

## Suggested schedule

| Day | Work |
|---|---|
| 1 | Steps 0, 1, 2 (audit, clean-machine test) |
| 2 | Steps 3, 4 (README, changelog, versions) |
| 3 | Steps 5, 6, 7 (PyPI, release, repo hygiene) |
| 4 | Step 8 (registries) |
| 5-6 | Steps 9, 10 (articles) |
| 7 | Step 11, 12 (CV, LinkedIn, adoption file) |

## Definition of done

- [ ] No secrets in history; ignored files not tracked; fixtures anonymised
- [ ] README quickstart followed successfully on a clean machine
- [ ] README final: GIF, results, limitations, OGL line, not-affiliated line; stray `...` removed
- [ ] CHANGELOG, versions aligned, tag pushed
- [ ] `uvx ukvet-mcp --version` works from PyPI
- [ ] GitHub release published
- [ ] Listed in the official MCP registry (curl check returns your server); other directories submitted
- [ ] Article 1 and article 2 published
- [ ] CV and LinkedIn updated with exact numbers
- [ ] `docs/adoption.md` created; 30-day reminder set
- [ ] Decision log rows, risks (R16 closed), README status updated

## Common mistakes

| Mistake | Fix |
|---|---|
| Uploading to PyPI before adding the `mcp-name:` line | PyPI versions cannot be changed; publish `0.1.1` with the line |
| Tag name does not match the workflow trigger | the workflow listens for `ukvet-mcp-v*`; check `release-mcp.yml` |
| Tagging before bumping the version | bump, commit, then tag |
| README links work in the editor but not on GitHub | click them on GitHub |
| Screenshots with real company or person names | use fixture or large public companies only, no people |
| Rounding numbers up in the articles | copy from `docs/results.md` |
| Making the repo public before the gitleaks check | audit first (Step 1) |
| Claiming Companies House partnership | add the "not affiliated" line |

Sources: https://modelcontextprotocol.io/registry/quickstart ,
https://modelcontextprotocol.io/registry/package-types
