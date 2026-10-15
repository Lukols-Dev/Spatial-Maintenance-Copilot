from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import boto3
from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from smc_perception.config import allowed_origins, check, configure_logging, service_settings
from smc_perception.errors import WorkspaceError
from smc_perception.middleware import ReadableErrors, ReadOnlyGuard
from smc_perception.routes import (
    atlases,
    boards,
    frames,
    localisation,
    sessions,
    view_sets,
    workspace,
)
from smc_perception.workspace_sync import copy_workspace


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """At startup: the workspace copied from S3 if it lives there, then the settings checked and logged."""
    configure_logging()
    settings = service_settings()
    if settings.smc_workspace_s3:
        settings.workspace_root.mkdir(parents=True, exist_ok=True)
        copy_workspace(boto3.client("s3"), settings.smc_workspace_s3, settings.workspace_root)
    check()
    yield


app = FastAPI(title="Spatial Maintenance Copilot - perception", version="0.1.0", lifespan=lifespan)

# The middleware added last runs first: CORS wraps the guard and the error
# answer, so a refused write's 403 and an unexpected error's 500 still carry
# the headers a browser needs to read them.
app.add_middleware(ReadableErrors)
app.add_middleware(ReadOnlyGuard)
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins(),
    allow_methods=["GET", "POST", "PUT"],
    allow_headers=["*"],
)

for module in (workspace, boards, view_sets, atlases, localisation, sessions, frames):
    app.include_router(module.router)


@app.exception_handler(WorkspaceError)
async def workspace_error(_request: Request, error: WorkspaceError) -> JSONResponse:
    return JSONResponse({"detail": str(error)}, status_code=error.status_code)


@app.exception_handler(RequestValidationError)
async def validation_error(_request: Request, error: RequestValidationError) -> JSONResponse:
    """FastAPI's 422 list without the input each problem echoes.

    A NaN in the body comes back in that input, which JSON cannot carry, and
    the 422 would become a 500; a model-level problem would echo the whole body.
    """
    problems = [
        {key: value for key, value in problem.items() if key != "input"}
        for problem in error.errors()
    ]
    return JSONResponse({"detail": jsonable_encoder(problems)}, status_code=422)


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", service="perception", version=app.version)
