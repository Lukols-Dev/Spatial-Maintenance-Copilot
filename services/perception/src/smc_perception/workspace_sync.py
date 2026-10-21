"""The workspace read from S3 at startup, for a container that starts empty.

On AWS the container has no workspace of its own: the calibration, the rig
file, the atlases and the view sets the demo shows sit in a private bucket.
At startup every object under SMC_WORKSPACE_S3 is copied to the same path
under the workspace folder, before the settings are checked. The service
then reads them as it reads a local workspace, and writes nothing back: the
deployment runs read-only.
"""

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def split_s3_url(url: str) -> tuple[str, str]:
    """s3://bucket/prefix as (bucket, prefix), the prefix ending in "/" unless empty."""
    bucket, _, prefix = url.removeprefix("s3://").partition("/")
    prefix = prefix.strip("/")
    return bucket, f"{prefix}/" if prefix else ""


def copy_workspace(client: Any, url: str, root: Path) -> int:
    """Copy every object under url to the same path under root; the number copied.

    client is boto3's S3 client, typed Any as boto3 has no types. A key that
    would land outside root is refused.
    """
    bucket, prefix = split_s3_url(url)
    root = root.resolve()
    copied = 0
    for page in client.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
        for item in page.get("Contents", []):
            key = item["Key"]
            relative = key[len(prefix) :]
            if not relative or relative.endswith("/"):
                continue
            target = (root / relative).resolve()
            if not target.is_relative_to(root):
                raise ValueError(f"s3://{bucket}/{key} would land outside the workspace")
            target.parent.mkdir(parents=True, exist_ok=True)
            client.download_file(bucket, key, str(target))
            copied += 1
    logger.info("✅ copied %d files from %s to %s", copied, url, root)
    return copied
