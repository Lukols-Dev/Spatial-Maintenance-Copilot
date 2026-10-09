"""View sets: folders of exported views in data/views/, with the clicks made on them."""

from collections import Counter
from pathlib import Path

from pydantic import ValidationError
from smc_core.contracts import Clicks

from smc_perception.errors import Conflict, Invalid, WorkspaceError, describe
from smc_perception.image_headers import image_format, read_header
from smc_perception.models import Camera, ClicksSummary, ViewSet, ViewSetImage, ViewSetSummary
from smc_perception.workspace import (
    CLICKS_FILE,
    WorkspaceFiles,
    changed_at,
    modified_at,
    write_atomic,
)

# build_atlas triangulates a point only from two or more views.
READY_VIEWS = 2


def list_view_sets(workspace: WorkspaceFiles, cameras: list[Camera]) -> list[ViewSetSummary]:
    return [summarise(workspace, name, cameras) for name in workspace.view_set_names()]


def summarise(workspace: WorkspaceFiles, name: str, cameras: list[Camera]) -> ViewSetSummary:
    """Counts, sizes and clicks of one set; a set that cannot be read is listed with its error."""
    try:
        return _summary(workspace, name, cameras)
    except (WorkspaceError, OSError) as error:
        return ViewSetSummary(
            name=name,
            image_count=0,
            jpeg_count=0,
            image_size=None,
            mixed_sizes=False,
            camera_ids=[],
            clicks=None,
            updated_at=changed_at(workspace.views_dir / name),
            error=str(error) if isinstance(error, WorkspaceError) else "cannot read the folder",
        )


def _summary(workspace: WorkspaceFiles, name: str, cameras: list[Camera]) -> ViewSetSummary:
    folder = workspace.view_set(name)
    images = workspace.images(folder)
    clicks_path = workspace.clicks_file(folder)

    sizes: set[tuple[int, int]] = set()
    broken: list[str] = []
    for path in images:
        header = read_header(path)
        if header.width is None or header.height is None:
            broken.append(f"{path.name}: {header.error}")
        else:
            sizes.add((header.width, header.height))
    size = next(iter(sizes)) if len(sizes) == 1 else None

    files = [folder, *images, *([clicks_path] if clicks_path is not None else [])]
    return ViewSetSummary(
        name=name,
        image_count=len(images),
        jpeg_count=sum(image_format(path.name) == "jpeg" for path in images),
        image_size=size,
        mixed_sizes=len(sizes) > 1,
        camera_ids=[
            camera.camera_id
            for camera in cameras
            if camera.camera_id is not None
            and size is not None
            and (camera.image_width, camera.image_height) == size
        ],
        clicks=None if clicks_path is None else clicks_summary(workspace, clicks_path),
        updated_at=max(modified_at(path) for path in files),
        error=None if not broken else _first_and_count(broken),
    )


def _first_and_count(problems: list[str]) -> str:
    more = len(problems) - 1
    return problems[0] + (f" (and {more} more)" if more else "")


def read_view_set(workspace: WorkspaceFiles, name: str) -> ViewSet:
    folder = workspace.view_set(name)
    images = []
    for path in workspace.images(folder):
        header = read_header(path)
        images.append(
            ViewSetImage(
                file=path.name,
                width=header.width,
                height=header.height,
                format=image_format(path.name),
                error=header.error,
            )
        )
    clicks, error = None, None
    try:
        clicks_path = workspace.clicks_file(folder)
        if clicks_path is not None:
            clicks = load_clicks(workspace, clicks_path)
    except WorkspaceError as problem:
        error = str(problem)
    return ViewSet(name=name, images=images, clicks=clicks, clicks_error=error)


def load_clicks(workspace: WorkspaceFiles, path: Path) -> Clicks:
    """The clicks of a set; raises Invalid with a one-line reason when the file is wrong."""
    try:
        return Clicks.model_validate_json(path.read_bytes())
    except OSError as error:
        raise Invalid(f"cannot read {workspace.relative(path)}") from error
    except ValidationError as error:
        raise Invalid(f"{workspace.relative(path)} is not valid: {describe(error)}") from error


def required_clicks(workspace: WorkspaceFiles, folder: Path, name: str) -> Clicks:
    """The clicks of a set that a computation starts from: 409 when there are none to use."""
    path = workspace.clicks_file(folder)
    if path is None:
        raise Conflict(f"view set {name!r} has no clicks")
    try:
        return load_clicks(workspace, path)
    except Invalid as error:
        raise Conflict(str(error)) from error


def clicks_summary(workspace: WorkspaceFiles, path: Path) -> ClicksSummary:
    """How far the clicking of a set has come; an invalid file gives zeros and its error."""
    saved_at = modified_at(path)
    try:
        clicks = load_clicks(workspace, path)
    except Invalid as error:
        return ClicksSummary(
            camera_id="",
            point_count=0,
            marked_images=0,
            ready_points=0,
            point_views={},
            saved_at=saved_at,
            error=str(error),
        )

    counts = Counter(point for marked in clicks.views.values() for point in marked)
    unlisted = sorted(set(counts) - set(clicks.points))
    point_views = {point: counts[point] for point in [*clicks.points, *unlisted]}
    return ClicksSummary(
        camera_id=clicks.camera_id,
        point_count=len(point_views),
        marked_images=sum(1 for marked in clicks.views.values() if marked),
        ready_points=sum(1 for count in point_views.values() if count >= READY_VIEWS),
        point_views=point_views,
        saved_at=saved_at,
        error=None,
    )


def save_clicks(workspace: WorkspaceFiles, name: str, clicks: Clicks) -> ClicksSummary:
    """Write the clicks of a set, after checking every clicked view is an image of it.

    An empty camera id is accepted: the annotator saves a draft before the
    camera is chosen.
    """
    folder = workspace.view_set(name)
    images = {path.name for path in workspace.images(folder)}
    unknown = sorted(set(clicks.views) - images)
    if unknown:
        raise Invalid(f"not images of view set {name!r}: {', '.join(unknown)}")

    # A clicks.json that is a symlink is replaced by a file, never written through.
    path = folder / CLICKS_FILE
    write_atomic(path, (clicks.model_dump_json(indent=2) + "\n").encode("utf-8"))
    return clicks_summary(workspace, path)
