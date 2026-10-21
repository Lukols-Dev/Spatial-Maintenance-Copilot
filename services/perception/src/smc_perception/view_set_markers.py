"""A view set's printed markers found in every image and saved as its clicks, as annotate_markers.py does.

The clicks are those an annotator would save, so the atlas builder, the
annotator and the Locate page read them as they read clicks made by hand.
Clicks the set already has are replaced only when the request says so.
"""

import os

from smc_core.contracts import Clicks
from smc_core.images import read_images
from smc_core.markers import load_marker_set, mark_images, marker_points

from smc_perception.atlases import check_image_size
from smc_perception.cameras import find_intrinsics
from smc_perception.errors import Conflict, Invalid
from smc_perception.models import MarkerCount, MarkersAnswer, MarkersRequest
from smc_perception.view_sets import save_clicks
from smc_perception.workspace import WorkspaceFiles


def find_markers(workspace: WorkspaceFiles, name: str, request: MarkersRequest) -> MarkersAnswer:
    """Mark the rig's markers in every image of the set and write them as its clicks.json."""
    folder = workspace.view_set(name)
    rig = workspace.relative(workspace.rig_file)
    try:
        markers = load_marker_set(workspace.rig_file)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        raise Conflict(f"{rig} names no printed markers: {error}") from error
    unknown = sorted(set(request.moving) - set(markers.landmark_ids))
    if unknown:
        listed = ", ".join(str(marker) for marker in unknown)
        raise Invalid(f"moving: {listed} are not landmark markers of {rig}")
    intrinsics = find_intrinsics(workspace, request.camera_id)
    check_image_size(workspace, folder, name, intrinsics)
    if workspace.clicks_file(folder) is not None and not request.replace:
        raise Conflict(f"view set {name!r} has clicks: replace them to mark its markers")

    try:
        marked = mark_images(read_images(folder), markers, request.target_id, request.moving)
    except OSError as error:
        # Paths in the message become relative: read_images names files in full.
        message = str(error).replace(f"{folder}{os.sep}", "")
        raise Conflict(f"view set {name!r}: {message}") from error
    if not marked.views:
        raise Conflict(f"no marker of {rig} in the {marked.images} images of view set {name!r}")

    clicks = Clicks(
        camera_id=request.camera_id,
        points=marker_points(markers, request.target_id),
        views=marked.views,
    )
    return MarkersAnswer(
        view_set=name,
        images=marked.images,
        marked_images=len(marked.views),
        tag_images=marked.tag_images,
        markers=[
            MarkerCount(marker_id=marker, images=marked.marker_images[marker])
            for marker in markers.landmark_ids
        ],
        clicks=save_clicks(workspace, name, clicks),
    )
