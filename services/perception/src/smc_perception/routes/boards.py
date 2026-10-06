from fastapi import APIRouter

from smc_perception.models import Board, BoardMeasurement
from smc_perception.rig_file import measure_board
from smc_perception.routes import WorkspaceDep

router = APIRouter(tags=["boards"])


@router.put("/boards/{board_id}/measurement")
def put_measurement(board_id: str, measurement: BoardMeasurement, workspace: WorkspaceDep) -> Board:
    """Record a caliper reading in calib/rig.yaml, changing nothing else in the file."""
    return measure_board(workspace, board_id, measurement)
