"""The HTTP endpoints, one router per resource; the work is done by the modules they call.

The endpoints are plain functions, not coroutines: FastAPI runs them in a
thread pool, so reading images and posing views never blocks the event loop.
"""

from typing import Annotated

from fastapi import Depends

from smc_perception.workspace import WorkspaceFiles, current_workspace

WorkspaceDep = Annotated[WorkspaceFiles, Depends(current_workspace)]
