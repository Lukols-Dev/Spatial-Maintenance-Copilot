.DEFAULT_GOAL := help
.PHONY: help api web setup lint format typecheck test check

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

api:  ## Run the perception service locally on :8000
	uv run uvicorn smc_perception.main:app --reload --port 8000

web:  ## Run the Next.js dev server on :3000
	cd apps/web && npm run dev

up:  ## Run api and web together
	$(MAKE) -j2 api web

setup:  ## Install the workspace and git hooks
	uv sync --all-packages
	uv run pre-commit install
	uv run pre-commit install --hook-type pre-push

lint:  ## Lint the Python workspace
	uv run ruff check .

format:  ## Format the Python workspace
	uv run ruff format .

typecheck:  ## Type check the paths listed in [tool.mypy]
	uv run mypy

test:  ## Run the test suite
	uv run pytest

check: lint typecheck test  ## Everything CI runs
