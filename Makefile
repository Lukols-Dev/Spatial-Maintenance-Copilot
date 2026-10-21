.DEFAULT_GOAL := help
.PHONY: help api web up api-build api-run api-stop logs setup lint format typecheck test web-check e2e check boards markers eval eval-check synth infra-check deploy
IMAGE := smc/perception:dev
NAME  := smc-perception
# The service's settings and keys. The service reads the file itself (config.py);
# the container has no copy of it, so api-run passes it to Docker when it is there.
API_ENV := services/perception/.env
API_ENV_FILE = $(if $(wildcard $(API_ENV)),--env-file $(API_ENV))
# The frozen dataset the evaluation runs on (tools/freeze_dataset.py).
EVAL_DATASET := eval/datasets/cabinet-manual-2026-10-09

help:  ## Show this help
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

api:  ## Run the perception service locally on :8000, with services/perception/.env
	SMC_WORKSPACE="$(CURDIR)" uv run uvicorn smc_perception.main:app --reload --reload-dir services --reload-dir packages --port 8000

web:  ## Run the Next.js dev server on :3000
	cd apps/web && npm run dev

up:  ## Run api and web together
	$(MAKE) -j2 api web

api-build:  ## Build the perception container image
	docker build -f services/perception/Dockerfile -t $(IMAGE) .

api-run:  ## Run the perception container on :8000, with services/perception/.env
	docker run --rm --name $(NAME) -p 8000:8000 $(API_ENV_FILE) $(IMAGE)

api-stop:  ## Stop and remove the perception container
	-docker rm -f $(NAME)

logs:  ## Follow container logs
	docker logs -f $(NAME)

setup:  ## Install the workspace, the web app, the AWS stack's tools and the git hooks
	uv sync --all-packages
	cd apps/web && npm ci
	cd infra && npm ci
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

check: lint typecheck test web-check infra-check  ## Everything CI runs

eval:  ## Evaluate on the frozen dataset: eval/results/<dataset>/
	uv run tools/evaluate.py $(EVAL_DATASET)

eval-check:  ## Run the evaluation again and compare it with the stored results
	uv run tools/evaluate.py $(EVAL_DATASET) --check

infra-check:  ## Type check and test the AWS stack
	cd infra && npm run typecheck && npm test

synth:  ## Synthesize the AWS stack into infra/cdk.out
	cd infra && npx cdk synth --quiet

deploy:  ## Build the web app for CloudFront and deploy the stack (AWS credentials, cdk bootstrap, Docker)
	cd apps/web && NEXT_PUBLIC_API_URL=/api npm run build
	cd infra && npx cdk deploy

boards:  ## Generate the printable ChArUco rig boards
	uv run tools/gen_charuco_boards.py --out calib/charuco_boards_A4.pdf --yaml calib/rig_nominal.yaml

markers:  ## Generate the printable ArUco landmark and target markers
	uv run tools/gen_markers.py --out calib/markers_A4.pdf
