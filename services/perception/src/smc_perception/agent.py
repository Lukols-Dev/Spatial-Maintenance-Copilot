"""The agent's side of the service: its model, its sessions, its view of the workspace.

The agent (smc_agent) runs its loop over a Perception. Here that is the
workspace: one atlas and one view set, localised by the code /localise runs,
so a session and the Locate page give the same answer for the same view.

Sessions live in the checkpointer: in memory, where a restart of the service
ends them, or in the DynamoDB table SMC_SESSIONS_TABLE names, on AWS.
"""

from functools import cache, cached_property
from typing import Any, cast

import boto3
from botocore.config import Config
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph_checkpoint_aws import DynamoDBSaver
from smc_agent.bedrock import bedrock_model
from smc_agent.budget import BudgetedModel, BudgetedVision, DailyBudget
from smc_agent.contracts import Located
from smc_agent.model import ChatModel
from smc_agent.nova import nova_model
from smc_agent.vision import NovaVision, NoVision, VisionModel
from smc_core.contracts import Action, Atlas, Clicks, Pose
from smc_core.policy import DEFAULT_POLICY
from smc_core.viewpoints import (
    hidden_target_views,
    poses_from_clicks,
    suggested_viewpoints,
    truth_view,
)

from smc_perception.atlases import read_atlas
from smc_perception.cameras import find_intrinsics
from smc_perception.config import model_settings, service_settings
from smc_perception.localisation import localise_view
from smc_perception.models import LocaliseRequest, LocaliseResult
from smc_perception.view_sets import required_clicks
from smc_perception.workspace import WorkspaceFiles

# Sessions kept on AWS expire a week after their last step.
SESSION_TTL_S = 7 * 24 * 3600


@cache
def _checkpointer(table: str | None) -> BaseCheckpointSaver[Any]:
    if table is None:
        return InMemorySaver()
    return cast(
        BaseCheckpointSaver[Any], DynamoDBSaver(table_name=table, ttl_seconds=SESSION_TTL_S)
    )


def checkpointer() -> BaseCheckpointSaver[Any]:
    """Where sessions are kept between requests: the settings' DynamoDB table, else memory."""
    return _checkpointer(service_settings().smc_sessions_table)


@cache
def _model(
    region: str, model_id: str, effort: str, access_key: str | None, secret_key: str | None
) -> ChatModel:
    """Claude (anthropic.…, eu.anthropic.…) through the Messages API, Amazon Nova through Converse."""
    make = bedrock_model if "anthropic." in model_id else nova_model
    return make(region, model_id, effort, access_key=access_key, secret_key=secret_key)


@cache
def _budget(limit: int) -> DailyBudget:
    return DailyBudget(limit)


def budget() -> DailyBudget | None:
    """The day's cap on model calls the settings name, one for the process; None without one."""
    limit = service_settings().smc_model_calls_per_day
    return None if limit is None else _budget(limit)


def agent_model() -> ChatModel:
    """The model the settings name, one client per setting for the life of the process.

    The keys go to the client from the settings: a .env file is read into them,
    not into the environment botocore looks at. Without keys (SMC_AWS_AUTH=role)
    the client signs with the platform's credentials. With a daily cap, each
    call is taken from it first.
    """
    found = model_settings()
    access_key, secret_key = found.keys or (None, None)
    model = _model(
        found.smc_bedrock_region,
        found.smc_agent_model,
        found.smc_agent_effort,
        access_key,
        secret_key,
    )
    cap = budget()
    return model if cap is None else BudgetedModel(model, cap)


@cache
def _vision(
    region: str, model_id: str, access_key: str | None, secret_key: str | None
) -> VisionModel:
    if "anthropic." in model_id:
        return NoVision("the second look runs on Amazon Nova, and the agent's model is Claude")
    client = boto3.client(
        "bedrock-runtime",
        region_name=region,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=Config(read_timeout=120, retries={"total_max_attempts": 3}),
    )
    return NovaVision(client, model_id)


def vision_model() -> VisionModel:
    """The model that takes a second look at a frame: the agent's own Nova, one client per setting."""
    found = model_settings()
    access_key, secret_key = found.keys or (None, None)
    model = _vision(found.smc_bedrock_region, found.smc_agent_model, access_key, secret_key)
    cap = budget()
    return model if cap is None else BudgetedVision(model, cap)


def model_name() -> str:
    """Which model speaks for the agent, as the web app shows it."""
    found = model_settings()
    return f"{found.smc_agent_model} ({found.smc_bedrock_region})"


class WorkspacePerception:
    """One atlas and one view set of the workspace, as the agent asks about them.

    Viewpoints and their truths are those of smc_core.viewpoints, the ones the
    evaluation runs on. Results are kept for the life of the object, one request.
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
        return hidden_target_views(self.clicks, self.atlas)

    def suggest(self, view: str, action: Action) -> list[str]:
        return suggested_viewpoints(
            view, action, self.poses, self.clicks, self.atlas, DEFAULT_POLICY.min_inliers
        )

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
        return truth_view(view, self.clicks, self.atlas.target.id)

    @cached_property
    def poses(self) -> dict[str, Pose]:
        """Where each viewpoint's camera stood, from its clicks alone."""
        intrinsics = find_intrinsics(self.workspace, self.clicks.camera_id)
        return poses_from_clicks(self.viewpoints(), self.clicks, self.atlas, intrinsics)
