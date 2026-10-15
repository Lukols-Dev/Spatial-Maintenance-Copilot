"""Typed contracts of the localisation pipeline.

Everything that leaves the geometry code, for a file, the HTTP API or an agent
tool, is one of these models. Positions are millimetres in the asset frame and
pixels in the calibrated frame. The Localisation carries measurements only:
whether a value is good enough is the policy's call. The Decision is that call,
and it carries the Policy it applied, so the facts and the thresholds held
against them never mix.
"""

import math
from enum import StrEnum
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

Vec2 = tuple[float, float]
Vec3 = tuple[float, float, float]


class Contract(BaseModel):
    """Immutable, and strict about keys: a typo in an atlas file fails loudly."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class Landmark(Contract):
    """A reference point on the asset, measured in the asset frame.

    seen_from and seen_within_deg say from where the landmark was seen while the
    atlas was built: a camera outside that cone may be looking at its back.
    Atlases built before they existed have neither.
    """

    id: str
    position_mm: Vec3
    sigma_mm: float = Field(ge=0, description="1-sigma error of each coordinate")
    description: str = ""
    seen_from: Vec3 | None = Field(
        default=None,
        description="unit vector: the mean direction from the landmark to the cameras that saw it",
    )
    seen_within_deg: float | None = Field(
        default=None,
        ge=0,
        le=180,
        description="the widest angle between seen_from and the direction to one of those cameras",
    )
    moves_with: str | None = Field(
        default=None,
        description="the panel it is on, when that panel opens: then it is not where the atlas has it",
    )

    @model_validator(mode="after")
    def _seen_from_is_a_direction(self) -> Self:
        if (self.seen_from is None) != (self.seen_within_deg is None):
            raise ValueError("seen_from and seen_within_deg are set together")
        if self.seen_from is not None and abs(math.hypot(*self.seen_from) - 1.0) > 1e-6:
            raise ValueError(f"seen_from must be a unit vector, not {self.seen_from}")
        return self


class Target(Contract):
    """The hidden component: the point of it that is located, and the box it takes.

    position_mm is the point the localisation projects and the evaluation
    scores: the box's centre, or the centre of a tag on its face. The box sits
    around it: turned by rvec in the asset frame, its centre box_offset_mm from
    the point along the box's own axes, extent_mm along those axes. Both
    default to nothing, a box around the point along the asset's axes.
    """

    id: str
    position_mm: Vec3
    sigma_mm: float = Field(ge=0, description="1-sigma error of each coordinate of the point")
    extent_mm: Vec3 = Field(description="full size of the box, along its x, y and z")
    rvec: Vec3 = Field(
        default=(0.0, 0.0, 0.0), description="the box's axes in the asset frame, a Rodrigues vector"
    )
    box_offset_mm: Vec3 = Field(
        default=(0.0, 0.0, 0.0), description="the box's centre from the point, along the box's axes"
    )
    description: str = ""


class Panel(Contract):
    """A flat face of the asset that can stand between the camera and the target: a door, a side."""

    id: str
    corners_mm: list[Vec3] = Field(min_length=3, description="its outline, in order around it")
    description: str = ""


class Atlas(Contract):
    """What the system knows about one asset: its landmarks, the target, and what hides it."""

    asset_id: str
    version: str
    frame: str = Field(description="how the asset frame is defined, e.g. by which board")
    landmarks: list[Landmark]
    target: Target
    panels: list[Panel] = Field(
        default_factory=list, description="the faces the target can be behind; none: not known"
    )
    guide_view: Pose | None = Field(
        default=None,
        description="a recorded camera pose the target is well localised from: where guidance leads",
    )

    @model_validator(mode="after")
    def _unique_ids(self) -> Self:
        for kind, ids in (
            ("landmark", [landmark.id for landmark in self.landmarks]),
            ("panel", [panel.id for panel in self.panels]),
        ):
            duplicates = sorted({item for item in ids if ids.count(item) > 1})
            if duplicates:
                raise ValueError(f"duplicate {kind} ids: {duplicates}")
        panels = {panel.id for panel in self.panels}
        unknown = sorted(
            {landmark.moves_with for landmark in self.landmarks if landmark.moves_with} - panels
        )
        if unknown:
            raise ValueError(f"landmarks move with panels the atlas does not have: {unknown}")
        return self


def load_atlas(path: Path) -> Atlas:
    """Read an atlas from a JSON file."""
    return Atlas.model_validate_json(path.read_text(encoding="utf-8"))


class Clicks(Contract):
    """Points marked by hand on exported views, the input of the atlas builder.

    views maps an image file name to {point id: (x, y) pixel}. Pixels are in
    the exported image, which is in the sensor grid the intrinsics describe.

    points keeps the annotator's list in its order, including points not
    clicked yet, so a session reopened from this file shows the same list.
    Files written before it existed have none; their clicked ids are the list.
    """

    # A NaN pixel would be written to JSON as null and break the file for every reader.
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)

    camera_id: str
    points: list[str] = Field(
        default_factory=list,
        description="every point defined in the annotator, in its order, clicked or not",
    )
    views: dict[str, dict[str, Vec2]]

    @model_validator(mode="after")
    def _points_cover_the_clicks(self) -> Self:
        duplicates = sorted({point for point in self.points if self.points.count(point) > 1})
        if duplicates:
            raise ValueError(f"points listed more than once: {duplicates}")
        if self.points:
            clicked = {point for marked in self.views.values() for point in marked}
            unlisted = sorted(clicked - set(self.points))
            if unlisted:
                raise ValueError(f"clicked points missing from points: {unlisted}")
        return self


def load_clicks(path: Path) -> Clicks:
    """Read hand-marked points from a JSON file."""
    return Clicks.model_validate_json(path.read_text(encoding="utf-8"))


class LandmarkObservation(Contract):
    """Where one landmark appears in a frame."""

    landmark_id: str
    pixel: Vec2
    sigma_px: float = Field(gt=0, description="1-sigma error of each pixel coordinate")


class View(Contract):
    """The landmarks seen in one frame, taken in one capture mode."""

    view_id: str
    camera_id: str
    observations: list[LandmarkObservation]

    @model_validator(mode="after")
    def _one_observation_per_landmark(self) -> Self:
        ids = [observation.landmark_id for observation in self.observations]
        duplicates = sorted({landmark_id for landmark_id in ids if ids.count(landmark_id) > 1})
        if duplicates:
            raise ValueError(f"landmarks observed more than once: {duplicates}")
        return self


class Pose(Contract):
    """Asset frame to camera frame: x_camera = R(rvec) @ x_asset + tvec_mm."""

    rvec: Vec3
    tvec_mm: Vec3


class Quality(Contract):
    """How well the pose explains the observations."""

    observed: int = Field(description="landmarks seen that the atlas knows")
    inliers: int = Field(description="landmarks the RANSAC pose agrees with")
    inlier_ratio: float
    outlier_ids: list[str]
    rms_reprojection_px: float = Field(description="over the inliers")
    max_reprojection_px: float = Field(description="over the inliers")
    reprojection_px: dict[str, float] = Field(description="error of every observed landmark")
    image_coverage: float = Field(description="area of the inliers' convex hull / frame area")
    non_planarity: float = Field(
        description="smallest / largest spread of the inliers in 3D, 0 when they are coplanar"
    )


class ProjectedTarget(Contract):
    """The target where the estimated pose puts it in the frame."""

    centre_px: Vec2
    depth_mm: float = Field(description="distance of the centre along the optical axis")
    in_frame: bool
    outline_px: list[Vec2] = Field(description="convex hull of the projected extent box")
    radius_px: float = Field(description="radius of a circle with the outline's area")
    corners_px: list[Vec2] = Field(
        description="the 8 corners of the extent box, in the order of xray.BOX_SIGNS"
    )


class Guidance(Contract):
    """How far the camera is from the atlas's guide view, and how the asset looks from there."""

    outlines_px: list[list[Vec2]] = Field(description="the panels as the guide view sees them")
    alignment_px: float | None = Field(
        description="mean distance between the asset's points as this pose and the guide view "
        "put them; None without a pose"
    )
    progress: float | None = Field(description="0 far from the guide view, 1 on it")


class TargetSighting(Contract):
    """The target's tag in sight: the panel is open, and the prediction can be held against it."""

    tag_px: list[Vec2] = Field(description="its corners, in OpenCV's order")
    centre_px: Vec2
    error_px: float | None = Field(description="from the projected target point; None without one")
    inside_95: bool | None


class ProjectedPanel(Contract):
    """The panel the line of sight to the target crosses: the target is behind it."""

    panel_id: str
    outline_px: list[Vec2]


class Ellipse(Contract):
    """A region around the target centre that holds it with the stated confidence."""

    semi_major_px: float
    semi_minor_px: float
    angle_deg: float = Field(description="major axis, from the image x axis towards y, 0 to 180")


class UncertaintyRegion(Contract):
    """Where the target centre lands when every input varies within its sigma."""

    confidence: float
    covariance_px: tuple[Vec2, Vec2]
    ellipse: Ellipse
    pose_only: Ellipse = Field(
        description="the target held at its atlas position: the part a new viewpoint can shrink"
    )
    samples: int
    failed_samples: int
    seed: int


class Failure(StrEnum):
    """Why a localisation could not be computed at all. No threshold is involved."""

    TOO_FEW_CORRESPONDENCES = "too_few_correspondences"
    DEGENERATE_GEOMETRY = "degenerate_geometry"
    PNP_FAILED = "pnp_failed"
    TARGET_BEHIND_CAMERA = "target_behind_camera"
    UNSTABLE_POSE = "unstable_pose"


class Localisation(Contract):
    """Everything the geometry says about one view.

    After a failure, the fields that could not be computed are None.
    """

    view_id: str
    failure: Failure | None = None
    quality: Quality | None = None
    pose: Pose | None = None
    target: ProjectedTarget | None = None
    uncertainty: UncertaintyRegion | None = None
    occluder: ProjectedPanel | None = Field(
        default=None, description="the atlas panel between the camera and the target, if any"
    )


class Action(StrEnum):
    """What the operator does next: take the result, or move the camera and look again.

    A move is the camera's, as the operator holds it: MOVE_LEFT brings what
    lies beyond the left edge of the frame into view.
    """

    ACCEPT = "ACCEPT"
    MOVE_LEFT = "MOVE_LEFT"
    MOVE_RIGHT = "MOVE_RIGHT"
    MOVE_CLOSER = "MOVE_CLOSER"
    MOVE_BACK = "MOVE_BACK"
    MOVE_UP = "MOVE_UP"
    MOVE_DOWN = "MOVE_DOWN"


class Check(Contract):
    """One measurement of a localisation held against one limit of the policy."""

    name: str
    value: float | None = Field(description="the measurement; None when it cannot be computed")
    limit: float = Field(description="from the policy")
    op: Literal[">=", "<="] = Field(description="passing means value op limit")
    passed: bool


class Policy(Contract):
    """The calibrated opinions: every limit a decision holds a measurement against.

    They are judgements of how much error a result may carry and still be
    shown as reliable, so they sit here, in one place, and not in the geometry.
    """

    min_landmarks: int = Field(default=4, description="PnP needs four: pose.MIN_CORRESPONDENCES")
    min_inliers: int = 6
    min_inlier_ratio: float = 0.75
    max_rms_reprojection_px: float = 3.0
    min_image_coverage: float = 0.05
    max_failed_sample_ratio: float = Field(
        default=0.05, description="share of Monte Carlo samples without a usable pose"
    )
    max_region_ratio: float = Field(
        default=0.5, description="95% ellipse semi-major axis / projected target radius"
    )


class Decision(Contract):
    """Whether a localisation is shown as reliable, and the move that should improve it."""

    reliable: bool
    action: Action
    reasons: list[str] = Field(description="one short fact per failed check, a failure first")
    move_reason: str = Field(description="the fact the move follows from; empty for ACCEPT")
    checks: list[Check]
    policy: Policy
