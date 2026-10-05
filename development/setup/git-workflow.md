# Git Workflow

Git is used to track changes and maintain a clear development history.

## Branch strategy

`main` is protected. Development is done on feature branches and merged through pull requests, even when working solo.

```text
main
  │
  └── feature branch
          │
       changes
          │
       commit
          │
     Pull Request
          │
        checks
          │
       merge → main
```

## Common workflow

```bash
git checkout -b feature/my-change
git add .
git commit -m "Add my change"
git push -u origin feature/my-change
```

Then create a Pull Request and merge it into `main` after the checks pass.

## Commit guidelines

Commits should be small and describe one logical change.

Examples:

```text
Add Companies House MCP server
Add API response caching
Add Q8 network analysis
Add evaluation tests
```

## Quality check

Before creating a Pull Request:

```bash
make check
```

This runs linting, type checking and tests.

## Why we use this workflow

It provides:

- A clear history of development.
- Safer changes through feature branches.
- Evidence of testing and quality checks.
- A professional workflow suitable for collaboration and portfolio review.