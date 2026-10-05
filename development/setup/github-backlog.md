## Backlog Creation Script

`scripts/create_backlog.sh` automates the creation of the GitHub backlog from `scripts/backlog.tsv`.

The script:

- creates the required GitHub labels
- creates project milestones
- creates GitHub issues with their titles, descriptions, labels and milestones
- adds the project's Definition of Done to each issue

This avoids manually creating many GitHub issues and keeps the backlog consistent with the project plan.

### How to use

1. Make sure the GitHub CLI (`gh`) is installed.
2. Authenticate once:

```bash
gh auth login
```

3. Run the script from the `ukvet` repository:

```bash
./scripts/create_backlog.sh
```

4. Check GitHub to confirm the milestones, labels and issues were created correctly.
5. Create the GitHub Project board separately and add the issues.

### Important: avoid duplicate issues

The current script is intended to be run **once**.

**Do:**
- Update `scripts/backlog.tsv` before the first run.
- Check GitHub before running the script.
- Create additional issues manually or modify the script if new work is added later.
- Keep the TSV as the source of the planned backlog.

**Do not:**
- Run the script repeatedly, because it will create duplicate issues.
- Run it again just because you changed an existing issue.
- Delete and recreate the whole backlog unnecessarily.

If the backlog needs to be generated phase-by-phase, the script should be modified to accept a phase argument, for example `phase-0`, rather than creating every issue at once.

### Development lesson

Automation is useful for repetitive setup, but it should be **idempotent** where possible. A future improvement would make the script detect existing issues as well as labels and milestones, so re-running it does not create duplicates.