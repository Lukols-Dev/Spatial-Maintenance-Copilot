"""The agent's perception over a frozen view set, and the score of what it locates."""

from eval_scene import ACCEPTED, BLIND, MOVES, TEST, UNSCORED, scene_dataset
from smc_core.contracts import Action, Failure
from smc_eval.dataset import Dataset
from smc_eval.perception import FrozenPerception
from smc_eval.scoring import score


def perception(dataset: Dataset) -> FrozenPerception:
    return FrozenPerception(dataset, TEST, samples=100)


def test_the_viewpoints_are_the_shots_with_the_target_hidden(dataset: Dataset) -> None:
    assert perception(dataset).viewpoints() == [ACCEPTED, MOVES, BLIND, UNSCORED]


def test_the_truth_of_a_viewpoint_is_its_paired_shot(dataset: Dataset) -> None:
    found = perception(dataset)
    truth = found.truth(ACCEPTED)

    assert truth is not None and truth.view == "A_open.png"
    assert truth.pixel == found.clicks.views["A_open.png"][dataset.atlas.target.id]
    assert found.truth(UNSCORED) is None


def test_a_viewpoint_is_localised_and_decided_as_the_service_does(dataset: Dataset) -> None:
    found = perception(dataset)

    assert found.localise(ACCEPTED).decision.action is Action.ACCEPT
    assert found.localise(MOVES).decision.action is Action.MOVE_CLOSER
    assert found.localise(BLIND).localisation.failure is Failure.TOO_FEW_CORRESPONDENCES
    assert found.localise(ACCEPTED) is found.localise(ACCEPTED)


def test_the_suggestions_lie_in_the_direction_of_the_move(dataset: Dataset) -> None:
    found = perception(dataset)

    assert found.suggest(MOVES, Action.MOVE_CLOSER) == [ACCEPTED]
    # Without a pose: the viewpoints that see every landmark, by name.
    assert found.suggest(BLIND, Action.MOVE_BACK) == [ACCEPTED, UNSCORED]


def test_a_located_view_scores_against_its_truth(dataset: Dataset) -> None:
    found = perception(dataset)

    accepted = score(found.localise(ACCEPTED), found.truth(ACCEPTED))
    held = score(found.localise(MOVES), found.truth(MOVES))

    assert accepted.outcome == "accepted_inside" and accepted.inside_95 is True
    assert accepted.error_px is not None and accepted.error_px < 3.0
    assert held.outcome == "held"
    assert score(found.localise(BLIND), found.truth(BLIND)).outcome == "failed"
    assert score(found.localise(UNSCORED), None).outcome == "accepted_unscored"


def test_an_accepted_result_far_from_the_truth_is_outside(dataset: Dataset) -> None:
    found = perception(dataset)
    truth = found.truth(ACCEPTED)
    assert truth is not None
    far = type(truth)(view=truth.view, pixel=(truth.pixel[0] + 200.0, truth.pixel[1]))

    scored = score(found.localise(ACCEPTED), far)

    assert scored.outcome == "accepted_outside" and scored.inside_95 is False


def test_the_scene_is_the_same_every_time() -> None:
    assert scene_dataset().sets[TEST].clicks == scene_dataset().sets[TEST].clicks
