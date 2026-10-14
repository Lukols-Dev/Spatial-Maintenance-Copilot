"""Sessions with a simulated operator: the agent against a single view, the policy alone, and chance.

The operator stands at a recorded viewpoint with the target hidden. Each
strategy decides what is shown to them and where they go next:

- single_view: the overlay of the first view, whatever its quality. No policy, no agent.
- policy_only: the overlay only when the policy accepts the first view; else nothing.
- agent: the Copilot's graph, as the web app runs it. The operator goes to the first
  viewpoint the agent suggests that they have not stood at, and approves the result
  when the agent presents one.
- random: the policy decides, and the operator goes to a viewpoint drawn at random
  from those they have not stood at.

A run ends when a result is accepted, when there is nowhere to go, or after
MAX_VIEWS viewpoints. It succeeds when the accepted result's 95% region holds
the truth; an accepted result without it is a false accept, the outcome the
system exists to prevent. A run ending without a result is a refusal: safe,
but the operator is no closer to the target.
"""

import random
from collections.abc import Sequence
from pathlib import Path

from langgraph.checkpoint.memory import InMemorySaver
from smc_agent.contracts import ApprovalRequest, TraceEvent
from smc_agent.copilot import Copilot
from smc_agent.model import ChatModel

from smc_eval.metrics import Spread, rate, spread
from smc_eval.perception import FrozenPerception
from smc_eval.results import Improvement, NextView, SessionRun, StartsFrom, StrategySummary
from smc_eval.scoring import score

# The first viewpoint and three moves.
MAX_VIEWS = 4
RANDOM_RUNS = 100

DESCRIPTIONS = {
    "single_view": "the first view's overlay, whatever its quality",
    "policy_only": "the first view's overlay if the policy accepts it, else nothing",
    "agent": "the agent's loop: move where it asks until it presents a result",
    "random": "the policy decides; the operator moves to a random viewpoint",
}


def _ended(
    strategy: str,
    perception: FrozenPerception,
    view_set: str,
    views: list[str],
    accepted: bool,
) -> SessionRun:
    final = views[-1] if accepted else None
    error = inside = success = None
    if final is not None:
        truth = perception.truth(final)
        scored = score(perception.localise(final), truth)
        error, inside = scored.error_px, scored.inside_95
        success = None if truth is None else bool(inside)
    else:
        success = False
    return SessionRun(
        strategy=strategy,
        view_set=view_set,
        start=views[0],
        views=views,
        outcome="accepted" if accepted else "refused",
        final_view=final,
        error_px=error,
        inside_95=inside,
        success=success,
    )


def single_view(perception: FrozenPerception, view_set: str, start: str) -> SessionRun:
    """The overlay of the first view is taken as it is, when there is one."""
    shown = score(perception.localise(start), perception.truth(start)).outcome != "failed"
    return _ended("single_view", perception, view_set, [start], shown)


def policy_only(perception: FrozenPerception, view_set: str, start: str) -> SessionRun:
    reliable = perception.localise(start).decision.reliable
    return _ended("policy_only", perception, view_set, [start], reliable)


def random_walk(
    perception: FrozenPerception,
    view_set: str,
    start: str,
    rng: random.Random,
    max_views: int = MAX_VIEWS,
) -> SessionRun:
    views = [start]
    while True:
        if perception.localise(views[-1]).decision.reliable:
            return _ended("random", perception, view_set, views, True)
        left = [view for view in perception.viewpoints() if view not in views]
        if len(views) >= max_views or not left:
            return _ended("random", perception, view_set, views, False)
        views.append(rng.choice(left))


def agent_session(
    copilot: Copilot,
    perception: FrozenPerception,
    asset_id: str,
    view_set: str,
    start: str,
    max_views: int = MAX_VIEWS,
) -> tuple[SessionRun, list[TraceEvent]]:
    """One session through the Copilot's graph, the operator following its first new suggestion."""
    session_id = f"{view_set}/{start}"
    turn = copilot.start(session_id, asset_id, view_set, start)
    views = [start]
    accepted = False
    while turn.awaiting is not None:
        request = turn.awaiting
        if isinstance(request, ApprovalRequest):
            copilot.approve(session_id, True)
            accepted = True
            break
        choice = next((view for view in request.suggested_views if view not in views), None)
        if choice is None or len(views) >= max_views:
            break
        views.append(choice)
        turn = copilot.choose_view(session_id, choice)
    trace = copilot.trace(session_id)
    run = _ended("agent", perception, view_set, views, accepted)
    return run.model_copy(
        update={
            "guards": sum(event.kind == "guard" for event in trace),
            "fallbacks": sum(event.kind == "fallback" for event in trace),
            "trace": trace_file(view_set, start),
        }
    ), trace


def trace_file(view_set: str, start: str) -> str:
    return f"traces/{view_set}/{Path(start).stem}.json"


def copilot_for(perceptions: dict[str, FrozenPerception], model: ChatModel) -> Copilot:
    return Copilot(model, lambda _asset_id, view_set: perceptions[view_set], InMemorySaver())


def summarise(
    strategy: str, runs: Sequence[SessionRun], runs_per_start: int, starts_from: StartsFrom
) -> StrategySummary:
    scored = [run for run in runs if run.success is not None]
    return StrategySummary(
        strategy=strategy,
        description=DESCRIPTIONS[strategy],
        starts_from=starts_from,
        starts=len(runs) // runs_per_start,
        runs_per_start=runs_per_start,
        success=rate(sum(bool(run.success) for run in scored), len(scored)),
        false_accept=rate(
            sum(run.outcome == "accepted" and run.inside_95 is False for run in scored),
            len(scored),
        ),
        refused=rate(sum(run.outcome == "refused" for run in runs), len(runs)),
        unscored=len(runs) - len(scored),
        views=spread([len(run.views) for run in runs]),
        views_to_success=spread([len(run.views) for run in runs if run.success]),
    )


# ---- one step: the agent's next view against a random one ---------------------------------


def next_view(perception: FrozenPerception, view_set: str, run: SessionRun) -> NextView | None:
    """For a start the policy holds, with a truth: the result before, after the agent's move, and after a random one."""
    located = perception.localise(run.start)
    before = score(located, perception.truth(run.start))
    region = located.localisation.uncertainty
    if located.decision.reliable or before.error_px is None or region is None:
        return None

    agent_view = run.views[1] if len(run.views) > 1 else None
    error_agent = semi_major_agent = agent_reliable = None
    if agent_view is not None:
        after = perception.localise(agent_view)
        error_agent = score(after, perception.truth(agent_view)).error_px
        if after.localisation.uncertainty is not None:
            semi_major_agent = after.localisation.uncertainty.ellipse.semi_major_px
        agent_reliable = after.decision.reliable

    others = [view for view in perception.viewpoints() if view != run.start]
    errors: list[float] = []
    semi_majors: list[float] = []
    for view in others:
        other = perception.localise(view)
        error = score(other, perception.truth(view)).error_px
        if error is not None:
            errors.append(error)
        if other.localisation.uncertainty is not None:
            semi_majors.append(other.localisation.uncertainty.ellipse.semi_major_px)
    reliable = [perception.localise(view).decision.reliable for view in others]

    return NextView(
        view_set=view_set,
        start=run.start,
        action=located.decision.action,
        agent_view=agent_view,
        error_before_px=before.error_px,
        error_agent_px=error_agent,
        error_random_px=_mean(errors),
        semi_major_before_px=region.ellipse.semi_major_px,
        semi_major_agent_px=semi_major_agent,
        semi_major_random_px=_mean(semi_majors),
        agent_reliable=agent_reliable,
        random_reliable=_mean([float(value) for value in reliable]),
    )


def improvement(steps: Sequence[NextView]) -> Improvement:
    moved = [step for step in steps if step.agent_view is not None]
    with_error = [step for step in moved if step.error_agent_px is not None]
    with_region = [step for step in moved if step.semi_major_agent_px is not None]
    random_reliable = [step.random_reliable for step in steps if step.random_reliable is not None]
    return Improvement(
        starts=len(steps),
        with_agent_view=len(moved),
        error_before_px=spread([step.error_before_px for step in steps]),
        error_agent_px=_spread_of([step.error_agent_px for step in moved]),
        error_random_px=_spread_of([step.error_random_px for step in steps]),
        semi_major_before_px=spread([step.semi_major_before_px for step in steps]),
        semi_major_agent_px=_spread_of([step.semi_major_agent_px for step in moved]),
        semi_major_random_px=_spread_of([step.semi_major_random_px for step in steps]),
        agent_lower_error=rate(
            sum(_below(step.error_agent_px, step.error_before_px) for step in with_error),
            len(with_error),
        ),
        agent_smaller_region=rate(
            sum(
                _below(step.semi_major_agent_px, step.semi_major_before_px) for step in with_region
            ),
            len(with_region),
        ),
        agent_reliable=rate(sum(bool(step.agent_reliable) for step in moved), len(moved)),
        random_reliable=_mean(random_reliable),
    )


def _below(value: float | None, limit: float) -> bool:
    return value is not None and value < limit


def _mean(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _spread_of(values: Sequence[float | None]) -> Spread:
    return spread([value for value in values if value is not None])
