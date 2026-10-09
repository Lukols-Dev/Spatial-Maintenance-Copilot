"""Localising the target in one viewpoint of a view set, and the decision on the result.

A viewpoint is an image whose clicks mark landmarks of the atlas. Those clicks
are the observations; any other clicked point is listed as ignored. Where the
target is clicked, in the image itself or in a paired shot taken from the same
spot with the door open, that click is the ground truth the projection is
measured against. Nothing is written, so a read-only service serves this too.
"""

import math
from pathlib import Path

from smc_core.calibration import Intrinsics
from smc_core.contracts import Atlas, Clicks, LandmarkObservation, Localisation, Vec2, View
from smc_core.localise import localise
from smc_core.policy import decide
from smc_core.pose import in_frame, project_landmarks
from smc_core.uncertainty import in_region

from smc_perception.atlases import read_atlas
from smc_perception.cameras import find_intrinsics
from smc_perception.errors import Conflict, NotFound
from smc_perception.image_headers import read_header
from smc_perception.models import (
    ImageSize,
    LocaliseRequest,
    LocaliseResult,
    Observation,
    Projection,
    ResolvedLocaliseRequest,
    Truth,
)
from smc_perception.view_sets import required_clicks
from smc_perception.workspace import WorkspaceFiles

# The click sigma when the request names none and the atlas has no build report.
DEFAULT_SIGMA_PX = 2.0


def localise_view(workspace: WorkspaceFiles, request: LocaliseRequest) -> LocaliseResult:
    """Localise the clicked landmarks of request.view and decide whether to trust the result."""
    detail = read_atlas(workspace, request.asset_id)
    atlas = detail.atlas
    folder = workspace.view_set(request.view_set)
    images = [workspace.image(request.view_set, request.view)]
    if request.truth_view is not None:
        images.append(workspace.image(request.view_set, request.truth_view))

    clicks = required_clicks(workspace, folder, request.view_set)
    marked = clicks.views.get(request.view, {})
    if not marked:
        raise Conflict(f"no clicks in {request.view} of view set {request.view_set!r}")
    intrinsics = _intrinsics(workspace, clicks, request.view_set)
    for path in images:
        _check_size(path, request.view_set, intrinsics)
    truth_view = _truth_view(request, clicks, atlas.target.id)

    sigma_px = request.sigma_px
    if sigma_px is None:
        built = detail.report
        sigma_px = DEFAULT_SIGMA_PX if built is None else built.request.click_sigma_px
    view = _view(request.view, clicks.camera_id, marked, atlas, sigma_px)
    localisation = localise(atlas, view, intrinsics, request.samples, request.seed)
    truth = None
    if truth_view is not None:
        truth = _truth(truth_view, clicks.views[truth_view][atlas.target.id], localisation)

    known = {landmark.id for landmark in atlas.landmarks} | {atlas.target.id}
    width, height = intrinsics["image_size"]
    resolved = {**request.model_dump(), "truth_view": truth_view, "sigma_px": sigma_px}
    return LocaliseResult(
        request=ResolvedLocaliseRequest.model_validate(resolved),
        camera_id=clicks.camera_id,
        image=ImageSize(width=width, height=height),
        localisation=localisation,
        observations=_observations(view, localisation),
        projections=_projections(view, localisation, atlas, intrinsics),
        ignored_points=[point for point in marked if point not in known],
        truth=truth,
        decision=decide(localisation, view, atlas, intrinsics),
    )


def _view(
    file: str, camera_id: str, marked: dict[str, Vec2], atlas: Atlas, sigma_px: float
) -> View:
    """The clicked landmarks of the atlas, as localise() takes them.

    They come in atlas order, not click order: RANSAC and the Monte Carlo draws
    follow the rows, and the same clicks should give the same result however
    they were made.
    """
    return View(
        view_id=file,
        camera_id=camera_id,
        observations=[
            LandmarkObservation(
                landmark_id=landmark.id, pixel=marked[landmark.id], sigma_px=sigma_px
            )
            for landmark in atlas.landmarks
            if landmark.id in marked
        ],
    )


def _intrinsics(workspace: WorkspaceFiles, clicks: Clicks, name: str) -> Intrinsics:
    """The camera the clicks were made with; 409 when the workspace cannot provide it."""
    if not clicks.camera_id:
        raise Conflict(f"the clicks of view set {name!r} name no camera")
    try:
        return find_intrinsics(workspace, clicks.camera_id)
    except NotFound as error:
        raise Conflict(str(error)) from error


def _check_size(path: Path, name: str, intrinsics: Intrinsics) -> None:
    """Fail unless the image has the size the camera was calibrated at.

    Clicks on an image of another size are pixels of another camera model: the
    pose would come out wrong without any sign of it.
    """
    header = read_header(path)
    if header.width is None or header.height is None:
        raise Conflict(f"{path.name} in view set {name!r}: {header.error}")
    size = (header.width, header.height)
    if size != intrinsics["image_size"]:
        width, height = intrinsics["image_size"]
        rotated = " (rotated by 90 degrees)" if size == (height, width) else ""
        raise Conflict(
            f"{path.name} in view set {name!r} is {size[0]}x{size[1]} px{rotated}, but "
            f"{intrinsics['camera_id']} was calibrated at {width}x{height} px"
        )


def _truth_view(request: LocaliseRequest, clicks: Clicks, target_id: str) -> str | None:
    """The image whose target click is the truth: the one asked for, else the view itself."""
    if request.truth_view is not None:
        if target_id not in clicks.views.get(request.truth_view, {}):
            raise Conflict(f"the target {target_id!r} is not clicked in {request.truth_view}")
        return request.truth_view
    return request.view if target_id in clicks.views[request.view] else None


def _observations(view: View, localisation: Localisation) -> list[Observation]:
    quality = localisation.quality
    outliers = set() if quality is None else set(quality.outlier_ids)
    return [
        Observation(
            landmark_id=observation.landmark_id,
            pixel=observation.pixel,
            inlier=None if quality is None else observation.landmark_id not in outliers,
        )
        for observation in view.observations
    ]


def _projections(
    view: View, localisation: Localisation, atlas: Atlas, intrinsics: Intrinsics
) -> list[Projection]:
    """Every landmark of the atlas through the estimated pose, the unobserved ones too."""
    if localisation.pose is None:
        return []
    observed = {observation.landmark_id for observation in view.observations}
    return [
        Projection(
            landmark_id=landmark_id,
            pixel=pixel,
            in_frame=pixel is not None and in_frame(pixel, intrinsics["image_size"]),
            observed=landmark_id in observed,
        )
        for landmark_id, pixel in project_landmarks(atlas, localisation.pose, intrinsics).items()
    ]


def _truth(truth_view: str, clicked: Vec2, localisation: Localisation) -> Truth:
    """The target clicked by hand against its projection: how far off, and whether inside."""
    target, region = localisation.target, localisation.uncertainty
    error = inside = None
    if target is not None:
        error = math.hypot(clicked[0] - target.centre_px[0], clicked[1] - target.centre_px[1])
        if region is not None:
            inside = in_region(region, target.centre_px, clicked)
    return Truth(source_view=truth_view, target_px=clicked, error_px=error, inside_95=inside)
