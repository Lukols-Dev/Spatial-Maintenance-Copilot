"""Refusing writes while the service is read-only, and failing in a way the web page can read."""

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from smc_perception.settings import read_only

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
# POSTs that compute an answer and write nothing: the read-only service serves them.
READING_POSTS = {"/localise"}


class ReadOnlyGuard:
    """Answers every write with 403 while SMC_READ_ONLY is set.

    A middleware rather than a dependency: FastAPI reads the request body
    before it runs dependencies, so a dependency would refuse an upload only
    after receiving all of it.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and not _reads(scope) and read_only():
            response = JSONResponse({"detail": "the service is read-only"}, status_code=403)
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)


def _reads(scope: Scope) -> bool:
    method = scope["method"]
    return method in SAFE_METHODS or (method == "POST" and scope["path"] in READING_POSTS)


class ReadableErrors:
    """Answers an unexpected error with a 500 that the web page can read.

    Starlette answers one from its outermost layer, outside CORS, so the
    answer has no Access-Control-Allow-Origin. The browser then hides it, and
    the page reports a service it cannot reach, while the service is up and
    failing, on a full disk say. This answers from inside CORS instead, and
    raises the error again, so the server still logs it with its traceback.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = False

        async def sending(message: Message) -> None:
            nonlocal started
            started = started or message["type"] == "http.response.start"
            await send(message)

        try:
            await self.app(scope, receive, sending)
        except Exception as error:
            if not started:
                # The message of an OSError names the file by its absolute path: only its reason goes.
                reason = error.strerror if isinstance(error, OSError) and error.strerror else None
                what = type(error).__name__ + (f" ({reason})" if reason else "")
                response = JSONResponse({"detail": f"internal error: {what}"}, status_code=500)
                await response(scope, receive, send)
            raise
