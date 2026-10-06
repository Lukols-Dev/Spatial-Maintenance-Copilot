"""Refusing writes while the service is read-only."""

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from smc_perception.settings import read_only

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


class ReadOnlyGuard:
    """Answers every write with 403 while SMC_READ_ONLY is set.

    A middleware rather than a dependency: FastAPI reads the request body
    before it runs dependencies, so a dependency would refuse an upload only
    after receiving all of it.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["method"] not in SAFE_METHODS and read_only():
            response = JSONResponse({"detail": "the service is read-only"}, status_code=403)
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)
