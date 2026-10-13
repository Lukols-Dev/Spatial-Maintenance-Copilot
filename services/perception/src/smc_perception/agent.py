"""The agent's side of the service: its model, its sessions, its view of the workspace.

The agent (smc_agent) runs its loop over a Perception. Here that is the
workspace: one atlas and one view set, localised by the code /localise runs,
so a session and the Locate page give the same answer for the same view.

Sessions live in CHECKPOINTER, in memory: a restart of the service ends them.
"""

from functools import cache, cached_property

from langgraph.checkpoint.memory import InMemorySaver
from smc_agent.bedrock import bedrock_model
from smc_agent.contracts import Located
from smc_agent.model import ChatModel
from smc_agent.nova import nova_model
from smc_core.contracts import Action, Atlas, Clicks, LandmarkObservation, Pose, View
from smc_core.pose import MIN_CORRESPONDENCES, correspondences, fit_pose
from smc_core.viewpoints import fitting_viewpoints

from smc_perception.atlases import read_atlas
from smc_perception.cameras import find_intrinsics
from smc_perception.config import model_settings
from smc_perception.localisation import DEFAULT_SIGMA_PX, localise_view
from smc_perception.models import LocaliseRequest, LocaliseResult
from smc_perception.view_sets import required_clicks
from smc_perception.workspace import WorkspaceFiles

CHECKPOINTER = InMemorySaver()


@cache
def _model(region: str, model_id: str, effort: str, access_key: str, secret_key: str) -> ChatModel:
    """Claude (anthropic.…, eu.anthropic.…) through the Messages API, Amazon Nova through Converse."""
    make = bedrock_model if "anthropic." in model_id else nova_model
    return make(region, model_id, effort, access_key=access_key, secret_key=secret_key)


def agent_model() -> ChatModel:
    """The model the settings name, one client per setting for the life of the process.

    The keys go to the client from the settings: a .env file is read into them,
    not into the environment botocore looks at.
    """
    found = model_settings()
    return _model(
        found.smc_bedrock_region,
        found.smc_agent_model,
        found.smc_agent_effort,
        found.aws_access_key_id.get_secret_value(),
        found.aws_secret_access_key.get_secret_value(),
    )


def model_name() -> str:
    """Which model speaks for the agent, as the web app shows it."""
    found = model_settings()
    return f"{found.smc_agent_model} ({found.smc_bedrock_region})"


class WorkspacePerception:
    """One atlas and one view set of the workspace, as the agent asks about them.

    A viewpoint is an image whose clicks mark landmarks of the atlas and not
    the target: the target is clicked only where it is in sight, so those
    images show it hidden. Its truth is the image of the same viewpoint with
    the target clicked: the files share the name up to the first "_", as
    B1_close.png and B1_open.png do.

    Results are kept for the life of the object, one request.
    """

    def __init__(self, workspace: WorkspaceFiles, asset_id: str, view_set: str) -> None:
        self.workspace = workspace
        self.asset_id = asset_id
        self.view_set = view_set
        self.results: dict[str, LocaliseResult] = {}

    @cached_property
    def atlas(self) -> Atlas:
        return read_atlas(self.workspace, self.asset_id).atlas

    @cached_property
    def clicks(self) -> Clicks:
        folder = self.workspace.view_set(self.view_set)
        return required_clicks(self.workspace, folder, self.view_set)

    # ---- the Perception of smc_agent ----------------------------------------------

    def localise(self, view: str) -> Located:
        result = self.result(view)
        return Located(view=view, localisation=result.localisation, decision=result.decision)

    def viewpoints(self) -> list[str]:
        landmarks = {landmark.id for landmark in self.atlas.landmarks}
        target = self.atlas.target.id
        return sorted(
            name
            for name, marked in self.clicks.views.items()
            if target not in marked and landmarks & marked.keys()
        )

    def suggest(self, view: str, action: Action) -> list[str]:
        poses = self.poses
        current = poses.get(view)
        if current is None:
            return []
        others = {name: pose for name, pose in poses.items() if name != view}
        return fitting_viewpoints(current, others, action)

    # ---- for the HTTP answer -------------------------------------------------------

    def result(self, view: str) -> LocaliseResult:
        """The localisation of a viewpoint as POST /localise answers it, its truth paired."""
        if view not in self.results:
            request = LocaliseRequest(
                asset_id=self.asset_id,
                view_set=self.view_set,
                view=view,
                truth_view=self.truth_view(view),
            )
            self.results[view] = localise_view(self.workspace, request)
        return self.results[view]

    def truth_view(self, view: str) -> str | None:
        """The image of the same viewpoint with the target clicked, if the set has one."""
        prefix = view.split("_", 1)[0]
        target = self.atlas.target.id
        paired = sorted(
            name
            for name, marked in self.clicks.views.items()
            if name != view and name.split("_", 1)[0] == prefix and target in marked
        )
        return paired[0] if paired else None

    @cached_property
    def poses(self) -> dict[str, Pose]:
        """Where each viewpoint's camera stood: PnP with RANSAC on its clicks, nothing more.

        No Monte Carlo region: placing viewpoints relative to each other needs
        only the pose, and this runs for every viewpoint of the set.
        """
        intrinsics = find_intrinsics(self.workspace, self.clicks.camera_id)
        poses: dict[str, Pose] = {}
        for name in self.viewpoints():
            marked = self.clicks.views[name]
            view = View(
                view_id=name,
                camera_id=self.clicks.camera_id,
                observations=[
                    LandmarkObservation(
                        landmark_id=landmark.id,
                        pixel=marked[landmark.id],
                        sigma_px=DEFAULT_SIGMA_PX,
                    )
                    for landmark in self.atlas.landmarks
                    if landmark.id in marked
                ],
            )
            pairs = correspondences(self.atlas, view)
            if len(pairs["ids"]) < MIN_CORRESPONDENCES:
                continue
            fit = fit_pose(pairs, intrinsics)
            if fit is None:
                continue
            rvec, tvec = fit["rvec"], fit["tvec"]
            poses[name] = Pose(
                rvec=(float(rvec[0]), float(rvec[1]), float(rvec[2])),
                tvec_mm=(float(tvec[0]), float(tvec[1]), float(tvec[2])),
            )
        return poses
