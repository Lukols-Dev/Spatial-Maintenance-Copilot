"""Faults injected into the clicks of a viewpoint, and what the system makes of them.

The proposal names the failures the system must handle: too few
correspondences, a low inlier ratio, a large reprojection error, an unstable
pose. Each fault here breaks a viewpoint's clicks the way an operator or a
detector would, and the outcome is held against the viewpoint's truth. A
refusal or a request to move is a safe answer; so is an accepted result whose
95% region still holds the truth. An accepted result whose region misses the
truth is a plausible overlay in the wrong place: the one unsafe outcome.

Faults are injected into viewpoints that localise and have a truth, so every
trial can be scored.
"""

import itertools
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
from smc_core.contracts import LandmarkObservation, View

# How far a gross click error moves a click: a neighbouring feature, not a slip.
GROSS_SHIFT_PX = 60.0
NOISE_TRIALS = 10


@dataclass(frozen=True)
class Fault:
    name: str
    description: str
    inject: Callable[[View, float, np.random.Generator], list[View]]


def _moved(view: View, pixels: dict[str, tuple[float, float]]) -> View:
    return view.model_copy(
        update={
            "observations": [
                LandmarkObservation(
                    landmark_id=observation.landmark_id,
                    pixel=pixels.get(observation.landmark_id, observation.pixel),
                    sigma_px=observation.sigma_px,
                )
                for observation in view.observations
            ]
        }
    )


def unchanged(view: View, sigma_px: float, rng: np.random.Generator) -> list[View]:
    return [view]


def three_landmarks(view: View, sigma_px: float, rng: np.random.Generator) -> list[View]:
    """Every way of keeping three of the clicked landmarks: one short of a pose."""
    return [
        view.model_copy(update={"observations": list(kept)})
        for kept in itertools.combinations(view.observations, 3)
    ]


def swapped_labels(view: View, sigma_px: float, rng: np.random.Generator) -> list[View]:
    """Every pair of landmarks clicked under each other's name."""
    return [
        _moved(view, {first.landmark_id: second.pixel, second.landmark_id: first.pixel})
        for first, second in itertools.combinations(view.observations, 2)
    ]


def gross_click(view: View, sigma_px: float, rng: np.random.Generator) -> list[View]:
    """Each click in turn put GROSS_SHIFT_PX away from the others, on the wrong feature."""
    pixels = np.array([observation.pixel for observation in view.observations], np.float64)
    centre = pixels.mean(axis=0)
    faulted = []
    for observation, pixel in zip(view.observations, pixels, strict=True):
        away = pixel - centre
        norm = float(np.linalg.norm(away))
        direction = away / norm if norm > 1e-9 else np.array([1.0, 0.0])
        shifted = pixel + GROSS_SHIFT_PX * direction
        faulted.append(
            _moved(view, {observation.landmark_id: (float(shifted[0]), float(shifted[1]))})
        )
    return faulted


def _noise(scale: float) -> Callable[[View, float, np.random.Generator], list[View]]:
    def inject(view: View, sigma_px: float, rng: np.random.Generator) -> list[View]:
        trials = []
        for _ in range(NOISE_TRIALS):
            offsets = rng.normal(0.0, scale * sigma_px, (len(view.observations), 2))
            trials.append(
                _moved(
                    view,
                    {
                        observation.landmark_id: (
                            observation.pixel[0] + float(offset[0]),
                            observation.pixel[1] + float(offset[1]),
                        )
                        for observation, offset in zip(view.observations, offsets, strict=True)
                    },
                )
            )
        return trials

    return inject


FAULTS = [
    Fault("none", "the clicks as made: the reference", unchanged),
    Fault("three_landmarks", "one landmark short of a pose", three_landmarks),
    Fault("swapped_labels", "two landmarks clicked under each other's name", swapped_labels),
    Fault(
        "gross_click", f"one click {GROSS_SHIFT_PX:.0f} px off, on the wrong feature", gross_click
    ),
    Fault("click_noise", "every click off by the click sigma the region assumes", _noise(1.0)),
    Fault("heavy_noise", "every click off by three times that sigma", _noise(3.0)),
]
