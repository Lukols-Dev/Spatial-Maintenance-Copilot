"""One evaluation run over a frozen dataset: every measure of the evaluation plan.

The test sets' viewpoints are the scored views: the target hidden, its truth
clicked in the shot from the same spot with the target in sight. Board checks
also cover the build set, marked in-sample. Everything random is seeded, so a
run on the same dataset, code and platform gives the same numbers.
"""

import math
import random
from collections import Counter
from collections.abc import Callable, Sequence
from itertools import combinations

import numpy as np
from smc_agent.contracts import TraceEvent
from smc_agent.model import ChatModel, NoModel
from smc_core.policy import DEFAULT_POLICY
from smc_core.viewpoints import observed_view, poses_from_clicks

from smc_eval import sessions
from smc_eval.dataset import Dataset
from smc_eval.faults import FAULTS
from smc_eval.metrics import chi2_2dof, distance, pose_gap, project, rate, spread
from smc_eval.perception import SAMPLES, SEED, FrozenPerception, locate
from smc_eval.results import (
    BoardCheck,
    BoardSummary,
    Coverage,
    DecisionQuality,
    Environment,
    FaultResult,
    LocalisationSummary,
    MonteCarloCheck,
    Repeat,
    RepeatSummary,
    Results,
    SessionRun,
    StartsFrom,
    StrategySummary,
    UncertaintyCalibration,
    ViewResult,
)
from smc_eval.scoring import score

CONFIDENCES = (0.5, 0.8, 0.95, 0.99)
OTHER_SEEDS = (1, 2, 3, 4)
NO_MODEL = "none"


def evaluate(
    dataset: Dataset,
    *,
    evaluated_at: str,
    environment: Environment,
    samples: int = SAMPLES,
    seed: int = SEED,
    model: ChatModel | None = None,
    model_name: str = NO_MODEL,
) -> tuple[Results, dict[str, list[TraceEvent]]]:
    """Every measure, and the agent's trace of each session by its file in the results folder."""
    perceptions = {
        view_set.name: FrozenPerception(dataset, view_set.name, samples, seed)
        for view_set in dataset.with_role("test")
    }
    views = [
        view_result(perception, name, view)
        for name, perception in perceptions.items()
        for view in perception.viewpoints()
    ]
    runs, traces = _sessions(dataset, perceptions, model, seed)
    agent_runs = [run for run in runs if run.strategy == "agent"]
    steps = [
        step
        for run in agent_runs
        if (step := sessions.next_view(perceptions[run.view_set], run.view_set, run)) is not None
    ]
    repeats = _repeats(perceptions)
    board_checks = _board_checks(dataset)

    results = Results(
        dataset=dataset.name,
        manifest_sha256=dataset.manifest_sha256,
        asset_id=dataset.atlas.asset_id,
        atlas_version=dataset.atlas.version,
        test_sets=list(perceptions),
        samples=samples,
        seed=seed,
        sigma_px=dataset.sigma_px,
        model=model_name,
        policy=DEFAULT_POLICY,
        evaluated_at=evaluated_at,
        environment=environment,
        views=views,
        localisation=_localisation(views),
        uncertainty=_calibration(views),
        decisions=_decisions(views),
        repeats=repeats,
        repeat_summary=RepeatSummary(
            pairs=len(repeats),
            translation_mm=spread([repeat.translation_mm for repeat in repeats]),
            rotation_deg=spread([repeat.rotation_deg for repeat in repeats]),
            target_px=spread([repeat.target_px for repeat in repeats]),
        ),
        board_checks=board_checks,
        board_summary=[
            _board_summary(
                [check for check in board_checks if check.in_sample == in_sample], in_sample
            )
            for in_sample in (False, True)
        ],
        monte_carlo=_monte_carlo(dataset, perceptions, samples, seed),
        strategies=_strategies(runs, views),
        sessions=[run for run in runs if run.strategy != "random"],
        next_views=steps,
        improvement=sessions.improvement(steps),
        faults=_faults(dataset, perceptions, samples, seed),
    )
    return results, traces


# ---- the viewpoints ----------------------------------------------------------------------


def view_result(perception: FrozenPerception, view_set: str, view: str) -> ViewResult:
    located = perception.localise(view)
    truth = perception.truth(view)
    scored = score(located, truth)
    localisation = located.localisation
    quality, target, region = localisation.quality, localisation.target, localisation.uncertainty
    return ViewResult(
        view_set=view_set,
        view=view,
        truth_view=None if truth is None else truth.view,
        landmarks=len(perception.observed(view).observations),
        failure=localisation.failure,
        action=located.decision.action,
        reliable=located.decision.reliable,
        inliers=None if quality is None else quality.inliers,
        inlier_ratio=None if quality is None else quality.inlier_ratio,
        rms_reprojection_px=None if quality is None else quality.rms_reprojection_px,
        target_radius_px=None if target is None else target.radius_px,
        error_px=scored.error_px,
        mahalanobis2=scored.mahalanobis2,
        inside_95=scored.inside_95,
        semi_major_px=None if region is None else region.ellipse.semi_major_px,
        semi_minor_px=None if region is None else region.ellipse.semi_minor_px,
        pose_only_semi_major_px=None if region is None else region.pose_only.semi_major_px,
        outcome=scored.outcome,
    )


def _scored(views: Sequence[ViewResult]) -> list[ViewResult]:
    """The viewpoints with a truth and a 95% region: those the error and coverage are read on."""
    return [view for view in views if view.inside_95 is not None]


def _localisation(views: Sequence[ViewResult]) -> LocalisationSummary:
    scored = _scored(views)
    accepted = [view for view in scored if view.reliable]
    posed = [view for view in views if view.rms_reprojection_px is not None]
    return LocalisationSummary(
        viewpoints=len(views),
        with_truth=sum(view.truth_view is not None for view in views),
        localised=len(scored),
        error_px=spread([view.error_px for view in scored if view.error_px is not None]),
        error_px_accepted=spread([view.error_px for view in accepted if view.error_px is not None]),
        error_over_radius=spread(
            [
                view.error_px / view.target_radius_px
                for view in scored
                if view.error_px is not None and view.target_radius_px
            ]
        ),
        inside_95=rate(sum(bool(view.inside_95) for view in scored), len(scored)),
        inside_95_accepted=rate(sum(bool(view.inside_95) for view in accepted), len(accepted)),
        rms_reprojection_px=spread(
            [view.rms_reprojection_px for view in posed if view.rms_reprojection_px is not None]
        ),
        inlier_ratio=spread([view.inlier_ratio for view in posed if view.inlier_ratio is not None]),
        semi_major_px=spread(
            [view.semi_major_px for view in scored if view.semi_major_px is not None]
        ),
        actions=dict(sorted(Counter(view.action.value for view in views).items())),
    )


def _calibration(views: Sequence[ViewResult]) -> UncertaintyCalibration:
    distances = [view.mahalanobis2 for view in _scored(views) if view.mahalanobis2 is not None]
    median = float(np.median(distances)) if distances else None
    return UncertaintyCalibration(
        levels=[
            Coverage(
                confidence=confidence,
                radius2=chi2_2dof(confidence),
                observed=rate(
                    sum(value <= chi2_2dof(confidence) for value in distances), len(distances)
                ),
            )
            for confidence in CONFIDENCES
        ],
        median_mahalanobis2=median,
        expected_median_mahalanobis2=chi2_2dof(0.5),
        scale=None if median is None else math.sqrt(median / chi2_2dof(0.5)),
    )


def _decisions(views: Sequence[ViewResult]) -> DecisionQuality:
    with_truth = [view for view in views if view.truth_view is not None]
    count = Counter(
        (view.reliable, view.inside_95) for view in with_truth if view.inside_95 is not None
    )
    failed = sum(view.inside_95 is None for view in with_truth)
    accepted = count[True, True] + count[True, False]
    held = count[False, True] + count[False, False]
    return DecisionQuality(
        accepted_inside=count[True, True],
        accepted_outside=count[True, False],
        held_inside=count[False, True],
        held_outside=count[False, False],
        failed=failed,
        false_accept=rate(count[True, False], accepted),
        held_but_inside=rate(count[False, True], held),
    )


# ---- pose stability ------------------------------------------------------------------------


def _repeats(perceptions: dict[str, FrozenPerception]) -> list[Repeat]:
    """Every two viewpoints taken from the same spot, both localised."""
    repeats = []
    for name, perception in perceptions.items():
        by_spot: dict[str, list[str]] = {}
        for view in perception.viewpoints():
            by_spot.setdefault(view.split("_", 1)[0], []).append(view)
        for spot in sorted(by_spot):
            for first, second in combinations(sorted(by_spot[spot]), 2):
                a = perception.localise(first).localisation
                b = perception.localise(second).localisation
                if a.pose is None or b.pose is None or a.target is None or b.target is None:
                    continue
                translation, rotation = pose_gap(a.pose, b.pose)
                repeats.append(
                    Repeat(
                        view_set=name,
                        first=first,
                        second=second,
                        translation_mm=translation,
                        rotation_deg=rotation,
                        target_px=distance(a.target.centre_px, b.target.centre_px),
                    )
                )
    return repeats


def _board_checks(dataset: Dataset) -> list[BoardCheck]:
    """Every frame with both a board pose and a landmark pose, in every set."""
    checks = []
    atlas, intrinsics = dataset.atlas, dataset.intrinsics
    for view_set in dataset.sets.values():
        boarded = sorted(set(view_set.board_poses) & set(view_set.clicks.views))
        landmark_poses = poses_from_clicks(boarded, view_set.clicks, atlas, intrinsics)
        for view in boarded:
            pose = landmark_poses.get(view)
            if pose is None:
                continue
            board = view_set.board_poses[view]
            translation, rotation = pose_gap(pose, board.pose)
            checks.append(
                BoardCheck(
                    view_set=view_set.name,
                    view=view,
                    in_sample=view_set.role == "build",
                    landmarks=len(
                        observed_view(view, view_set.clicks, atlas, dataset.sigma_px).observations
                    ),
                    board_corners=board.corners,
                    translation_mm=translation,
                    rotation_deg=rotation,
                    target_px=distance(
                        project(atlas.target.position_mm, pose, intrinsics),
                        project(atlas.target.position_mm, board.pose, intrinsics),
                    ),
                )
            )
    return checks


def _board_summary(checks: Sequence[BoardCheck], in_sample: bool) -> BoardSummary:
    return BoardSummary(
        in_sample=in_sample,
        frames=len(checks),
        translation_mm=spread([check.translation_mm for check in checks]),
        rotation_deg=spread([check.rotation_deg for check in checks]),
        target_px=spread([check.target_px for check in checks]),
    )


def _monte_carlo(
    dataset: Dataset, perceptions: dict[str, FrozenPerception], samples: int, seed: int
) -> MonteCarloCheck:
    relative_spreads = []
    inside_changes = decision_changes = views = 0
    seeds = [seed, *(other for other in OTHER_SEEDS if other != seed)]
    for perception in perceptions.values():
        for view in perception.viewpoints():
            first = perception.localise(view)
            if first.localisation.uncertainty is None:
                continue
            views += 1
            truth = perception.truth(view)
            located = [first] + [
                locate(perception.observed(view), dataset.atlas, dataset.intrinsics, samples, other)
                for other in seeds[1:]
            ]
            semi_majors = [
                item.localisation.uncertainty.ellipse.semi_major_px
                for item in located
                if item.localisation.uncertainty is not None
            ]
            relative_spreads.append(
                (max(semi_majors) - min(semi_majors)) / float(np.median(semi_majors))
            )
            inside_changes += len({score(item, truth).inside_95 for item in located}) > 1
            decision_changes += len({item.decision.action for item in located}) > 1
    return MonteCarloCheck(
        seeds=seeds,
        views=views,
        semi_major_relative_spread=spread(relative_spreads),
        inside_95_changes=inside_changes,
        decision_changes=decision_changes,
    )


# ---- the sessions --------------------------------------------------------------------------


def _sessions(
    dataset: Dataset,
    perceptions: dict[str, FrozenPerception],
    model: ChatModel | None,
    seed: int,
) -> tuple[list[SessionRun], dict[str, list[TraceEvent]]]:
    copilot = sessions.copilot_for(
        perceptions, model or NoModel("the evaluation runs the agent without a model")
    )
    rng = random.Random(seed)
    runs: list[SessionRun] = []
    traces: dict[str, list[TraceEvent]] = {}
    for name, perception in perceptions.items():
        for start in perception.viewpoints():
            runs.append(sessions.single_view(perception, name, start))
            runs.append(sessions.policy_only(perception, name, start))
            run, trace = sessions.agent_session(
                copilot, perception, dataset.atlas.asset_id, name, start
            )
            runs.append(run)
            traces[sessions.trace_file(name, start)] = trace
            runs.extend(
                sessions.random_walk(perception, name, start, rng)
                for _ in range(sessions.RANDOM_RUNS)
            )
    return runs, traces


def _strategies(runs: Sequence[SessionRun], views: Sequence[ViewResult]) -> list[StrategySummary]:
    """Every strategy from every viewpoint, then apart: the starts that localise and those that do not."""
    localised = {(view.view_set, view.view) for view in views if view.outcome != "failed"}
    groups: dict[StartsFrom, Callable[[SessionRun], bool]] = {
        "every viewpoint": lambda run: True,
        "localised": lambda run: (run.view_set, run.start) in localised,
        "not localised": lambda run: (run.view_set, run.start) not in localised,
    }
    return [
        sessions.summarise(
            strategy,
            [run for run in runs if run.strategy == strategy and belongs(run)],
            sessions.RANDOM_RUNS if strategy == "random" else 1,
            starts_from,
        )
        for starts_from, belongs in groups.items()
        for strategy in sessions.DESCRIPTIONS
    ]


# ---- the faults ----------------------------------------------------------------------------


def _faults(
    dataset: Dataset, perceptions: dict[str, FrozenPerception], samples: int, seed: int
) -> list[FaultResult]:
    """Each fault over every viewpoint that localises and has a truth."""
    results = []
    for fault in FAULTS:
        rng = np.random.default_rng(seed)
        outcomes: Counter[str] = Counter()
        overlay_outside = 0
        for perception in perceptions.values():
            for view in perception.viewpoints():
                truth = perception.truth(view)
                if truth is None or perception.localise(view).localisation.uncertainty is None:
                    continue
                for faulted in fault.inject(perception.observed(view), dataset.sigma_px, rng):
                    located = locate(faulted, dataset.atlas, dataset.intrinsics, samples, seed)
                    scored = score(located, truth)
                    outcomes[scored.outcome] += 1
                    overlay_outside += scored.outcome != "failed" and scored.inside_95 is False
        trials = sum(outcomes.values())
        results.append(
            FaultResult(
                fault=fault.name,
                description=fault.description,
                trials=trials,
                failed=outcomes["failed"],
                held=outcomes["held"],
                accepted_inside=outcomes["accepted_inside"],
                accepted_outside=outcomes["accepted_outside"],
                unsafe=rate(outcomes["accepted_outside"], trials),
                overlay_outside=overlay_outside,
            )
        )
    return results
