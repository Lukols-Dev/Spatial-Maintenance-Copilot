"""The words the agent uses besides the model's: the system prompt and the fallbacks.

A fallback is the policy's own decision put plainly. The operator gets it when
the model gives no answer, or an answer a guard rejected, so the loop never
waits for the model and never shows what the policy did not decide.
"""

import json
import re

from smc_core.contracts import Action

from smc_agent.contracts import Located

SYSTEM = """\
You are the guide of Spatial Maintenance Copilot. An operator points a phone at an asset to find \
a component hidden behind a cover. Computer vision localises the component from reference marks \
on the asset, and a policy judges the result against measured limits.

The policy decides, not you. It says whether the localisation is reliable, and if not, which way \
the camera should move and why. You turn that into words the operator can act on, and you act \
through your tools:

- Not reliable: you may call suggest_viewpoints with the policy's move, then call request_view \
once with the policy's move, one or two short sentences of guidance, and the viewpoints you suggest.
- Reliable: call present_result once, with where the component is in the operator's view and the \
next maintenance step for the operator to approve.

Rules:
- Never contradict the policy's move or its verdict.
- Never write numbers, percentages, distances or confidence levels: the measurements are shown \
next to your words and are not yours to state.
- Name the reference marks the operator should keep in view when the reasons mention them.
- Write plainly, to the operator, in English.
"""

MOVES = {
    Action.MOVE_LEFT: "Move the camera to the left",
    Action.MOVE_RIGHT: "Move the camera to the right",
    Action.MOVE_UP: "Raise the camera",
    Action.MOVE_DOWN: "Lower the camera",
    Action.MOVE_CLOSER: "Move the camera closer",
    Action.MOVE_BACK: "Step back with the camera",
}

EXPLANATION = "The hidden component lies inside the highlighted region of this view."
NEXT_STEP = "Remove the cover in front of the highlighted region and check the component."

# Digits and percent signs: the model may not state measurements or confidence.
NUMBERS = re.compile(r"[0-9%]")


def has_numbers(text: str) -> bool:
    return NUMBERS.search(text) is not None


def guidance_for(located: Located) -> str:
    """The policy's move and its reason, as a sentence."""
    decision = located.decision
    move = MOVES.get(decision.action, "Take another view")
    return f"{move}: {decision.move_reason}." if decision.move_reason else f"{move}."


def observation(located: Located) -> str:
    """What the model is told about a viewpoint: the facts, as JSON."""
    decision = located.decision
    localisation = located.localisation
    quality = localisation.quality
    facts = {
        "view": located.view,
        "reliable": decision.reliable,
        "failure": None if localisation.failure is None else localisation.failure.value,
        "policy_move": decision.action.value,
        "move_reason": decision.move_reason,
        "reasons": decision.reasons,
        "marks_seen": [] if quality is None else sorted(quality.reprojection_px),
        "marks_rejected": [] if quality is None else quality.outlier_ids,
    }
    return json.dumps(facts, ensure_ascii=False)
