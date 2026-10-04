.PHONY: install lint format typecheck test check notebook clean

install:       ## Install all packages + dev tools, set up git hooks
	uv sync --all-groups
	uv run pre-commit install

lint:          ## Lint and check formatting
	uv run ruff check .
	uv run ruff format --check .

format:        ## Auto-fix lint issues and format
	uv run ruff check . --fix
	uv run ruff format .

typecheck:     ## Static type check
	uv run mypy

test:          ## Run tests with coverage
	uv run pytest

check: lint typecheck test   ## Everything CI runs

notebook:      ## Open Jupyter for the API spike
	uv run jupyter lab notebooks/

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov dist build
