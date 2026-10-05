# uv

`uv` is used to manage the Python environment and dependencies for ukvet.

## Why we use it

- Creates and manages the virtual environment.
- Installs and updates dependencies.
- Maintains `pyproject.toml` and `uv.lock`.
- Supports the project workspace containing `ukvet-mcp` and `ukvet-agent`.

## Common commands

```bash
uv sync
uv add <package>
uv add --dev <package>
uv remove <package>
uv run <command>
```

`uv.lock` records the exact dependency versions used by the project.