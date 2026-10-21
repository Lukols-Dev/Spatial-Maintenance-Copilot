"""The agent's perception over a frozen view set: the service's code, on frozen inputs.

A viewpoint is localised by smc_core's localise and decide on its clicks, as
POST /localise does it; viewpoints, truths and suggestions are those of
smc_core.viewpoints, as the service's sessions take them. So the agent scored
here is the one the web app runs, with only the files read differently.
"""

from dataclasses import dataclass
from functools import cached_property

from smc_agent.contracts import Located
from smc_core.calibration import Intrinsics
from smc_core.contracts import Action, Atlas, Pose, Vec2, View
from smc_core.localise import localise
from smc_core.policy import DEFAULT_POLICY, decide
from smc_core.viewpoints import (
    hidden_target_views,
    observed_view,
    poses_from_clicks,
    suggested_viewpoints,
    truth_view,
)

from smc_eval.dataset import Dataset

# As POST /localise takes them by default.
SAMPLES = 500
SEED = 0


@dataclass(frozen=True)
class Truth:
    """The target clicked where it is in sight: in view, from the spot a viewpoint was taken."""

    view: str
    pixel: Vec2


def locate(view: View, atlas: Atlas, intrinsics: Intrinsics, samples: int, seed: int) -> Located:
    """One view localised and the policy's decision on it, as the service gives them."""
    localisation = localise(atlas, view, intrinsics, samples, seed)
    return Located(
        view=view.view_id,
        localisation=localisation,
        decision=decide(localisation, view, atlas, intrinsics),
    )


class FrozenPerception:
    """One view set of a frozen dataset, as the agent asks about it.

    Every viewpoint is localised once; the results are kept for the life of
    the object, as the service keeps them for one request.
    """

    def __init__(
        self, dataset: Dataset, view_set: str, samples: int = SAMPLES, seed: int = SEED
    ) -> None:
        self.dataset = dataset
        self.clicks = dataset.sets[view_set].clicks
        self.samples = samples
        self.seed = seed
        self._located: dict[str, Located] = {}

    def observed(self, view: str) -> View:
        return observed_view(view, self.clicks, self.dataset.atlas, self.dataset.sigma_px)

    def truth(self, view: str) -> Truth | None:
        paired = truth_view(view, self.clicks, self.dataset.atlas.target.id)
        if paired is None:
            return None
        return Truth(view=paired, pixel=self.clicks.views[paired][self.dataset.atlas.target.id])

    @cached_property
    def poses(self) -> dict[str, Pose]:
        """Where each viewpoint's camera stood, from its clicks alone."""
        return poses_from_clicks(
            self.viewpoints(), self.clicks, self.dataset.atlas, self.dataset.intrinsics
        )

    # ---- the Perception of smc_agent ----------------------------------------------

    def localise(self, view: str) -> Located:
        if view not in self._located:
            self._located[view] = locate(
                self.observed(view),
                self.dataset.atlas,
                self.dataset.intrinsics,
                self.samples,
                self.seed,
            )
        return self._located[view]

    def viewpoints(self) -> list[str]:
        return hidden_target_views(self.clicks, self.dataset.atlas)

    def suggest(self, view: str, action: Action) -> list[str]:
        return suggested_viewpoints(
            view, action, self.poses, self.clicks, self.dataset.atlas, DEFAULT_POLICY.min_inliers
        )
