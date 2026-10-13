from typing import Protocol

from smc_core.contracts import Action

from smc_agent.contracts import Located


class Perception(Protocol):
    """The geometry of one view set against one atlas, as the agent calls it.

    The service implements it over /localise; the tests with fixed answers.
    """

    def localise(self, view: str) -> Located:
        """The viewpoint localised and the policy's decision on it."""
        ...

    def viewpoints(self) -> list[str]:
        """The recorded viewpoints the operator may choose from."""
        ...

    def suggest(self, view: str, action: Action) -> list[str]:
        """Recorded viewpoints that lie in the direction of the move from view, best first."""
        ...
