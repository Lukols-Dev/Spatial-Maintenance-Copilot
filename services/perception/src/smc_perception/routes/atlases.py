from fastapi import APIRouter

from smc_perception.atlases import build, read_atlas
from smc_perception.models import AtlasBuildRequest, AtlasDetail
from smc_perception.routes import WorkspaceDep

router = APIRouter(tags=["atlases"])


@router.get("/atlases/{asset_id}")
def get_atlas(asset_id: str, workspace: WorkspaceDep) -> AtlasDetail:
    return read_atlas(workspace, asset_id)


@router.post("/atlases", status_code=201)
def post_atlas(request: AtlasBuildRequest, workspace: WorkspaceDep) -> AtlasDetail:
    """Build an atlas from a view set and write it with its report; may take tens of seconds."""
    return build(workspace, request)
