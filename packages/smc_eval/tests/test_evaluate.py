"""A whole evaluation of the synthetic scene: every section counts what the scene holds."""

import dataclasses

from eval_scene import (
    ACCEPTED,
    BLIND,
    BUILD,
    ENVIRONMENT,
    LANDMARKS,
    MOVES,
    SAMPLES,
    TEST,
    UNSCORED,
    clicked,
    held_out_clicks,
)
from smc_agent.contracts import TraceEvent
from smc_core.contracts import Clicks
from smc_eval.check import differences
from smc_eval.dataset import Dataset, ViewSet
from smc_eval.evaluate import evaluate
from smc_eval.faults import FAULTS
from smc_eval.report import render
from smc_eval.results import Results


def test_every_viewpoint_is_scored_against_its_truth(results: Results) -> None:
    outcomes = {view.view: view.outcome for view in results.views}

    assert outcomes == {
        ACCEPTED: "accepted_inside",
        MOVES: "held",
        BLIND: "failed",
        UNSCORED: "accepted_unscored",
    }
    accepted = next(view for view in results.views if view.view == ACCEPTED)
    assert accepted.truth_view == "A_open.png" and accepted.landmarks == 6
    assert accepted.error_px is not None and accepted.error_px < 3.0


def test_the_localisation_summary_counts_the_scored_viewpoints(results: Results) -> None:
    summary = results.localisation

    assert (summary.viewpoints, summary.with_truth, summary.localised) == (4, 3, 2)
    assert (summary.inside_95.k, summary.inside_95.n) == (2, 2)
    assert (summary.inside_95_accepted.k, summary.inside_95_accepted.n) == (1, 1)
    assert summary.rms_reprojection_px.n == 3
    assert summary.actions == {"ACCEPT": 2, "MOVE_BACK": 1, "MOVE_CLOSER": 1}


def test_the_decisions_are_held_against_the_truth(results: Results) -> None:
    decisions = results.decisions

    assert (decisions.accepted_inside, decisions.accepted_outside) == (1, 0)
    assert (decisions.held_inside + decisions.held_outside, decisions.failed) == (1, 1)
    assert decisions.false_accept.n == 1


def test_the_calibration_reads_coverage_at_each_confidence(results: Results) -> None:
    levels = results.uncertainty.levels

    assert [level.confidence for level in levels] == [0.5, 0.8, 0.95, 0.99]
    assert all(level.observed.n == 2 for level in levels)
    assert [level.observed.k for level in levels] == sorted(level.observed.k for level in levels)
    assert results.uncertainty.scale is not None


def test_the_landmark_pose_is_held_against_the_board(results: Results) -> None:
    checks = {(check.view_set, check.view): check for check in results.board_checks}

    # B_close has four landmarks, enough for a pose; the build frames are in-sample.
    assert sorted(checks) == [
        (BUILD, "frame_3.png"),
        (BUILD, "frame_4.png"),
        (BUILD, "frame_5.png"),
        (TEST, ACCEPTED),
        (TEST, MOVES),
    ]
    assert checks[TEST, ACCEPTED].in_sample is False and checks[BUILD, "frame_3.png"].in_sample
    assert checks[TEST, ACCEPTED].translation_mm < 10.0
    assert checks[TEST, ACCEPTED].rotation_deg < 1.0
    assert [summary.frames for summary in results.board_summary] == [2, 3]


def test_the_monte_carlo_region_is_checked_on_other_seeds(results: Results) -> None:
    monte_carlo = results.monte_carlo

    assert monte_carlo.seeds == [0, 1, 2, 3, 4]
    assert monte_carlo.views == 3
    assert monte_carlo.inside_95_changes == 0


def test_every_strategy_runs_from_every_start(results: Results) -> None:
    strategies = {(s.strategy, s.starts_from): s for s in results.strategies}

    assert len(strategies) == 12
    agent = strategies["agent", "every viewpoint"]
    assert (agent.success.k, agent.success.n, agent.refused.k, agent.unscored) == (3, 3, 0, 1)
    assert strategies["policy_only", "localised"].success.k == 1
    assert strategies["agent", "not localised"].starts == 1
    assert strategies["random", "every viewpoint"].runs_per_start == 100
    assert [run.strategy for run in results.sessions].count("random") == 0
    assert len(results.sessions) == 12


def test_the_agent_s_next_view_beats_the_start(results: Results) -> None:
    assert [step.start for step in results.next_views] == [MOVES]
    assert results.next_views[0].agent_view == ACCEPTED
    assert results.improvement.agent_reliable.k == 1


def test_every_fault_is_counted_in_full(results: Results) -> None:
    assert [fault.fault for fault in results.faults] == [fault.name for fault in FAULTS]
    for fault in results.faults:
        assert fault.trials == (
            fault.failed + fault.held + fault.accepted_inside + fault.accepted_outside
        )
        assert fault.overlay_outside >= fault.accepted_outside
    none = results.faults[0]
    assert (none.trials, none.accepted_inside, none.held) == (2, 1, 1)
    three = results.faults[1]
    # Twenty ways of keeping three of A's six landmarks, four of B's four.
    assert three.trials == three.failed == 24


def test_a_trace_is_kept_for_every_agent_session(
    run: tuple[Results, dict[str, list[TraceEvent]]],
) -> None:
    results, traces = run

    assert sorted(traces) == sorted(
        session.trace for session in results.sessions if session.trace is not None
    )
    assert traces[f"traces/{TEST}/B_close.json"][-1].kind == "human"


def test_the_results_survive_their_json(results: Results) -> None:
    assert Results.model_validate_json(results.model_dump_json()) == results


def test_a_second_run_reproduces_the_first(dataset: Dataset, results: Results) -> None:
    again, _ = evaluate(
        dataset, evaluated_at="another day", environment=ENVIRONMENT, samples=SAMPLES
    )

    assert differences(results.model_dump(mode="json"), again.model_dump(mode="json")) == []


def test_two_shots_from_one_spot_are_compared(dataset: Dataset) -> None:
    views = dict(held_out_clicks().views)
    views["A_1_close.png"] = {
        point: (pixel[0] + 1.0, pixel[1] - 1.0) for point, pixel in clicked(2, LANDMARKS).items()
    }
    test = dataset.sets[TEST]
    with_repeat = dataclasses.replace(
        dataset,
        sets={
            TEST: ViewSet(TEST, "test", Clicks(camera_id=test.clicks.camera_id, views=views), {}),
        },
    )

    found, _ = evaluate(with_repeat, evaluated_at="now", environment=ENVIRONMENT, samples=SAMPLES)

    assert [(repeat.first, repeat.second) for repeat in found.repeats] == [
        ("A_1_close.png", ACCEPTED)
    ]
    assert found.repeats[0].target_px < 5.0


def test_the_report_shows_every_section(results: Results) -> None:
    report = render(results)

    for heading in (
        "# Evaluation on synthetic",
        "## Localisation",
        "## Uncertainty calibration",
        "## Decisions against the truth",
        "## Pose stability",
        "## Task success",
        "## The agent's next view",
        "## Injected faults",
        "## Traces",
    ):
        assert heading in report
    assert f"| {ACCEPTED} | A_open.png | 6 | ACCEPT |" in report
    assert "`abc123`" in report
