from fastapi import APIRouter

from smc_perception.localisation import localise_view
from smc_perception.models import LocaliseRequest, LocaliseResult
from smc_perception.routes import WorkspaceDep

router = APIRouter(tags=["localisation"])


@router.post("/localise")
def post_localise(request: LocaliseRequest, workspace: WorkspaceDep) -> LocaliseResult:
    """Localise the target in one viewpoint and decide on the result; writes nothing."""
    return localise_view(workspace, request)
