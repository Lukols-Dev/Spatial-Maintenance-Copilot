"""Frames of a live camera or a video: localised one by one, and looked at again on request.

POST /frames takes the image itself as the request body, a JPEG or PNG at the
size the camera was calibrated at, so a page can send a frame of its camera
or of a video it plays without encoding it in a form.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Query, Request
from fastapi.concurrency import run_in_threadpool
from smc_agent.model import ModelUnavailable

from smc_perception.agent import model_name, vision_model
from smc_perception.errors import Unavailable
from smc_perception.live import inspect_frame, kept_frame, post_frame
from smc_perception.models import FrameAnswer, InspectAnswer, InspectRequest, Name
from smc_perception.routes import WorkspaceDep

router = APIRouter(tags=["frames"])
# Why the model gave no answer goes to the log: an AWS error can name the account.
logger = logging.getLogger(__name__)


@router.post("/frames", status_code=201)
async def post_frames(
    request: Request,
    workspace: WorkspaceDep,
    asset_id: Annotated[Name, Query()],
    camera_id: Annotated[str, Query(min_length=1)],
    samples: Annotated[int, Query(ge=50, le=2000, description="Monte Carlo samples")] = 200,
) -> FrameAnswer:
    """One frame localised from its printed markers; the body is the image, JPEG or PNG."""
    data = await request.body()
    # The work is OpenCV's, not I/O: in the thread pool, as the plain endpoints are.
    return await run_in_threadpool(post_frame, workspace, asset_id, camera_id, data, samples)


@router.post("/frames/{frame_id}/inspect")
def post_inspect(frame_id: str, body: InspectRequest) -> InspectAnswer:
    """A vision-language model's look at the target's region of a kept frame: a second opinion."""
    kept_frame(frame_id)  # an unknown frame is a 404 before any model is set up
    try:
        return inspect_frame(frame_id, body.question, vision_model(), model_name())
    except ModelUnavailable as error:
        logger.warning("the vision model gave no answer: %s", error)
        raise Unavailable("the vision model gave no answer") from error
