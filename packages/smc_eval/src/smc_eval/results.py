"""What an evaluation run writes to results.json, section by section.

Every section answers one measure of the evaluation plan: localisation error,
reprojection and inliers, pose stability, uncertainty calibration, decision
quality, the agent's improvement over a single or a random view, task success,
and the faults the system must handle. The header holds what makes a run
reproducible: the dataset's manifest hash, the seeds, the versions and the
commit.
"""

from typing import Literal

from pydantic import Field
from smc_core.contracts import Action, Contract, Failure, Policy

from smc_eval.metrics import Rate, Spread

# What a located view comes to, held against the truth.
#   failed: no target projection at all; held: the policy asks for another view;
#   accepted_inside / accepted_outside: the policy accepts, the truth in or out
#   of the 95% region; accepted_unscored: accepted where no truth was recorded.
Outcome = Literal["failed", "held", "accepted_inside", "accepted_outside", "accepted_unscored"]


class Environment(Contract):
    git_commit: str | None
    git_dirty: bool | None
    python: str
    numpy: str
    opencv: str
    langgraph: str
    machine: str


class ViewResult(Contract):
    """One viewpoint of a test set: the target hidden, localised from its clicked landmarks."""

    view_set: str
    view: str
    truth_view: str | None = Field(
        description="the shot from the same spot with the target in sight"
    )
    landmarks: int = Field(description="landmarks of the atlas clicked")
    failure: Failure | None
    action: Action
    reliable: bool
    inliers: int | None
    inlier_ratio: float | None
    rms_reprojection_px: float | None
    target_radius_px: float | None
    error_px: float | None = Field(description="projected target centre to the clicked truth")
    mahalanobis2: float | None = Field(description="the same, under the region's covariance")
    inside_95: bool | None
    semi_major_px: float | None = Field(description="of the 95% region")
    semi_minor_px: float | None
    pose_only_semi_major_px: float | None = Field(description="the part a better view can shrink")
    outcome: Outcome


class LocalisationSummary(Contract):
    viewpoints: int
    with_truth: int
    localised: int = Field(description="with a truth and a 95% region")
    error_px: Spread
    error_px_accepted: Spread
    error_over_radius: Spread = Field(description="error / radius of the projected target")
    inside_95: Rate
    inside_95_accepted: Rate
    rms_reprojection_px: Spread = Field(description="every viewpoint with a pose")
    inlier_ratio: Spread
    semi_major_px: Spread
    actions: dict[str, int]


class Coverage(Contract):
    confidence: float
    radius2: float = Field(description="the squared Mahalanobis radius of that confidence")
    observed: Rate


class UncertaintyCalibration(Contract):
    """Whether the reported region holds the truth as often as it says it does."""

    levels: list[Coverage]
    median_mahalanobis2: float | None
    expected_median_mahalanobis2: float
    scale: float | None = Field(
        description="sqrt(median / expected): the median error in units of the region's spread; "
        "below 1 the region is larger than the errors need"
    )


class DecisionQuality(Contract):
    """The policy's verdicts on the test viewpoints with a truth, against that truth."""

    accepted_inside: int
    accepted_outside: int
    held_inside: int
    held_outside: int
    failed: int
    false_accept: Rate = Field(description="accepted with the truth outside, of the accepted")
    held_but_inside: Rate = Field(description="asked to move though the truth was inside")


class Repeat(Contract):
    """Two shots from the same spot, B1_close and B1_1_close: how far the results drift."""

    view_set: str
    first: str
    second: str
    translation_mm: float
    rotation_deg: float
    target_px: float


class RepeatSummary(Contract):
    pairs: int
    translation_mm: Spread
    rotation_deg: Spread
    target_px: Spread


class BoardCheck(Contract):
    """The pose from the landmarks against the pose from the rig board in the same frame."""

    view_set: str
    view: str
    in_sample: bool = Field(description="the atlas was built from this frame")
    landmarks: int
    board_corners: int
    translation_mm: float
    rotation_deg: float
    target_px: float = Field(description="the target projected through each pose")


class BoardSummary(Contract):
    in_sample: bool
    frames: int
    translation_mm: Spread
    rotation_deg: Spread
    target_px: Spread


class MonteCarloCheck(Contract):
    """The same viewpoints localised with other seeds: what the Monte Carlo region owes to chance."""

    seeds: list[int]
    views: int
    semi_major_relative_spread: Spread = Field(description="(max - min) / median, per view")
    inside_95_changes: int = Field(description="views whose verdict on the truth changes")
    decision_changes: int


class SessionRun(Contract):
    strategy: str
    view_set: str
    start: str
    views: list[str]
    outcome: Literal["accepted", "refused"]
    final_view: str | None
    error_px: float | None
    inside_95: bool | None
    success: bool | None = Field(description="accepted with the truth inside; None when unscored")
    guards: int = Field(default=0, description="model outputs the guards corrected")
    fallbacks: int = Field(default=0, description="turns that took the policy's own words")
    trace: str | None = Field(default=None, description="the agent's trace, in the results folder")


StartsFrom = Literal["every viewpoint", "localised", "not localised"]


class StrategySummary(Contract):
    strategy: str
    description: str
    starts_from: StartsFrom = Field(description="localised: the first view gives a 95% region")
    starts: int
    runs_per_start: int
    success: Rate = Field(description="accepted with the truth inside, of the scored runs")
    false_accept: Rate = Field(description="accepted with the truth outside, of the scored runs")
    refused: Rate = Field(description="ended with no result shown, of all runs")
    unscored: int = Field(description="accepted at a viewpoint with no recorded truth")
    views: Spread = Field(description="viewpoints taken per run")
    views_to_success: Spread = Field(description="viewpoints taken per successful run")


class NextView(Contract):
    """One unreliable start: its result, the agent's next view, and a random next view."""

    view_set: str
    start: str
    action: Action
    agent_view: str | None
    error_before_px: float
    error_agent_px: float | None
    error_random_px: float | None = Field(description="mean over every other viewpoint")
    semi_major_before_px: float
    semi_major_agent_px: float | None
    semi_major_random_px: float | None
    agent_reliable: bool | None
    random_reliable: float | None = Field(description="share of the other viewpoints accepted")


class Improvement(Contract):
    """Does the view the agent asks for beat the first view, and a random one?"""

    starts: int
    with_agent_view: int
    error_before_px: Spread
    error_agent_px: Spread
    error_random_px: Spread
    semi_major_before_px: Spread
    semi_major_agent_px: Spread
    semi_major_random_px: Spread
    agent_lower_error: Rate
    agent_smaller_region: Rate
    agent_reliable: Rate
    random_reliable: float | None


class FaultResult(Contract):
    fault: str
    description: str
    trials: int
    failed: int
    held: int
    accepted_inside: int
    accepted_outside: int
    unsafe: Rate = Field(
        description="accepted with the truth outside: an overlay in the wrong place"
    )
    overlay_outside: int = Field(
        description="a target drawn with the truth outside its region, accepted or not: "
        "what a system without the policy would show"
    )


class Results(Contract):
    dataset: str
    manifest_sha256: str
    asset_id: str
    atlas_version: str
    test_sets: list[str]
    samples: int
    seed: int
    sigma_px: float
    model: str = Field(description="the agent's model in the sessions; none: the policy's words")
    policy: Policy
    evaluated_at: str
    environment: Environment

    views: list[ViewResult]
    localisation: LocalisationSummary
    uncertainty: UncertaintyCalibration
    decisions: DecisionQuality
    repeats: list[Repeat]
    repeat_summary: RepeatSummary
    board_checks: list[BoardCheck]
    board_summary: list[BoardSummary]
    monte_carlo: MonteCarloCheck
    strategies: list[StrategySummary]
    sessions: list[SessionRun]
    next_views: list[NextView]
    improvement: Improvement
    faults: list[FaultResult]
