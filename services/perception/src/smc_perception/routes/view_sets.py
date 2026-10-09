from typing import Annotated

from fastapi import APIRouter, File, Form, Header, Query, Response, UploadFile
from fastapi.responses import FileResponse
from smc_core.contracts import Clicks

from smc_perception.cameras import list_cameras
from smc_perception.image_headers import image_format
from smc_perception.models import ClicksSummary, ViewSet, ViewSetSummary
from smc_perception.routes import WorkspaceDep
from smc_perception.thumbnails import (
    MAX_WIDTH,
    MIN_WIDTH,
    entity_tag,
    is_cached,
    thumbnail,
    thumbnail_width,
)
from smc_perception.view_set_import import Upload, import_view_set
from smc_perception.view_sets import read_view_set, save_clicks, summarise

router = APIRouter(tags=["view sets"])

MEDIA_TYPES = {"png": "image/png", "jpeg": "image/jpeg"}


@router.post("/view-sets", status_code=201)
def post_view_set(
    name: Annotated[str, Form()],
    files: Annotated[list[UploadFile], File(description="one video, or one or more photos")],
    workspace: WorkspaceDep,
    window: Annotated[
        int, Form(ge=1, description="video: keep the sharpest of every n frames")
    ] = 15,
) -> ViewSetSummary:
    uploads = [Upload(file.filename or "", file.file) for file in files]
    import_view_set(workspace, name, window, uploads)
    return summarise(workspace, name, list_cameras(workspace))


@router.get("/view-sets/{name}")
def get_view_set(name: str, workspace: WorkspaceDep) -> ViewSet:
    return read_view_set(workspace, name)


@router.get("/view-sets/{name}/images/{file}", response_class=FileResponse)
def get_image(
    name: str,
    file: str,
    workspace: WorkspaceDep,
    width: Annotated[
        int | None,
        Query(
            ge=MIN_WIDTH, le=MAX_WIDTH, description="a JPEG this wide, never wider than the image"
        ),
    ] = None,
    if_none_match: Annotated[str | None, Header()] = None,
) -> Response:
    """The image as stored, or with ?width a JPEG thumbnail of it."""
    path = workspace.image(name, file)
    status = path.stat()
    scaled = thumbnail_width(path, width)
    # no-cache: revalidate every time, as a set may be imported again under its
    # name; the entity tag makes that a 304 while the file stays the same.
    headers = {"Cache-Control": "no-cache", "ETag": entity_tag(status, scaled)}
    if is_cached(if_none_match, headers["ETag"]):
        return Response(status_code=304, headers=headers)
    if scaled is None:
        return FileResponse(
            path, media_type=MEDIA_TYPES[image_format(file)], headers=headers, stat_result=status
        )
    return Response(thumbnail(path, scaled), media_type="image/jpeg", headers=headers)


@router.put("/view-sets/{name}/clicks")
def put_clicks(name: str, clicks: Clicks, workspace: WorkspaceDep) -> ClicksSummary:
    return save_clicks(workspace, name, clicks)
