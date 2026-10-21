"""The service's settings: the .env file, the environment, the checks, and the startup report.

Every test starts from no setting at all: the variables the developer's shell
may have are removed and no .env is read, so nothing here sees a real key.
"""

import logging
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from smc_perception import agent
from smc_perception.config import (
    ENV_FILE,
    ConfigError,
    check,
    env_file,
    model_settings,
    service_settings,
)

MODEL_VARIABLES = [
    "SMC_BEDROCK_REGION",
    "SMC_AGENT_MODEL",
    "SMC_AGENT_EFFORT",
    "SMC_AWS_AUTH",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
]
REQUIRED_VARIABLES = MODEL_VARIABLES[:4]
SERVICE_VARIABLES = [
    "SMC_WORKSPACE",
    "SMC_READ_ONLY",
    "CORS_ALLOWED_ORIGINS",
    "SMC_WORKSPACE_S3",
    "SMC_SESSIONS_TABLE",
]
# AWS's documented example key: gitleaks passes it, and any other AKIA… id looks real to it.
KEY_ID = "AKIAIOSFODNN7EXAMPLE"
SECRET = "wJalrXUtnFEMIK7MDENGbPxRfiCYEXAMPLEKEY01"
COMPLETE = (
    "SMC_BEDROCK_REGION=eu-central-1\nSMC_AGENT_MODEL=anthropic.claude-opus-5-5\n"
    "SMC_AGENT_EFFORT=low\nSMC_AWS_AUTH=keys\n"
    f"AWS_ACCESS_KEY_ID={KEY_ID}\nAWS_SECRET_ACCESS_KEY={SECRET}\n"
)


@pytest.fixture(autouse=True)
def nothing_set(monkeypatch: pytest.MonkeyPatch) -> None:
    for variable in MODEL_VARIABLES + SERVICE_VARIABLES:
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setenv("SMC_ENV_FILE", "")


def use_env_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, text: str) -> Path:
    path = tmp_path / "service.env"
    path.write_text(text, encoding="utf-8")
    monkeypatch.setenv("SMC_ENV_FILE", str(path))
    return path


def complete_but(*changes: tuple[str, str]) -> str:
    text = COMPLETE
    for old, new in changes:
        text = text.replace(old, new)
    return text


def messages(caplog: pytest.LogCaptureFixture) -> str:
    return "\n".join(record.getMessage() for record in caplog.records)


# ---- the example file --------------------------------------------------------------


def test_the_example_lists_exactly_the_model_settings() -> None:
    """Nothing the service does not read, and nothing it reads missing."""
    example = (ENV_FILE.parent / ".env.example").read_text(encoding="utf-8")
    names = [
        line.split("=", 1)[0]
        for line in example.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]

    assert names == MODEL_VARIABLES


# ---- the model settings: every one required --------------------------------------------


def test_the_env_file_is_read_and_the_environment_wins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    use_env_file(tmp_path, monkeypatch, COMPLETE)
    monkeypatch.setenv("SMC_AGENT_EFFORT", "high")

    found = model_settings()

    assert found.smc_bedrock_region == "eu-central-1"
    assert found.smc_agent_model == "anthropic.claude-opus-5-5"
    assert found.smc_agent_effort == "high"
    assert found.aws_access_key_id.get_secret_value() == KEY_ID


def test_the_env_file_is_the_service_s_unless_another_is_named(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SMC_ENV_FILE")
    assert env_file() == ENV_FILE
    assert ENV_FILE.parent.name == "perception"

    monkeypatch.setenv("SMC_ENV_FILE", "")
    assert env_file() is None


def test_with_nothing_set_every_model_setting_is_missing() -> None:
    """The keys are asked for once SMC_AWS_AUTH says they sign: see the start's tests."""
    with pytest.raises(ValidationError) as caught:
        model_settings()

    missing = [
        problem["loc"][0] for problem in caught.value.errors() if problem["type"] == "missing"
    ]
    assert [str(name).upper() for name in missing] == REQUIRED_VARIABLES


def test_an_empty_value_is_a_missing_value(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    use_env_file(
        tmp_path,
        monkeypatch,
        complete_but(("SMC_BEDROCK_REGION=eu-central-1", "SMC_BEDROCK_REGION=")),
    )

    with pytest.raises(ValidationError, match="smc_bedrock_region"):
        model_settings()


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (
            ("SMC_BEDROCK_REGION=eu-central-1", "SMC_BEDROCK_REGION=Frankfurt"),
            "such as eu-central-1",
        ),
        (("SMC_AGENT_EFFORT=low", "SMC_AGENT_EFFORT=maximum"), "smc_agent_effort"),
        ((f"AWS_ACCESS_KEY_ID={KEY_ID}", "AWS_ACCESS_KEY_ID=my-key"), "start with AKIA"),
    ],
)
def test_a_value_that_cannot_work_is_named(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: tuple[str, str], message: str
) -> None:
    use_env_file(tmp_path, monkeypatch, complete_but(change))

    with pytest.raises(ValidationError, match=message):
        model_settings()


def test_no_secret_is_ever_shown(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    use_env_file(
        tmp_path, monkeypatch, complete_but(("SMC_AGENT_EFFORT=low", "SMC_AGENT_EFFORT=bad"))
    )

    with pytest.raises(ValidationError) as caught:
        model_settings()

    assert SECRET not in str(caught.value)
    use_env_file(tmp_path, monkeypatch, COMPLETE)
    assert SECRET not in repr(model_settings())


# ---- the service settings: local defaults ---------------------------------------------


def test_the_service_runs_on_local_defaults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    found = service_settings()

    assert found.workspace_root == tmp_path.resolve()
    assert found.smc_read_only is False
    assert found.origins == ["http://localhost:3000"]


def test_the_service_settings_come_from_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SMC_WORKSPACE", str(tmp_path))
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://a.example, https://b.example")

    found = service_settings()

    assert found.workspace_root == tmp_path.resolve()
    assert found.origins == ["https://a.example", "https://b.example"]


@pytest.mark.parametrize("value", ["1", "true", "YES", " yes "])
def test_read_only_takes_the_usual_yes(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("SMC_READ_ONLY", value)

    assert service_settings().smc_read_only is True


# ---- the startup check ---------------------------------------------------------------


def test_the_start_logs_what_is_configured_and_never_a_secret(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    env = use_env_file(tmp_path, monkeypatch, COMPLETE)
    monkeypatch.setenv("SMC_WORKSPACE", str(tmp_path))
    caplog.set_level(logging.INFO)

    check()

    logged = messages(caplog)
    assert f"workspace {tmp_path.resolve()}" in logged
    assert (
        "agent model anthropic.claude-opus-5-5 in eu-central-1, effort low, "
        f"signed by AWS key AKIA…MPLE, from {env}"
    ) in logged
    assert "agent sessions in memory" in logged
    assert SECRET not in logged
    assert KEY_ID not in logged


def test_the_start_stops_and_lists_every_missing_variable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = use_env_file(tmp_path, monkeypatch, "SMC_AGENT_MODEL=anthropic.claude-opus-5-5\n")
    monkeypatch.setenv("SMC_WORKSPACE", str(tmp_path))

    with pytest.raises(ConfigError) as caught:
        check()

    assert str(caught.value) == (
        f"{env} is missing: SMC_BEDROCK_REGION, SMC_AGENT_EFFORT, SMC_AWS_AUTH "
        "- see services/perception/.env.example"
    )


def test_the_start_names_the_missing_and_the_invalid_apart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    use_env_file(
        tmp_path,
        monkeypatch,
        complete_but(
            ("SMC_BEDROCK_REGION=eu-central-1", "SMC_BEDROCK_REGION=Frankfurt"),
            ("SMC_AGENT_EFFORT=low\n", ""),
        ),
    )
    monkeypatch.setenv("SMC_WORKSPACE", str(tmp_path))

    with pytest.raises(ConfigError) as caught:
        check()

    assert (
        "is missing: SMC_AGENT_EFFORT - invalid: SMC_BEDROCK_REGION should be an AWS region"
        in str(caught.value)
    )


# ---- how the calls are signed ------------------------------------------------------------


def test_signing_with_keys_needs_both_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env = use_env_file(
        tmp_path, monkeypatch, complete_but((f"AWS_SECRET_ACCESS_KEY={SECRET}\n", ""))
    )
    monkeypatch.setenv("SMC_WORKSPACE", str(tmp_path))

    with pytest.raises(ConfigError) as caught:
        check()

    assert str(caught.value) == (
        f"{env} is missing: AWS_SECRET_ACCESS_KEY - see services/perception/.env.example"
    )


def test_the_task_role_signs_without_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    use_env_file(
        tmp_path,
        monkeypatch,
        "SMC_BEDROCK_REGION=eu-north-1\nSMC_AGENT_MODEL=eu.amazon.nova-2-lite-v1:0\n"
        "SMC_AGENT_EFFORT=low\nSMC_AWS_AUTH=role\n",
    )
    monkeypatch.setenv("SMC_WORKSPACE", str(tmp_path))
    caplog.set_level(logging.INFO)

    assert check().keys is None
    assert "signed by the task role" in messages(caplog)


def test_the_task_role_takes_no_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    use_env_file(tmp_path, monkeypatch, complete_but(("SMC_AWS_AUTH=keys", "SMC_AWS_AUTH=role")))
    monkeypatch.setenv("SMC_WORKSPACE", str(tmp_path))

    with pytest.raises(ConfigError, match="takes no keys"):
        check()


def test_only_keys_or_the_role_sign(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    use_env_file(tmp_path, monkeypatch, complete_but(("SMC_AWS_AUTH=keys", "SMC_AWS_AUTH=profile")))

    with pytest.raises(ValidationError, match="smc_aws_auth"):
        model_settings()


def test_a_missing_workspace_stops_the_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    use_env_file(tmp_path, monkeypatch, COMPLETE)
    monkeypatch.setenv("SMC_WORKSPACE", str(tmp_path / "nowhere"))

    with pytest.raises(ConfigError, match="is not a folder"):
        check()


# ---- the agent's model -----------------------------------------------------------------


def test_the_keys_go_to_the_bedrock_client_from_the_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A .env file is read into the settings, not the environment: the client gets the keys."""
    made: list[dict[str, Any]] = []
    monkeypatch.setattr(
        agent, "bedrock_model", lambda *args, **kwargs: made.append({"args": args, **kwargs})
    )
    agent._model.cache_clear()
    use_env_file(
        tmp_path, monkeypatch, complete_but(("SMC_AGENT_EFFORT=low", "SMC_AGENT_EFFORT=medium"))
    )

    agent.agent_model()
    agent._model.cache_clear()

    assert made == [
        {
            "args": ("eu-central-1", "anthropic.claude-opus-5-5", "medium"),
            "access_key": KEY_ID,
            "secret_key": SECRET,
        }
    ]
    assert agent.model_name() == "anthropic.claude-opus-5-5 (eu-central-1)"


def test_a_nova_model_goes_to_the_converse_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Claude's ids name anthropic; every other id is Amazon Nova, called through Converse."""
    made: list[dict[str, Any]] = []
    monkeypatch.setattr(
        agent, "nova_model", lambda *args, **kwargs: made.append({"args": args, **kwargs})
    )
    agent._model.cache_clear()
    use_env_file(
        tmp_path,
        monkeypatch,
        complete_but(("anthropic.claude-opus-5-5", "eu.amazon.nova-2-lite-v1:0")),
    )

    agent.agent_model()
    agent._model.cache_clear()

    assert made == [
        {
            "args": ("eu-central-1", "eu.amazon.nova-2-lite-v1:0", "low"),
            "access_key": KEY_ID,
            "secret_key": SECRET,
        }
    ]


def test_with_the_role_the_model_client_gets_no_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    made: list[dict[str, Any]] = []
    monkeypatch.setattr(
        agent, "nova_model", lambda *args, **kwargs: made.append({"args": args, **kwargs})
    )
    agent._model.cache_clear()
    use_env_file(
        tmp_path,
        monkeypatch,
        "SMC_BEDROCK_REGION=eu-north-1\nSMC_AGENT_MODEL=eu.amazon.nova-2-lite-v1:0\n"
        "SMC_AGENT_EFFORT=low\nSMC_AWS_AUTH=role\n",
    )

    agent.agent_model()
    agent._model.cache_clear()

    assert made == [
        {
            "args": ("eu-north-1", "eu.amazon.nova-2-lite-v1:0", "low"),
            "access_key": None,
            "secret_key": None,
        }
    ]


# ---- where sessions and the workspace live ------------------------------------------------


def test_sessions_live_in_memory_unless_a_table_is_named(monkeypatch: pytest.MonkeyPatch) -> None:
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph_checkpoint_aws import DynamoDBSaver

    agent._checkpointer.cache_clear()
    assert isinstance(agent.checkpointer(), InMemorySaver)

    monkeypatch.setenv("SMC_SESSIONS_TABLE", "smc-sessions")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "eu-north-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", KEY_ID)
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", SECRET)
    found = agent.checkpointer()
    agent._checkpointer.cache_clear()

    assert isinstance(found, DynamoDBSaver)


@pytest.mark.parametrize("url", ["https://bucket/prefix", "s3://", "s3://Bucket_Name/x"])
def test_the_workspace_s3_url_is_checked(monkeypatch: pytest.MonkeyPatch, url: str) -> None:
    monkeypatch.setenv("SMC_WORKSPACE_S3", url)

    with pytest.raises(ValidationError, match="smc_workspace_s3"):
        service_settings()


# ---- the daily cap on model calls ---------------------------------------------------


def test_without_a_cap_the_models_are_called_as_they_are(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SMC_MODEL_CALLS_PER_DAY", raising=False)

    assert agent.budget() is None


def test_a_cap_is_one_budget_for_the_process(monkeypatch: pytest.MonkeyPatch) -> None:
    agent._budget.cache_clear()
    monkeypatch.setenv("SMC_MODEL_CALLS_PER_DAY", "1000")

    first, again = agent.budget(), agent.budget()

    assert first is not None and first.limit == 1000
    assert first is again
