from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from smc_perception.errors import WorkspaceError
from smc_perception.middleware import ReadOnlyGuard
from smc_perception.routes import atlases, boards, view_sets, workspace
from smc_perception.settings import allowed_origins

app = FastAPI(title="Spatial Maintenance Copilot - perception", version="0.1.0")

# The middleware added last runs first: CORS wraps the guard, so the 403 of a
# refused write still carries the headers a browser needs to read it.
app.add_middleware(ReadOnlyGuard)
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins(),
    allow_methods=["GET", "POST", "PUT"],
    allow_headers=["*"],
)

for module in (workspace, boards, view_sets, atlases):
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
