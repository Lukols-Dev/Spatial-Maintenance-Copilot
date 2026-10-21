"""Sessions with a simulated operator, through the Copilot's graph and without it."""

import random

import pytest
from eval_scene import ACCEPTED, BLIND, MOVES, TEST, UNSCORED
from smc_agent.model import NoModel
from smc_eval import sessions
from smc_eval.dataset import Dataset
from smc_eval.perception import FrozenPerception
from smc_eval.results import SessionRun

ASSET = "home-cabinet"


@pytest.fixture
def perception(dataset: Dataset) -> FrozenPerception:
    return FrozenPerception(dataset, TEST, samples=100)


def agent(perception: FrozenPerception, start: str) -> SessionRun:
    copilot = sessions.copilot_for({TEST: perception}, NoModel("no model in the tests"))
    run, _ = sessions.agent_session(copilot, perception, ASSET, TEST, start)
    return run


def test_the_agent_moves_where_it_asks_and_the_result_is_approved(
    perception: FrozenPerception,
) -> None:
    run = agent(perception, MOVES)

    assert run.views == [MOVES, ACCEPTED]
    assert run.outcome == "accepted" and run.final_view == ACCEPTED
    assert run.success is True and run.inside_95 is True
    assert run.fallbacks == 2 and run.guards == 0
    assert run.trace == "traces/cabinet-b/B_close.json"


def test_the_agent_s_trace_runs_from_perception_to_approval(perception: FrozenPerception) -> None:
    copilot = sessions.copilot_for({TEST: perception}, NoModel("no model in the tests"))
    _, trace = sessions.agent_session(copilot, perception, ASSET, TEST, MOVES)

    assert [event.kind for event in trace] == [
        "perception",
        "decision",
        "fallback",
        "agent",
        "human",
        "perception",
        "decision",
        "fallback",
        "agent",
        "human",
    ]
    assert trace[-1].summary == "the operator approved"


def test_from_a_view_without_a_pose_the_agent_sends_the_operator_where_most_is_seen(
    perception: FrozenPerception,
) -> None:
    run = agent(perception, BLIND)

    assert run.views == [BLIND, ACCEPTED]
    assert run.outcome == "accepted" and run.success is True


def test_a_result_accepted_where_no_truth_was_recorded_is_unscored(
    perception: FrozenPerception,
) -> None:
    run = agent(perception, UNSCORED)

    assert run.outcome == "accepted" and run.success is None


def test_the_agent_stops_after_the_last_viewpoint_allowed(perception: FrozenPerception) -> None:
    copilot = sessions.copilot_for({TEST: perception}, NoModel("no model in the tests"))

    run, _ = sessions.agent_session(copilot, perception, ASSET, TEST, MOVES, max_views=1)

    assert run.views == [MOVES] and run.outcome == "refused"


def test_a_single_view_shows_whatever_localises(perception: FrozenPerception) -> None:
    assert sessions.single_view(perception, TEST, MOVES).outcome == "accepted"
    assert sessions.single_view(perception, TEST, MOVES).success is True
    assert sessions.single_view(perception, TEST, BLIND).outcome == "refused"


def test_the_policy_alone_shows_only_what_it_accepts(perception: FrozenPerception) -> None:
    assert sessions.policy_only(perception, TEST, MOVES).outcome == "refused"
    assert sessions.policy_only(perception, TEST, ACCEPTED).success is True


def test_a_random_walk_ends_within_its_views_and_repeats_with_its_seed(
    perception: FrozenPerception,
) -> None:
    first = [sessions.random_walk(perception, TEST, BLIND, random.Random(3)) for _ in range(5)]
    again = [sessions.random_walk(perception, TEST, BLIND, random.Random(3)) for _ in range(5)]

    assert first == again
    for run in first:
        assert run.views[0] == BLIND and len(run.views) <= sessions.MAX_VIEWS
        assert len(set(run.views)) == len(run.views)
        assert run.outcome == "accepted" or len(run.views) == len(perception.viewpoints())


def test_a_summary_counts_success_false_accepts_and_refusals(
    perception: FrozenPerception,
) -> None:
    runs = [agent(perception, start) for start in perception.viewpoints()]

    summary = sessions.summarise("agent", runs, 1, "every viewpoint")

    assert (summary.starts, summary.unscored) == (4, 1)
    assert (summary.success.k, summary.success.n) == (3, 3)
    assert (summary.false_accept.k, summary.refused.k) == (0, 0)
    assert summary.views_to_success.mean == pytest.approx(5 / 3)


def test_the_agent_s_next_view_is_held_against_the_first_and_a_random_one(
    perception: FrozenPerception,
) -> None:
    run = agent(perception, MOVES)

    step = sessions.next_view(perception, TEST, run)

    assert step is not None and step.agent_view == ACCEPTED and step.agent_reliable is True
    assert step.error_agent_px is not None and step.error_random_px is not None
    assert step.random_reliable == pytest.approx(2 / 3)
    assert sessions.next_view(perception, TEST, agent(perception, ACCEPTED)) is None

    improvement = sessions.improvement([step])
    assert (improvement.starts, improvement.with_agent_view, improvement.agent_reliable.k) == (
        1,
        1,
        1,
    )
