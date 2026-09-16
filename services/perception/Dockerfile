# Build context is the REPOSITORY ROOT, not this directory:
#   docker build -f services/perception/Dockerfile -t smc-perception .
# uv resolves dependencies at the workspace level, so the root pyproject.toml
# and uv.lock must be present in the image before the install step.

FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# Dependency layer: copy only the manifests, so this layer is cached and does
# not rebuild every time application code changes.
COPY pyproject.toml uv.lock ./
COPY services/perception/pyproject.toml services/perception/README.md services/perception/

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project --package smc-perception

# Application layer.
COPY services/perception/src services/perception/src

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package smc-perception


FROM python:3.14-slim-bookworm AS runtime

# Never run as root. Fargate does not enforce this; the image should.
RUN useradd --create-home --uid 1000 app

WORKDIR /app
COPY --from=builder --chown=app:app /app /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

USER app
EXPOSE 8000

# --host 0.0.0.0 is mandatory. Uvicorn's default of 127.0.0.1 means "inside the
# container only": the server starts, the logs look healthy, and nothing on the
# host can reach it.
CMD ["uvicorn", "smc_perception.main:app", "--host", "0.0.0.0", "--port", "8000"]
