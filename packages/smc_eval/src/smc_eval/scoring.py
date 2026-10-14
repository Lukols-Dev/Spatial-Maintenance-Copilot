"""A located view held against the truth: how far off, whether inside, and what it comes to."""

from dataclasses import dataclass

from smc_agent.contracts import Located
from smc_core.uncertainty import CHI2_95_2DOF

from smc_eval.metrics import distance, mahalanobis2
from smc_eval.perception import Truth
from smc_eval.results import Outcome


@dataclass(frozen=True)
class Scored:
    outcome: Outcome
    error_px: float | None
    mahalanobis2: float | None
    inside_95: bool | None


def score(located: Located, truth: Truth | None) -> Scored:
    """The outcome of a located view: failed, held, or accepted with the truth inside or not.

    inside_95 is the region's own test, the one the service reports: the
    squared Mahalanobis distance against the 95% radius. A region whose
    covariance cannot be inverted holds nothing, so an accepted result with
    one counts as outside.
    """
    localisation = located.localisation
    target, region = localisation.target, localisation.uncertainty
    error = d2 = inside = None
    if truth is not None and target is not None:
        error = distance(target.centre_px, truth.pixel)
        if region is not None:
            d2 = mahalanobis2(region, target.centre_px, truth.pixel)
            inside = d2 is not None and d2 <= CHI2_95_2DOF

    outcome: Outcome
    if localisation.failure is not None or target is None or region is None:
        outcome = "failed"
    elif not located.decision.reliable:
        outcome = "held"
    elif truth is None:
        outcome = "accepted_unscored"
    else:
        outcome = "accepted_inside" if inside else "accepted_outside"
    return Scored(outcome=outcome, error_px=error, mahalanobis2=d2, inside_95=inside)
