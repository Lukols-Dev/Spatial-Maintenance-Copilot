"""Configuration from the environment.

Every value is read when it is needed, not at import, so a test can point the
service at a temporary workspace with monkeypatch.setenv. CORS is the
exception: the middleware takes its origins once, when the app is built.
"""

import os
from pathlib import Path

TRUTHY = {"1", "true", "yes"}


def workspace_root() -> Path:
    """The folder that holds calib/ and data/: SMC_WORKSPACE, else the working directory.

    Symlinks are resolved here, so every containment check compares real paths.
    """
    configured = os.environ.get("SMC_WORKSPACE", "").strip()
    return (Path(configured).expanduser() if configured else Path.cwd()).resolve()


def read_only() -> bool:
    """Whether writes are refused: SMC_READ_ONLY set to 1, true or yes.

    The public deployment runs read-only, so visitors see the workspace as it
    was left and cannot change it.
    """
    return os.environ.get("SMC_READ_ONLY", "").strip().lower() in TRUTHY


def allowed_origins() -> list[str]:
    """Web origins allowed to call the API.

    CORS_ALLOWED_ORIGINS holds a comma-separated list, e.g. the CloudFront domain
    in the deployed task. Without it, only the local Next.js dev server may call.
    """
    origins = os.environ.get("CORS_ALLOWED_ORIGINS", "http://localhost:3000")
    return [origin.strip() for origin in origins.split(",") if origin.strip()]
