# Pre-commit

`pre-commit` runs automated checks before a Git commit is created.

## Why we use it

It helps prevent common problems from entering the repository.

The configured hooks:

- Remove trailing whitespace.
- Ensure files end correctly.
- Validate YAML.
- Detect large files.
- Detect private keys.
- Run Ruff linting and formatting.
- Remove notebook outputs with `nbstripout`.

Install the hooks with:

```bash
uv run pre-commit install
```

After installation, the checks run automatically when committing.