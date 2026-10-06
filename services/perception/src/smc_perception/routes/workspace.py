from fastapi import APIRouter

from smc_perception.atlases import list_atlases
from smc_perception.cameras import list_cameras
from smc_perception.models import Workspace
from smc_perception.rig_file import read_rig
from smc_perception.routes import WorkspaceDep
from smc_perception.settings import read_only
from smc_perception.view_sets import list_view_sets

router = APIRouter(tags=["workspace"])


@router.get("/workspace")
def get_workspace(workspace: WorkspaceDep) -> Workspace:
    """Everything the app works with. One bad file never fails it: that item carries an error."""
    cameras = list_cameras(workspace)
    return Workspace(
        read_only=read_only(),
        cameras=cameras,
        rig=read_rig(workspace),
        view_sets=list_view_sets(workspace, cameras),
        atlases=list_atlases(workspace),
    )
