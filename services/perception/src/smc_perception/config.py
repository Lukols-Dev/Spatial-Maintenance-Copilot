"""The service's settings, checked at startup.

Two groups, read the same way: field name = environment variable name,
case-insensitive, and a variable set in the environment wins.

- ModelSettings: the agent's model and its keys, from services/perception/.env.
  Every one is required; .env.example lists exactly these.
- ServiceSettings: how the service runs, set by `make api` and by the
  deployment, with local defaults. No secrets, so no file.

Both are read on every call, not once at import, so a test points the service
at a temporary workspace with monkeypatch.setenv. SMC_ENV_FILE names another
.env, or none when empty: the tests read none.

check() runs when the service starts: it logs what is configured and stops the
start with every missing or invalid variable named.
"""

import logging
import os
import re
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

SERVICE_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = SERVICE_DIR / ".env"

AWS_REGION = re.compile(r"^[a-z]{2}(-gov)?-[a-z]+-\d+$")
Effort = Literal["low", "medium", "high", "xhigh", "max"]


class ConfigError(Exception):
    """The service cannot start with these settings; the message names what to add or change."""


class ModelSettings(BaseSettings):
    """The agent's model on Amazon Bedrock, Nova or Claude, and the keys of an IAM user allowed to call it."""

    model_config = SettingsConfigDict(
        env_ignore_empty=True,
        str_strip_whitespace=True,
        extra="ignore",
        hide_input_in_errors=True,
    )

    smc_bedrock_region: str
    smc_agent_model: str = Field(min_length=1)
    smc_agent_effort: Effort
    aws_access_key_id: SecretStr
    aws_secret_access_key: SecretStr

    @field_validator("smc_bedrock_region")
    @classmethod
    def _check_region(cls, value: str) -> str:
        if not AWS_REGION.match(value):
            raise ValueError("should be an AWS region, such as eu-central-1")
        return value

    @field_validator("aws_access_key_id")
    @classmethod
    def _check_key_id(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().startswith("AKIA"):
            raise ValueError("should start with AKIA, as the key of an IAM user does")
        return value


class ServiceSettings(BaseSettings):
    """How the service runs: its workspace, whether it writes, and who may call it."""

    model_config = SettingsConfigDict(
        env_ignore_empty=True, str_strip_whitespace=True, extra="ignore"
    )

    smc_workspace: Path | None = Field(default=None, description="the working directory when unset")
    smc_read_only: bool = False
    cors_allowed_origins: str = Field(
        default="http://localhost:3000", description="comma-separated web origins"
    )

    @field_validator("smc_read_only", mode="before")
    @classmethod
    def _strip_flag(cls, value: object) -> object:
        """A flag of " yes " is yes: str_strip_whitespace covers str fields, not a bool from text."""
        return value.strip() if isinstance(value, str) else value

    @property
    def workspace_root(self) -> Path:
        """The folder that holds calib/ and data/, symlinks resolved for every containment check."""
        root = self.smc_workspace.expanduser() if self.smc_workspace else Path.cwd()
        return root.resolve()

    @property
    def origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]


def env_file() -> Path | None:
    """The .env of the model settings: SMC_ENV_FILE, else services/perception/.env."""
    configured = os.environ.get("SMC_ENV_FILE")
    if configured is None:
        return ENV_FILE
    return Path(configured).expanduser() if configured.strip() else None


def model_settings() -> ModelSettings:
    return ModelSettings(_env_file=env_file())  # type: ignore[call-arg]


def service_settings() -> ServiceSettings:
    return ServiceSettings()


# ---- what the rest of the service reads -------------------------------------------


def workspace_root() -> Path:
    return service_settings().workspace_root


def read_only() -> bool:
    """Whether writes are refused. The public deployment runs read-only."""
    return service_settings().smc_read_only


def allowed_origins() -> list[str]:
    """Web origins allowed to call the API: the CloudFront domain when deployed."""
    return service_settings().origins


# ---- the startup check ---------------------------------------------------------------


def describe(error: ValidationError, file: Path | None) -> str:
    """Every problem by its variable: the missing ones in one list, then the invalid ones."""
    missing: list[str] = []
    invalid: list[str] = []
    for problem in error.errors(include_url=False, include_input=False):
        name = ".".join(str(part) for part in problem["loc"]).upper()
        if problem["type"] == "missing":
            missing.append(name)
        else:
            invalid.append(f"{name} {problem['msg'].removeprefix('Value error, ')}")
    where = file if file is not None else "the environment"
    parts = []
    if missing:
        parts.append(f"{where} is missing: {', '.join(missing)}")
    if invalid:
        parts.append(f"invalid: {'; '.join(invalid)}")
    return " - ".join(parts) + " - see services/perception/.env.example"


def masked(key: SecretStr) -> str:
    """An access key id as the AWS console shows it, enough to tell keys apart."""
    value = key.get_secret_value()
    return f"{value[:4]}…{value[-4:]}"


def check() -> ModelSettings:
    """Read the settings once, log what they configure, and stop on any that is missing or invalid."""
    try:
        service = service_settings()
    except ValidationError as error:
        raise ConfigError(describe(error, None)) from error
    root = service.workspace_root
    if not root.is_dir():
        raise ConfigError(f"SMC_WORKSPACE={root} is not a folder")
    logger.info("✅ workspace %s%s", root, " (read-only)" if service.smc_read_only else "")
    logger.info("✅ CORS origins: %s", ", ".join(service.origins) or "none")

    file = env_file()
    try:
        model = model_settings()
    except ValidationError as error:
        raise ConfigError(describe(error, file)) from error
    logger.info(
        "✅ agent model %s in %s, effort %s, AWS key %s, from %s",
        model.smc_agent_model,
        model.smc_bedrock_region,
        model.smc_agent_effort,
        masked(model.aws_access_key_id),
        file if file is not None and file.is_file() else "the environment",
    )
    return model


def configure_logging() -> None:
    """INFO for the service's own messages; HTTP clients log every request, so less for them."""
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    for noisy in ("httpx", "httpx2", "botocore", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
