"""Frames of a live camera or a video, localised as they arrive and kept a while for the agent.

A frame comes as a JPEG or PNG. Its printed markers are localised against the
atlas (smc_core.frames), and the answer and the image are kept in a short
store under a fresh id. The agent's sessions read that store as the view set
LIVE: the operator's viewpoint is a frame, so the graph that runs over
recorded viewpoints runs over a camera, guards, trace and approval included.
The store is the process's memory: a restart, or KEEP newer frames, ends a
frame.
"""

import threading
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass

import cv2 as cv
import numpy as np
from smc_agent.contracts import Located
from smc_agent.vision import VisionModel, look
from smc_core.contracts import Action, Atlas
from smc_core.frames import FRAME_SAMPLES, FrameResult, localise_frame
from smc_core.markers import load_marker_set, marker_detector

from smc_perception.atlases import read_atlas
from smc_perception.cameras import find_intrinsics
from smc_perception.errors import Conflict, Invalid, NotFound
from smc_perception.live_names import LIVE as LIVE
from smc_perception.models import FrameAnswer, ImageSize, InspectAnswer, Observation
from smc_perception.workspace import WorkspaceFiles

KEEP = 120
MAX_BYTES = 10 * 1024 * 1024
# The pixel error of a marker corner, when the atlas has no build report to say how it was marked.
MARKER_SIGMA_PX = 1.0


@dataclass(frozen=True)
class Kept:
    asset_id: str
    atlas: Atlas
    result: FrameResult
    answer: FrameAnswer
    image: bytes


class LiveFrames:
    """The latest frames, oldest dropped first; safe across the service's threads."""

    def __init__(self, keep: int = KEEP) -> None:
        self.keep = keep
        self._frames: OrderedDict[str, Kept] = OrderedDict()
        self._lock = threading.Lock()

    def put(self, kept: Kept) -> None:
        with self._lock:
            self._frames[kept.answer.frame_id] = kept
            while len(self._frames) > self.keep:
                self._frames.popitem(last=False)

    def get(self, frame_id: str) -> Kept | None:
        with self._lock:
            return self._frames.get(frame_id)

    def ids(self, asset_id: str) -> list[str]:
        with self._lock:
            return [
                frame_id for frame_id, kept in self._frames.items() if kept.asset_id == asset_id
            ]

    def clear(self) -> None:
        with self._lock:
            self._frames.clear()


STORE = LiveFrames()


def post_frame(
    workspace: WorkspaceFiles,
    asset_id: str,
    camera_id: str,
    data: bytes,
    samples: int = FRAME_SAMPLES,
    store: LiveFrames = STORE,
) -> FrameAnswer:
    """Localise the frame's markers against the atlas, keep the frame, and answer with what was found."""
    started = time.perf_counter()
    if len(data) > MAX_BYTES:
        raise Invalid(f"a frame is at most {MAX_BYTES // (1024 * 1024)} MB")
    frame = cv.imdecode(np.frombuffer(data, np.uint8), cv.IMREAD_COLOR)
    if frame is None:
        raise Invalid("the frame is not a JPEG or PNG image")
    detail = read_atlas(workspace, asset_id)
    intrinsics = find_intrinsics(workspace, camera_id)
    try:
        markers = load_marker_set(workspace.rig_file)
    except (OSError, ValueError, KeyError) as error:
        raise Conflict(f"calib/rig.yaml names no printed markers: {error}") from error
    sigma_px = MARKER_SIGMA_PX if detail.report is None else detail.report.request.click_sigma_px
    frame_id = uuid.uuid4().hex[:12]
    try:
        result = localise_frame(
            frame,
            frame_id,
            detail.atlas,
            intrinsics,
            marker_detector(markers),
            markers,
            sigma_px,
            samples,
        )
    except ValueError as error:
        raise Conflict(str(error)) from error

    quality = result.localisation.quality
    outliers = set() if quality is None else set(quality.outlier_ids)
    height, width = frame.shape[:2]
    answer = FrameAnswer(
        frame_id=frame_id,
        asset_id=asset_id,
        camera_id=camera_id,
        image=ImageSize(width=width, height=height),
        observations=[
            Observation(
                landmark_id=observation.landmark_id,
                pixel=observation.pixel,
                inlier=None if quality is None else observation.landmark_id not in outliers,
            )
            for observation in result.view.observations
        ],
        localisation=result.localisation,
        decision=result.decision,
        sighting=result.sighting,
        frame_quality=result.quality,
        elapsed_ms=(time.perf_counter() - started) * 1000,
    )
    store.put(Kept(asset_id=asset_id, atlas=detail.atlas, result=result, answer=answer, image=data))
    return answer


def kept_frame(frame_id: str, store: LiveFrames = STORE) -> Kept:
    kept = store.get(frame_id)
    if kept is None:
        raise NotFound(f"no frame {frame_id!r}: it was never posted, or newer frames replaced it")
    return kept


class LivePerception:
    """The kept frames of one asset, as the agent asks about viewpoints.

    No frame lies "that way" from another, so the agent suggests none: the
    page shows the guide view to move toward instead.
    """

    def __init__(self, asset_id: str, store: LiveFrames = STORE) -> None:
        self.asset_id = asset_id
        self.store = store

    def localise(self, view: str) -> Located:
        kept = kept_frame(view, self.store)
        return Located(
            view=view, localisation=kept.result.localisation, decision=kept.result.decision
        )

    def viewpoints(self) -> list[str]:
        return self.store.ids(self.asset_id)

    def suggest(self, view: str, action: Action) -> list[str]:
        return []


# ---- a second look ----------------------------------------------------------------

# How far the region reaches beyond the target's box, as a share of the box's size.
REGION_MARGIN = 0.25


def target_region(kept: Kept) -> tuple[int, int, int, int]:
    """The frame's region around the target's projected box, with a margin; the whole frame without one."""
    width, height = kept.answer.image.width, kept.answer.image.height
    target = kept.result.localisation.target
    if target is None:
        return 0, 0, width, height
    corners = np.array(target.corners_px)
    low, high = corners.min(axis=0), corners.max(axis=0)
    margin = (high - low) * REGION_MARGIN + 16
    left, top = np.maximum(low - margin, 0)
    right, bottom = np.minimum(high + margin, [width, height])
    if right - left < 8 or bottom - top < 8:
        return 0, 0, width, height
    return int(left), int(top), int(right), int(bottom)


def inspect_frame(
    frame_id: str,
    question: str | None,
    model: VisionModel,
    model_name: str,
    store: LiveFrames = STORE,
) -> InspectAnswer:
    """Ask the vision model about the target's region of a kept frame.

    Raises ModelUnavailable when the model gives no answer.
    """
    kept = kept_frame(frame_id, store)
    left, top, right, bottom = target_region(kept)
    frame = cv.imdecode(np.frombuffer(kept.image, np.uint8), cv.IMREAD_COLOR)
    if frame is None:
        raise Conflict(f"frame {frame_id!r} can no longer be decoded")
    ok, encoded = cv.imencode(".jpg", frame[top:bottom, left:right], [cv.IMWRITE_JPEG_QUALITY, 90])
    if not ok:
        raise Conflict("the frame's region could not be encoded")
    target = kept.atlas.target.description or "the hidden component"
    asked = question or f"Is {target} visible in this region?"
    found = look(model, encoded.tobytes(), "jpeg", asked)
    return InspectAnswer(
        frame_id=frame_id,
        region_px=(left, top, right, bottom),
        question=asked,
        verdict=found.verdict,
        answer=found.answer,
        model=model_name,
    )
