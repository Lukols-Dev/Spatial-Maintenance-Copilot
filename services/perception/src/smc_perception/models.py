"""The JSON of the HTTP API, field for field.

apps/web/lib/api-examples/ holds an example of every model, which the web app
uses as mocks and tests/test_api_examples.py validates here. Responses have
no defaults, so an example that misses a field fails; every model forbids
unknown keys, so a misspelt one fails too.

A file that cannot be read is listed with its error rather than failing the
whole response, which is why so many fields may be None.
"""

from datetime import date
from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator
from smc_core.contracts import Atlas, Clicks

from smc_perception.workspace import NAME_PATTERN

PositiveMm = Annotated[float, Field(gt=0)]
Name = Annotated[str, Field(pattern=NAME_PATTERN)]


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Camera(ApiModel):
    """One calibration file of calib/intrinsics/."""

    file: str
    camera_id: str | None
    image_width: int | None
    image_height: int | None
    frames: int | None
    rms_px: float | None
    fx: float | None
    fy: float | None
    cx: float | None
    cy: float | None
    dist_coeffs: list[float] = Field(description="k1 k2 p1 p2 k3; empty when the file is broken")
    std: dict[str, float] = Field(description="1-sigma of fx fy cx cy k1 k2 p1 p2 k3")
    calibrated_at: str | None = Field(description="as written in the file")
    opencv_version: str | None
    error: str | None


class Board(ApiModel):
    """One board of calib/rig.yaml."""

    id: str
    squares_x: int
    squares_y: int
    marker_ids: tuple[int, int] = Field(description="first and last, inclusive")
    square_nominal_mm: float
    marker_nominal_mm: float
    square_measured_mm: float | None
    marker_measured_mm: float | None
    measurement_uncertainty_mm: float | None
    substrate: str | None
    measured_on: date | None
    measured: bool = Field(description="whether the square side is measured, which posing needs")


class Rig(ApiModel):
    dictionary: str | None
    boards: list[Board]
    error: str | None


class BoardMeasurement(ApiModel):
    """A caliper reading of a printed board, as mounted."""

    square_measured_mm: PositiveMm
    measurement_uncertainty_mm: float = Field(ge=0)
    marker_measured_mm: PositiveMm | None = None
    substrate: str | None = Field(default=None, max_length=200)
    measured_on: date | None = Field(default=None, description="the server's today when absent")

    @field_validator("substrate")
    @classmethod
    def _blank_is_none(cls, value: str | None) -> str | None:
        return (value.strip() or None) if value is not None else None

    @model_validator(mode="after")
    def _marker_inside_its_square(self) -> Self:
        if (
            self.marker_measured_mm is not None
            and self.marker_measured_mm >= self.square_measured_mm
        ):
            raise ValueError("marker_measured_mm must be smaller than square_measured_mm")
        return self


class ClicksSummary(ApiModel):
    camera_id: str
    point_count: int = Field(description="points listed or clicked")
    marked_images: int
    ready_points: int = Field(description="points clicked in at least two images")
    point_views: dict[str, int] = Field(
        description="images each point is clicked in, in the annotator's order"
    )
    saved_at: AwareDatetime
    error: str | None


class ViewSetSummary(ApiModel):
    name: str
    image_count: int
    jpeg_count: int
    image_size: tuple[int, int] | None = Field(description="None when empty or sizes differ")
    mixed_sizes: bool
    camera_ids: list[str] = Field(description="cameras calibrated at image_size")
    clicks: ClicksSummary | None
    updated_at: AwareDatetime = Field(description="when the newest file of the set changed")
    error: str | None


class ViewSetImage(ApiModel):
    file: str
    width: int | None
    height: int | None
    format: Literal["png", "jpeg"]
    error: str | None


class ViewSet(ApiModel):
    name: str
    images: list[ViewSetImage]
    clicks: Clicks | None
    clicks_error: str | None


class AtlasSummary(ApiModel):
    asset_id: str
    file: str
    version: str | None
    frame: str | None
    landmarks: int | None
    target_id: str | None
    target_sigma_mm: float | None
    built_at: AwareDatetime
    has_report: bool
    error: str | None


class AtlasBuildRequest(ApiModel):
    asset_id: Name
    view_set: Name
    camera_id: str = Field(min_length=1)
    board: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    target_extent_mm: tuple[PositiveMm, PositiveMm, PositiveMm]
    target_measured_mm: tuple[float, float, float] | None = Field(
        default=None, description="the target centre measured by hand, for a cross-check"
    )
    click_sigma_px: float = Field(default=2.0, gt=0)
    target_centre_sigma_mm: float = Field(default=5.0, ge=0)
    samples: int = Field(default=200, ge=10, le=2000)
    seed: int = Field(default=0, ge=0)
    version: str = "1"

    @field_validator("asset_id")
    @classmethod
    def _not_a_report_name(cls, value: str) -> str:
        # <id>.report.json is the report of <id>, so this atlas would not be listed.
        if value.lower().endswith(".report"):
            raise ValueError("asset_id must not end with .report")
        return value


class PosedView(ApiModel):
    file: str
    corners: int
    rms_px: float


class AtlasPoint(ApiModel):
    id: str
    position_mm: tuple[float, float, float]
    sigma_mm: float = Field(description="as stored in the atlas")
    triangulation_sigma_mm: float = Field(description="from the clicks and the poses alone")
    views: int
    worst_px: float
    ray_angle_deg: float
    is_target: bool


class AtlasBuildReport(ApiModel):
    """What went into an atlas built by the service, for reading before trusting it."""

    built_at: AwareDatetime
    request: AtlasBuildRequest
    posed_views: list[PosedView]
    unposed_views: list[str] = Field(description="clicked views in which the board was not found")
    points: list[AtlasPoint]
    skipped: dict[str, str] = Field(description="point id -> why it is not in the atlas")
    target_gap_mm: float | None = Field(description="located minus measured target centre")


class AtlasDetail(ApiModel):
    atlas: Atlas
    report: AtlasBuildReport | None


class Workspace(ApiModel):
    read_only: bool
    cameras: list[Camera]
    rig: Rig
    view_sets: list[ViewSetSummary]
    atlases: list[AtlasSummary]
