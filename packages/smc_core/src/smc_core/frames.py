"""One frame of a live camera or a video, localised from the printed markers in it.

The markers give the observations, and the same localisation and policy as a
clicked view turn them into a result. The markers' edges also measure the
frame's blur (smc_core.blur), which the policy holds against its limit: a
frame taken while the camera moved localises with a small reprojection error
and a pose that is off all the same. When the target's tag is in sight the
panel in front of it is open: the landmarks on that panel are not where the
atlas has them and are left out, and the tag is held against the projected
target, a check of the prediction as the operator sees the target.
"""

import math
from dataclasses import dataclass

import cv2 as cv
import numpy as np

from smc_core.blur import frame_quality
from smc_core.calibration import Intrinsics, check_frame_size
from smc_core.contracts import (
    Atlas,
    Decision,
    FrameQuality,
    LandmarkObservation,
    Localisation,
    TargetSighting,
    View,
)
from smc_core.localise import localise
from smc_core.markers import Detection, MarkerSet, detect, tag_centre
from smc_core.policy import decide
from smc_core.uncertainty import in_region

# Monte Carlo samples per frame: a frame comes every few hundred milliseconds,
# and the region's size moves by a few percent between seeds at this count.
FRAME_SAMPLES = 200


@dataclass(frozen=True)
class FrameResult:
    view: View
    localisation: Localisation
    decision: Decision
    sighting: TargetSighting | None
    quality: FrameQuality


def observed(
    detection: Detection, atlas: Atlas, frame_id: str, camera_id: str, sigma_px: float
) -> View:
    """The detected landmarks the atlas knows, in atlas order; those on an open panel left out."""
    open_panel = detection.tag is not None
    return View(
        view_id=frame_id,
        camera_id=camera_id,
        observations=[
            LandmarkObservation(
                landmark_id=landmark.id, pixel=detection.landmarks[landmark.id], sigma_px=sigma_px
            )
            for landmark in atlas.landmarks
            if landmark.id in detection.landmarks and not (open_panel and landmark.moves_with)
        ],
    )


def localise_frame(
    frame: np.ndarray,
    frame_id: str,
    atlas: Atlas,
    intrinsics: Intrinsics,
    detector: cv.aruco.ArucoDetector,
    markers: MarkerSet,
    sigma_px: float,
    samples: int = FRAME_SAMPLES,
    seed: int = 0,
) -> FrameResult:
    """The frame's markers localised, decided on, and held against the target's tag.

    Raises ValueError for a frame of another size than the camera's calibration.
    """
    check_frame_size(intrinsics, frame)
    detection = detect(detector, markers, frame)
    quality = frame_quality(frame, detection.quads)
    view = observed(detection, atlas, frame_id, intrinsics["camera_id"], sigma_px)
    localisation = localise(atlas, view, intrinsics, samples, seed)
    return FrameResult(
        view=view,
        localisation=localisation,
        decision=decide(localisation, view, atlas, intrinsics, frame=quality),
        sighting=sighting(detection, localisation),
        quality=quality,
    )


def sighting(detection: Detection, localisation: Localisation) -> TargetSighting | None:
    """The target's tag held against where the localisation put the target; None without the tag."""
    if detection.tag is None:
        return None
    centre = tag_centre(detection.tag)
    target, region = localisation.target, localisation.uncertainty
    error = inside = None
    if target is not None:
        error = math.hypot(centre[0] - target.centre_px[0], centre[1] - target.centre_px[1])
        if region is not None:
            inside = in_region(region, target.centre_px, centre)
    return TargetSighting(
        tag_px=list(detection.tag), centre_px=centre, error_px=error, inside_95=inside
    )
