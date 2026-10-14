"""The injected faults: each breaks the clicks the way it says, and only that."""

import numpy as np
import pytest
from eval_scene import ACCEPTED, TEST
from smc_core.contracts import View
from smc_eval.dataset import Dataset
from smc_eval.faults import (
    FAULTS,
    GROSS_SHIFT_PX,
    NOISE_TRIALS,
    gross_click,
    swapped_labels,
    three_landmarks,
)
from smc_eval.perception import FrozenPerception


@pytest.fixture
def view(dataset: Dataset) -> View:
    return FrozenPerception(dataset, TEST).observed(ACCEPTED)


def pixels(view: View) -> dict[str, tuple[float, float]]:
    return {observation.landmark_id: observation.pixel for observation in view.observations}


def test_three_landmarks_keeps_every_three_of_six(view: View) -> None:
    faulted = three_landmarks(view, 1.0, np.random.default_rng(0))

    assert len(faulted) == 20
    assert all(len(each.observations) == 3 for each in faulted)
    assert len({tuple(pixels(each)) for each in faulted}) == 20


def test_swapped_labels_exchanges_two_clicks_and_keeps_the_rest(view: View) -> None:
    faulted = swapped_labels(view, 1.0, np.random.default_rng(0))
    clicks = pixels(view)

    assert len(faulted) == 15
    first = pixels(faulted[0])
    moved = [landmark for landmark in clicks if first[landmark] != clicks[landmark]]
    assert len(moved) == 2
    assert first[moved[0]] == clicks[moved[1]] and first[moved[1]] == clicks[moved[0]]


def test_a_gross_click_moves_one_click_by_the_shift(view: View) -> None:
    faulted = gross_click(view, 1.0, np.random.default_rng(0))
    clicks = pixels(view)

    assert len(faulted) == len(clicks)
    for index, each in enumerate(faulted):
        landmark = view.observations[index].landmark_id
        moved = pixels(each)
        assert np.hypot(*np.subtract(moved[landmark], clicks[landmark])) == pytest.approx(
            GROSS_SHIFT_PX
        )
        assert {key: value for key, value in moved.items() if key != landmark} == {
            key: value for key, value in clicks.items() if key != landmark
        }


def test_the_noise_draws_from_its_generator(view: View) -> None:
    noise = next(fault for fault in FAULTS if fault.name == "click_noise")

    first = noise.inject(view, 2.0, np.random.default_rng(7))
    again = noise.inject(view, 2.0, np.random.default_rng(7))

    assert len(first) == NOISE_TRIALS
    assert [pixels(each) for each in first] == [pixels(each) for each in again]
    assert pixels(first[0]) != pixels(view)


def test_every_fault_keeps_the_click_sigma(view: View) -> None:
    for fault in FAULTS:
        for faulted in fault.inject(view, 1.0, np.random.default_rng(0)):
            assert {observation.sigma_px for observation in faulted.observations} == {1.0}
