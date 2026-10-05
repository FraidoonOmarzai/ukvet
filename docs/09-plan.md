# Project Plan

| Field | Value |
|---|---|
| Version | 0.1 |
| Owner | Fraidoon Omarzai |
| Start | 05 Oct 2026 |

---

## 1. Milestones

| Milestone | Goal | Exit criteria | Target |
|---|---|---|---|
| Phase 0 — Define & plan | Know exactly what to build and that the data supports it | All Phase 0 docs complete; spike done; stakeholder sign-off | Week 1 |
| Phase 1 — MCP server | `ukvet-mcp` published and usable in Claude Desktop | Published on PyPI; all tools tested with fixtures; coverage ≥ 80% | Week 2 |
| Phase 2 — Agent | End-to-end report from UI to MCP | Q1–Q10 answered for any active company; runs via docker-compose | Week 3 |
| Phase 3 — Evals | Measured quality | 200+ item dataset; M1–M5 reported; CI gate live | Weeks 4–5 |
| Phase 4 — Observability & guardrails | Measured cost, latency, safety | Langfuse live; M6–M9 reported | Week 5 |
| Phase 5 — Model comparison | Evidence-based model choice | Comparison table published | Week 6 |
| Phase 6 — Launch | Public, documented, discoverable | v0.1.0 released; registries; 2 articles | Week 6 |

Timeline is ~6 weeks including Phase 0. If a phase slips, cut scope inside the phase — **never skip Phase 3**.

## 2. Backlog

51 issues across all phases live in `scripts/backlog.tsv`. Create them on GitHub with:

```bash
gh auth login          # once
./scripts/create_backlog.sh
```

Rules for issues:
- Each issue is **≤ 1 day** of work. If bigger, split it.
- Each issue has a milestone and at least one label.
- New ideas go to the backlog with label `v2` — not into the current phase.

## 3. GitHub Project board

Create manually (Projects → New project → Board), named **ukvet**, with columns:

**Backlog → To do (this week) → In progress → Review → Done**

- Max **2** issues "In progress" at once.
- Every Monday: move this week's issues from Backlog to To do.
- Every Friday: demo what's in Done (see `kickoff/weekly-update-template.md`).

## 4. Definition of Done (applies to every issue)

- [ ] Code merged to `main` via a pull request (even solo)
- [ ] CI green: lint, type check, tests (and evals from Phase 3)
- [ ] New code has tests; coverage stays ≥ 80%
- [ ] No secrets or personal data committed
- [ ] Docs updated if behaviour, config or decisions changed
- [ ] Decision log updated if a decision was made

## 5. Git workflow

- `main` is protected: no direct pushes, PR required, CI must pass.
- Branch names: `phase-1/rate-limiter`, `fix/charges-404`, `docs/data-notes`.
- Commit messages: Conventional Commits — `feat:`, `fix:`, `docs:`, `test:`, `chore:`.
- PR description: what, why, how tested, linked issue (`Closes #12`).

## 6. Weekly rhythm

| Day | Activity |
|---|---|
| Monday | Plan the week: pick issues, update board |
| Tue–Thu | Build |
| Friday | Demo to AAII, weekly update, review risks, update decision log |
