"""The workspace copied from S3 at startup, with a fake S3 client: nothing reaches AWS."""

from pathlib import Path
from typing import Any

import pytest
from smc_perception.workspace_sync import copy_workspace, split_s3_url


class FakeS3:
    def __init__(self, objects: dict[str, bytes]) -> None:
        self.objects = objects
        self.asked: list[dict[str, str]] = []

    def get_paginator(self, name: str) -> FakeS3:
        assert name == "list_objects_v2"
        return self

    def paginate(self, Bucket: str, Prefix: str) -> list[dict[str, Any]]:
        self.asked.append({"Bucket": Bucket, "Prefix": Prefix})
        keys = sorted(key for key in self.objects if key.startswith(Prefix))
        return [
            {"Contents": [{"Key": key} for key in keys[:2]]},
            {"Contents": [{"Key": key} for key in keys[2:]]},
        ]

    def download_file(self, bucket: str, key: str, target: str) -> None:
        Path(target).write_bytes(self.objects[key])


def test_an_s3_url_is_a_bucket_and_a_prefix() -> None:
    assert split_s3_url("s3://smc-data/workspace/") == ("smc-data", "workspace/")
    assert split_s3_url("s3://smc-data/a/b") == ("smc-data", "a/b/")
    assert split_s3_url("s3://smc-data") == ("smc-data", "")


def test_every_object_under_the_prefix_lands_at_its_path(tmp_path: Path) -> None:
    client = FakeS3(
        {
            "workspace/calib/rig.yaml": b"rig",
            "workspace/data/atlas/szafka.json": b"{}",
            "workspace/data/views/demo/": b"",
            "workspace/data/views/demo/a.png": b"png",
            "other/secret.txt": b"no",
        }
    )

    copied = copy_workspace(client, "s3://smc-data/workspace", tmp_path)

    assert copied == 3
    assert client.asked == [{"Bucket": "smc-data", "Prefix": "workspace/"}]
    assert (tmp_path / "calib" / "rig.yaml").read_bytes() == b"rig"
    assert (tmp_path / "data" / "views" / "demo" / "a.png").read_bytes() == b"png"
    assert not (tmp_path / "secret.txt").exists()


def test_a_key_that_would_land_outside_the_workspace_is_refused(tmp_path: Path) -> None:
    client = FakeS3({"workspace/../../etc/passwd": b"x"})

    with pytest.raises(ValueError, match="outside the workspace"):
        copy_workspace(client, "s3://smc-data/workspace", tmp_path / "root")
