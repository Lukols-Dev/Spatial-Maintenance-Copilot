.DEFAULT_GOAL := help
.PHONY: help api web up api-build api-run api-stop logs setup lint format typecheck test web-check e2e check boards
IMAGE := smc/perception:dev
NAME  := smc-perception

help:  ## Show this help
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

api:  ## Run the perception service locally on :8000
	SMC_WORKSPACE="$(CURDIR)" uv run uvicorn smc_perception.main:app --reload --reload-dir services --reload-dir packages --port 8000

web:  ## Run the Next.js dev server on :3000
	cd apps/web && npm run dev

up:  ## Run api and web together
	$(MAKE) -j2 api web

api-build:  ## Build the perception container image
	docker build -f services/perception/Dockerfile -t $(IMAGE) .

api-run:  ## Run the perception container on :8000
	docker run --rm --name $(NAME) -p 8000:8000 $(IMAGE)

api-stop:  ## Stop and remove the perception container
	-docker rm -f $(NAME)

logs:  ## Follow container logs
	docker logs -f $(NAME)

setup:  ## Install the workspace, the web app and the git hooks
	uv sync --all-packages
	cd apps/web && npm ci
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

web-check:  ## Lint, type check and unit test the web app
	cd apps/web && npm run lint && npm run typecheck && npm test

e2e:  ## Build the web app and run its browser tests (needs Google Chrome)
	cd apps/web && npm run test:e2e

check: lint typecheck test web-check  ## Everything CI runs

boards:  ## Generate the printable ChArUco rig boards
	uv run tools/gen_charuco_boards.py --out calib/charuco_boards_A4.pdf --yaml calib/rig_nominal.yaml
