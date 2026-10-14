"""results.json as a Markdown report: the tables the technical report quotes."""

from collections.abc import Sequence

from smc_eval.metrics import Rate, Spread
from smc_eval.results import Results

NONE = "-"


def number(value: float | None, digits: int = 1) -> str:
    return NONE if value is None else f"{value:.{digits}f}"


def share(value: Rate) -> str:
    """k/n (rate, Wilson 95% interval)."""
    if value.n == 0 or value.rate is None or value.low is None or value.high is None:
        return f"{value.k}/{value.n}"
    return (
        f"{value.k}/{value.n} ({value.rate:.0%}, CI {value.low * 100:.0f}-{value.high * 100:.0f}%)"
    )


def spread_cells(value: Spread, digits: int = 1) -> list[str]:
    return [
        str(value.n),
        number(value.median, digits),
        number(value.p90, digits),
        number(value.max, digits),
    ]


def table(header: Sequence[str], rows: Sequence[Sequence[str]]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    return [*lines, ""]


def render(results: Results) -> str:
    environment = results.environment
    localisation = results.localisation
    lines = [
        f"# Evaluation on {results.dataset}",
        "",
        f"Atlas {results.asset_id} v{results.atlas_version}, scored on the held-out view "
        f"{'set' if len(results.test_sets) == 1 else 'sets'} {', '.join(results.test_sets)}. Every viewpoint shows the target hidden; its truth is "
        "the target clicked in the shot from the same spot with the target in sight.",
        "",
        *table(
            ["", ""],
            [
                ["dataset manifest", f"`{results.manifest_sha256[:16]}`"],
                ["Monte Carlo", f"{results.samples} samples, seed {results.seed}"],
                ["click sigma", f"{results.sigma_px:g} px"],
                ["agent's model", results.model],
                [
                    "code",
                    f"`{environment.git_commit or 'unknown'}`"
                    + (" with uncommitted changes" if environment.git_dirty else ""),
                ],
                [
                    "versions",
                    f"Python {environment.python}, NumPy {environment.numpy}, "
                    f"OpenCV {environment.opencv}, LangGraph {environment.langgraph}, "
                    f"{environment.machine}",
                ],
                ["run", results.evaluated_at],
            ],
        ),
        "## Localisation",
        "",
        f"{localisation.viewpoints} viewpoints, {localisation.with_truth} with a truth, "
        f"{localisation.localised} of those localised with a 95% region.",
        "",
        *table(
            ["measure", "n", "median", "p90", "max"],
            [
                ["target error, px", *spread_cells(localisation.error_px)],
                ["target error, accepted, px", *spread_cells(localisation.error_px_accepted)],
                ["error / target radius", *spread_cells(localisation.error_over_radius, 2)],
                ["RMS reprojection, px", *spread_cells(localisation.rms_reprojection_px, 2)],
                ["RANSAC inlier ratio", *spread_cells(localisation.inlier_ratio, 2)],
                ["95% region, semi-major, px", *spread_cells(localisation.semi_major_px)],
            ],
        ),
        f"Truth inside the 95% region: {share(localisation.inside_95)}; "
        f"of the accepted results: {share(localisation.inside_95_accepted)}.",
        "",
        "Decisions: "
        + ", ".join(f"{action} {count}" for action, count in localisation.actions.items())
        + ".",
        "",
        *table(
            [
                "viewpoint",
                "truth",
                "landmarks",
                "decision",
                "inliers",
                "RMS px",
                "error px",
                "target radius px",
                "inside 95%",
                "semi-major px",
            ],
            [
                [
                    view.view,
                    view.truth_view or NONE,
                    str(view.landmarks),
                    view.failure.value if view.failure else view.action.value,
                    NONE if view.inliers is None else str(view.inliers),
                    number(view.rms_reprojection_px, 2),
                    number(view.error_px),
                    number(view.target_radius_px),
                    NONE if view.inside_95 is None else ("yes" if view.inside_95 else "no"),
                    number(view.semi_major_px),
                ]
                for view in results.views
            ],
        ),
    ]

    uncertainty = results.uncertainty
    decisions = results.decisions
    lines += [
        "## Uncertainty calibration",
        "",
        "How often the truth falls inside the region at each confidence, read from the "
        "squared Mahalanobis distance of the truth under the region's covariance.",
        "",
        *table(
            ["confidence", "radius²", "truth inside"],
            [
                [f"{level.confidence:.0%}", number(level.radius2, 2), share(level.observed)]
                for level in uncertainty.levels
            ],
        ),
        f"Median squared distance {number(uncertainty.median_mahalanobis2, 2)}; "
        f"a calibrated region gives {number(uncertainty.expected_median_mahalanobis2, 2)}. "
        + _calibration_verdict(uncertainty.scale),
        "",
        "## Decisions against the truth",
        "",
        *table(
            ["", "truth inside", "truth outside"],
            [
                ["accepted", str(decisions.accepted_inside), str(decisions.accepted_outside)],
                ["asked to move", str(decisions.held_inside), str(decisions.held_outside)],
            ],
        ),
        f"No localisation: {decisions.failed}. False accepts: {share(decisions.false_accept)}. "
        f"Asked to move though the truth was inside: {share(decisions.held_but_inside)}.",
        "",
    ]

    repeat = results.repeat_summary
    lines += [
        "## Pose stability",
        "",
        f"Two shots from the same spot, {repeat.pairs} pairs both localised. Each shot was "
        "taken by hand, so a difference is the pose's error and the camera's own movement "
        "together.",
        "",
        *table(
            ["between the shots", "n", "median", "p90", "max"],
            [
                ["camera centre, mm", *spread_cells(repeat.translation_mm)],
                ["rotation, deg", *spread_cells(repeat.rotation_deg, 2)],
                ["target, px", *spread_cells(repeat.target_px)],
            ],
        ),
        *table(
            ["first", "second", "camera centre mm", "rotation deg", "target px"],
            [
                [
                    pair.first,
                    pair.second,
                    number(pair.translation_mm),
                    number(pair.rotation_deg, 2),
                    number(pair.target_px),
                ]
                for pair in results.repeats
            ],
        ),
        "The pose from the landmarks against the pose from the rig board in the same frame. "
        "In-sample frames are those the atlas was built from.",
        "",
        *table(
            [
                "frames",
                "n",
                "centre mm median",
                "max",
                "rotation deg median",
                "max",
                "target px median",
                "max",
            ],
            [
                [
                    "in-sample" if summary.in_sample else "held out",
                    str(summary.frames),
                    number(summary.translation_mm.median),
                    number(summary.translation_mm.max),
                    number(summary.rotation_deg.median, 2),
                    number(summary.rotation_deg.max, 2),
                    number(summary.target_px.median),
                    number(summary.target_px.max),
                ]
                for summary in results.board_summary
            ],
        ),
    ]
    held_out = [check for check in results.board_checks if not check.in_sample]
    if held_out:
        lines += table(
            [
                "held-out frame",
                "landmarks",
                "board corners",
                "centre mm",
                "rotation deg",
                "target px",
            ],
            [
                [
                    check.view,
                    str(check.landmarks),
                    str(check.board_corners),
                    number(check.translation_mm),
                    number(check.rotation_deg, 2),
                    number(check.target_px),
                ]
                for check in held_out
            ],
        )
    monte_carlo = results.monte_carlo
    lines += [
        f"Monte Carlo seeds {', '.join(map(str, monte_carlo.seeds))} over {monte_carlo.views} "
        f"viewpoints: the region's semi-major axis varies by a median "
        f"{number(_percent(monte_carlo.semi_major_relative_spread.median))}% "
        f"(max {number(_percent(monte_carlo.semi_major_relative_spread.max))}%); "
        f"the verdict on the truth changes in {monte_carlo.inside_95_changes}, "
        f"the decision in {monte_carlo.decision_changes}.",
        "",
        "## Task success",
        "",
        "Sessions from every viewpoint, the operator simulated, at most "
        f"{max((s.views.max or 0) for s in results.strategies):.0f} viewpoints each. Success: a "
        "result accepted with the truth inside its region. False accept: accepted with the truth "
        "outside. Refused: no result shown. A start is localised when its first view gives a 95% "
        "region.",
        "",
        *table(
            ["strategy", ""],
            [
                [strategy.strategy, strategy.description]
                for strategy in results.strategies
                if strategy.starts_from == "every viewpoint"
            ],
        ),
    ]
    for starts_from in ("every viewpoint", "localised", "not localised"):
        group = [s for s in results.strategies if s.starts_from == starts_from]
        lines += [
            f"From {starts_from if starts_from == 'every viewpoint' else f'the {starts_from} starts'}:",
            "",
            *table(
                [
                    "strategy",
                    "runs",
                    "success",
                    "false accept",
                    "refused",
                    "views to success, mean",
                ],
                [
                    [
                        strategy.strategy,
                        f"{strategy.starts} x {strategy.runs_per_start}",
                        _rate_cell(strategy.success, strategy.runs_per_start),
                        _rate_cell(strategy.false_accept, strategy.runs_per_start),
                        _rate_cell(strategy.refused, strategy.runs_per_start),
                        number(strategy.views_to_success.mean),
                    ]
                    for strategy in group
                ],
            ),
        ]
    agent_runs = [run for run in results.sessions if run.strategy == "agent"]
    lines += [
        "Random runs share their start, so no interval is given for them.",
        "",
        f"The agent's model: {results.model}. Across its {len(agent_runs)} sessions the guards "
        f"corrected {sum(run.guards for run in agent_runs)} of its outputs, and "
        f"{sum(run.fallbacks for run in agent_runs)} turns took the policy's own words.",
        "",
    ]

    improvement = results.improvement
    lines += [
        "## The agent's next view",
        "",
        f"{improvement.starts} starts the policy asked to move from, with a truth; the agent "
        f"named a viewpoint for {improvement.with_agent_view}. The random column is the mean "
        "over every other viewpoint.",
        "",
        *table(
            [
                "start",
                "move",
                "error px",
                "semi-major px",
                "agent's view",
                "error px",
                "semi-major px",
                "accepted",
                "random error px",
                "random semi-major px",
                "random accepted",
            ],
            [
                [
                    step.start,
                    step.action.value,
                    number(step.error_before_px),
                    number(step.semi_major_before_px),
                    step.agent_view or NONE,
                    number(step.error_agent_px),
                    number(step.semi_major_agent_px),
                    NONE
                    if step.agent_reliable is None
                    else ("yes" if step.agent_reliable else "no"),
                    number(step.error_random_px),
                    number(step.semi_major_random_px),
                    NONE if step.random_reliable is None else f"{step.random_reliable:.0%}",
                ]
                for step in results.next_views
            ],
        ),
        f"The agent's view lowers the error in {share(improvement.agent_lower_error)}, shrinks "
        f"the region in {share(improvement.agent_smaller_region)} and is accepted in "
        f"{share(improvement.agent_reliable)}; a random view is accepted in "
        f"{NONE if improvement.random_reliable is None else f'{improvement.random_reliable:.0%}'}.",
        "",
        "## Injected faults",
        "",
        "Each fault over every viewpoint that localises and has a truth. Unsafe: accepted with the "
        "truth outside the region, an overlay in the wrong place.",
        "",
        "The last column counts the trials whose target was drawn with the truth outside its "
        "region, accepted or not: what a system showing every overlay, without the policy, "
        "would have put in the wrong place.",
        "",
        *table(
            [
                "fault",
                "",
                "trials",
                "no result",
                "asked to move",
                "accepted, inside",
                "unsafe",
                "drawn, truth outside",
            ],
            [
                [
                    fault.fault,
                    fault.description,
                    str(fault.trials),
                    str(fault.failed),
                    str(fault.held),
                    str(fault.accepted_inside),
                    share(fault.unsafe),
                    str(fault.overlay_outside),
                ]
                for fault in results.faults
            ],
        ),
        "## Traces",
        "",
        "Every agent session's trace, perception to action, is in `traces/`, one file per start.",
        "",
    ]
    return "\n".join(lines)


def _rate_cell(value: Rate, runs_per_start: int) -> str:
    return share(value) if runs_per_start == 1 else _plain(value)


def _calibration_verdict(scale: float | None) -> str:
    if scale is None:
        return ""
    if scale < 1:
        return (
            f"At the median the error is {scale:.2f} of the spread the region assumes: the "
            "region is larger than the errors need, on the safe side."
        )
    return (
        f"At the median the error is {scale:.2f} times the spread the region assumes: the "
        "region is smaller than the errors need."
    )


def _plain(value: Rate) -> str:
    return f"{value.k}/{value.n}" + ("" if value.rate is None else f" ({value.rate:.0%})")


def _percent(value: float | None) -> float | None:
    return None if value is None else value * 100
