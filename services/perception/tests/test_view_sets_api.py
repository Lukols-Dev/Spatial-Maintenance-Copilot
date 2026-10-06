"""View sets: importing one, reading it, serving its images, saving its clicks."""

import json
import os
from pathlib import Path
from typing import Any

import cv2 as cv
import numpy as np
import pytest
from fastapi.testclient import TestClient
from smc_core.testing import CAMERA_ID
from workspace_builder import write_image, write_view_set

PNG = "image/png"


def write_clip(path: Path) -> Path:
    """Six 64x48 frames, sharp only at 1 and 4, as the export test of the CLI writes."""
    writer = cv.VideoWriter(str(path), cv.VideoWriter.fourcc(*"MJPG"), 30.0, (64, 48))
    pattern = np.kron([[0, 255], [255, 0]], np.ones((6, 8))).astype(np.uint8)
    sharp = cv.cvtColor(np.tile(pattern, (4, 4)), cv.COLOR_GRAY2BGR)
    for index in range(6):
        writer.write(sharp if index in (1, 4) else cv.GaussianBlur(sharp, (0, 0), 3))
    writer.release()
    return path


def upload(
    client: TestClient, name: str, files: list[Path | tuple[str, bytes]], **form: str
) -> Any:
    parts = [
        ("files", (item.name, item.read_bytes()) if isinstance(item, Path) else item)
        for item in files
    ]
    return client.post("/view-sets", data={"name": name, **form}, files=parts)


def leftovers(root: Path) -> list[str]:
    views = root / "data" / "views"
    return sorted(path.name for path in views.iterdir()) if views.is_dir() else []


# ---- import --------------------------------------------------------------------


def test_a_video_becomes_the_sharpest_frame_of_every_window(
    calib: Path, client: TestClient, tmp_path: Path
) -> None:
    clip = write_clip(tmp_path / "clip.avi")

    response = upload(client, "clip", [clip], window="3")

    assert response.status_code == 201, response.text
    summary = response.json()
    assert summary["name"] == "clip"
    assert (summary["image_count"], summary["jpeg_count"]) == (2, 0)
    assert summary["image_size"] == [64, 48]
    assert summary["camera_ids"] == []
    assert summary["clicks"] is None
    folder = calib / "data" / "views" / "clip"
    assert sorted(path.name for path in folder.iterdir()) == [
        "frame_000001.png",
        "frame_000004.png",
    ]
    assert leftovers(calib) == ["clip"]


def test_photos_become_png_in_their_sensor_grid(
    calib: Path, client: TestClient, tmp_path: Path
) -> None:
    rotated = write_image(tmp_path / "IMG_0001.JPG", 1080, 1920, exif=True)
    plain = write_image(tmp_path / "IMG_0002.png", 1080, 1920)

    response = upload(client, "photos", [rotated, plain])

    assert response.status_code == 201, response.text
    assert response.json()["image_size"] == [1080, 1920]
    assert response.json()["camera_ids"] == [CAMERA_ID]
    folder = calib / "data" / "views" / "photos"
    assert sorted(path.name for path in folder.iterdir()) == ["IMG_0001.png", "IMG_0002.png"]
    assert cv.imread(str(folder / "IMG_0001.png")).shape == (1920, 1080, 3)


def test_the_folder_a_browser_sends_with_a_file_name_is_dropped(
    root: Path, client: TestClient, tmp_path: Path
) -> None:
    photo = write_image(tmp_path / "a.png", 40, 30).read_bytes()

    response = upload(client, "set", [("trip/day 1/a.png", photo)])

    assert response.status_code == 201, response.text
    assert [path.name for path in (root / "data" / "views" / "set").iterdir()] == ["a.png"]


@pytest.mark.parametrize(
    ("files", "message"),
    [
        (["a.jpg", "a.png"], "these would give the same PNG file: a.jpg, a.png"),
        (["IMG_1.png", "img_1.PNG"], "these would give the same PNG file: IMG_1.png, img_1.PNG"),
        (["clip.mov", "a.png"], "upload either one video or photos"),
        (["one.mp4", "two.mp4"], "upload either one video or photos"),
        (["notes.txt"], "unsupported file type: notes.txt"),
        (["photo (1).png"], "file names not allowed: photo (1).png"),
        ([".hidden.png"], "file names not allowed: .hidden.png"),
    ],
)
def test_an_upload_that_is_not_one_video_or_photos_is_refused(
    root: Path, client: TestClient, files: list[str], message: str
) -> None:
    response = upload(client, "set", [(name, b"0") for name in files])

    assert response.status_code == 422
    assert response.json()["detail"].startswith(message)
    assert leftovers(root) == []


def test_a_file_that_is_not_an_image_is_refused_and_nothing_is_left(
    root: Path, client: TestClient, tmp_path: Path
) -> None:
    good = write_image(tmp_path / "a.png", 40, 30)

    response = upload(client, "set", [good, ("b.jpg", b"not a jpeg")])

    assert response.status_code == 422
    assert response.json()["detail"] == "cannot read image: b.jpg"
    assert leftovers(root) == []


def test_a_file_that_is_not_a_video_is_refused(root: Path, client: TestClient) -> None:
    response = upload(client, "set", [("clip.mov", b"not a video")])

    assert response.status_code == 422
    assert response.json()["detail"] == "cannot read clip.mov as a video"
    assert leftovers(root) == []


def test_a_video_without_frames_is_refused(root: Path, client: TestClient, tmp_path: Path) -> None:
    clip = write_clip(tmp_path / "clip.avi")
    cut = clip.read_bytes()[:4096]  # the header survives, the frames do not

    response = upload(client, "set", [("clip.avi", cut)])

    assert response.status_code == 422
    assert "clip.avi" in response.json()["detail"]
    assert leftovers(root) == []


def test_an_existing_set_is_not_replaced(root: Path, client: TestClient, tmp_path: Path) -> None:
    write_view_set(root, "cabinet", {"old.png": (40, 30)})

    response = upload(client, "cabinet", [write_image(tmp_path / "new.png", 40, 30)])

    assert response.status_code == 409
    assert response.json()["detail"] == "view set 'cabinet' already exists"
    assert leftovers(root) == ["cabinet"]
    assert [path.name for path in (root / "data" / "views" / "cabinet").iterdir()] == ["old.png"]


@pytest.mark.parametrize("name", ["..", ".hidden", "a/b", "a b", "x" * 65, ""])
def test_a_set_name_that_is_not_a_plain_name_is_refused(
    root: Path, client: TestClient, tmp_path: Path, name: str
) -> None:
    response = upload(client, name, [write_image(tmp_path / "a.png", 40, 30)])

    assert response.status_code == 422
    assert leftovers(root) == []


def test_an_import_needs_files_and_a_window_of_one_or_more(
    root: Path, client: TestClient, tmp_path: Path
) -> None:
    assert client.post("/view-sets", data={"name": "set"}).status_code == 422
    clip = write_clip(tmp_path / "clip.avi")
    assert upload(client, "set", [clip], window="0").status_code == 422
    assert leftovers(root) == []


# ---- reading -------------------------------------------------------------------


def test_a_set_lists_its_images_by_name_with_their_sizes(calib: Path, client: TestClient) -> None:
    folder = write_view_set(calib, "cabinet", {"b.png": (1080, 1920), "a.png": (1080, 1920)})
    write_image(folder / "c.jpeg", 40, 30, exif=True)

    response = client.get("/view-sets/cabinet")

    assert response.status_code == 200
    assert response.json() == {
        "name": "cabinet",
        "images": [
            {"file": "a.png", "width": 1080, "height": 1920, "format": "png", "error": None},
            {"file": "b.png", "width": 1080, "height": 1920, "format": "png", "error": None},
            {"file": "c.jpeg", "width": 40, "height": 30, "format": "jpeg", "error": None},
        ],
        "clicks": None,
        "clicks_error": None,
    }


def test_a_set_returns_its_clicks_or_why_they_cannot_be_read(
    calib: Path, client: TestClient
) -> None:
    folder = write_view_set(calib, "cabinet", {"a.png": (40, 30)})
    clicks = {
        "camera_id": CAMERA_ID,
        "points": ["drone"],
        "views": {"a.png": {"drone": [1.5, 2.5]}},
    }
    (folder / "clicks.json").write_text(json.dumps(clicks))

    assert client.get("/view-sets/cabinet").json()["clicks"] == clicks

    (folder / "clicks.json").write_text('{"camera_id": "x", "points": ["a", "a"], "views": {}}')
    body = client.get("/view-sets/cabinet").json()
    assert body["clicks"] is None
    assert body["clicks_error"] == (
        "data/views/cabinet/clicks.json is not valid: points listed more than once: ['a']"
    )


def test_an_unknown_set_is_not_found(root: Path, client: TestClient) -> None:
    response = client.get("/view-sets/cabinet")

    assert response.status_code == 404
    assert response.json()["detail"] == "no view set named 'cabinet'"


def test_an_image_is_served_with_its_type(calib: Path, client: TestClient) -> None:
    folder = write_view_set(calib, "cabinet", {"a.png": (40, 30)})
    write_image(folder / "b.JPG", 40, 30)

    png = client.get("/view-sets/cabinet/images/a.png")
    jpeg = client.get("/view-sets/cabinet/images/b.JPG")

    assert png.status_code == 200
    assert png.headers["content-type"] == PNG
    assert png.content == (folder / "a.png").read_bytes()
    assert jpeg.headers["content-type"] == "image/jpeg"
    assert client.get("/view-sets/cabinet/images/c.png").status_code == 404
    assert client.get("/view-sets/cabinet/images/clicks.json").status_code == 422


# ---- paths that lead elsewhere ---------------------------------------------------


@pytest.fixture
def secret(tmp_path: Path) -> Path:
    """A file outside the workspace that no request may reach."""
    path = write_image(tmp_path / "outside" / "secret.png", 40, 30)
    (tmp_path / "outside" / "secret.txt").write_text("secret")
    return path


@pytest.mark.parametrize(
    "url",
    [
        "/view-sets/%2E%2E",
        "/view-sets/%2E%2E/images/rig.yaml",
        "/view-sets/..%2F..%2Fcalib/images/rig.yaml",
        "/view-sets/cabinet/images/..%2F..%2F..%2Fcalib%2Frig.yaml",
        "/view-sets/cabinet/images/%2E%2E%2Fsecret.png",
        "/view-sets/cabinet/images/..%5C..%5Csecret.png",
        "/view-sets/cabinet/images/%2Ftmp%2Fsecret.png",
        "/view-sets/%2Ftmp/images/secret.png",
        "/view-sets/escape",
        "/view-sets/escape/images/secret.png",
        "/view-sets/cabinet/images/leak.png",
    ],
)
def test_no_request_reaches_outside_the_workspace(
    calib: Path, client: TestClient, secret: Path, url: str
) -> None:
    folder = write_view_set(calib, "cabinet", {"a.png": (40, 30)})
    os.symlink(secret.parent, calib / "data" / "views" / "escape")
    os.symlink(secret, folder / "leak.png")

    response = client.get(url)

    assert response.status_code in (404, 422), (url, response.status_code)
    assert response.content != secret.read_bytes()
    assert str(secret.parent) not in response.text


def test_a_symlinked_image_that_leads_out_is_not_listed(
    calib: Path, client: TestClient, secret: Path
) -> None:
    folder = write_view_set(calib, "cabinet", {"a.png": (40, 30)})
    os.symlink(secret, folder / "leak.png")

    images = client.get("/view-sets/cabinet").json()["images"]

    assert [image["file"] for image in images] == ["a.png"]


# ---- clicks ----------------------------------------------------------------------


def test_clicks_are_saved_as_the_annotator_sent_them(calib: Path, client: TestClient) -> None:
    folder = write_view_set(calib, "cabinet", {"a.png": (40, 30), "b.png": (40, 30)})
    clicks = {
        "camera_id": CAMERA_ID,
        "points": ["hinge", "drone"],
        "views": {"a.png": {"drone": [1.5, 2.25], "hinge": [3, 4]}, "b.png": {"drone": [5, 6]}},
    }

    response = client.put("/view-sets/cabinet/clicks", json=clicks)

    assert response.status_code == 200, response.text
    summary = response.json()
    assert summary["point_views"] == {"hinge": 1, "drone": 2}
    assert (summary["point_count"], summary["marked_images"], summary["ready_points"]) == (2, 2, 1)
    text = (folder / "clicks.json").read_text()
    assert text.endswith("}\n")
    assert text.startswith('{\n  "camera_id": "phone-1x-portrait",\n  "points": [\n    "hinge",')
    assert json.loads(text)["views"]["a.png"]["drone"] == [1.5, 2.25]
    assert client.get("/view-sets/cabinet").json()["clicks"]["points"] == ["hinge", "drone"]


def test_a_draft_without_a_camera_is_saved(calib: Path, client: TestClient) -> None:
    write_view_set(calib, "cabinet", {"a.png": (40, 30)})

    response = client.put("/view-sets/cabinet/clicks", json={"camera_id": "", "views": {}})

    assert response.status_code == 200
    assert response.json()["camera_id"] == ""


def test_clicks_on_images_the_set_does_not_have_are_refused(
    calib: Path, client: TestClient
) -> None:
    folder = write_view_set(calib, "cabinet", {"a.png": (40, 30)})
    clicks = {"camera_id": "", "views": {"a.png": {}, "z.png": {"p": [1, 2]}, "y.png": {}}}

    response = client.put("/view-sets/cabinet/clicks", json=clicks)

    assert response.status_code == 422
    assert response.json()["detail"] == "not images of view set 'cabinet': y.png, z.png"
    assert not (folder / "clicks.json").exists()


@pytest.mark.parametrize(
    "body",
    [
        '{"camera_id": "", "points": ["p", "p"], "views": {}}',
        '{"camera_id": "", "points": ["p"], "views": {"a.png": {"q": [1, 2]}}}',
        '{"camera_id": "", "views": {"a.png": {"p": [NaN, 2]}}}',
        '{"camera_id": "", "views": {"a.png": {"p": [1]}}}',
        '{"views": {}}',
    ],
)
def test_clicks_that_break_the_contract_are_refused(
    calib: Path, client: TestClient, body: str
) -> None:
    folder = write_view_set(calib, "cabinet", {"a.png": (40, 30)})

    response = client.put(
        "/view-sets/cabinet/clicks", content=body, headers={"Content-Type": "application/json"}
    )

    assert response.status_code == 422
    assert not (folder / "clicks.json").exists()


def test_clicks_for_an_unknown_set_are_not_found(root: Path, client: TestClient) -> None:
    response = client.put("/view-sets/cabinet/clicks", json={"camera_id": "", "views": {}})

    assert response.status_code == 404


# ---- read-only -------------------------------------------------------------------


def test_a_read_only_service_imports_nothing_and_saves_no_clicks(
    calib: Path, client: TestClient, read_only: None, tmp_path: Path
) -> None:
    write_view_set(calib, "cabinet", {"a.png": (40, 30)})

    imported = upload(client, "new", [write_image(tmp_path / "b.png", 40, 30)])
    saved = client.put("/view-sets/cabinet/clicks", json={"camera_id": "", "views": {}})

    assert (imported.status_code, saved.status_code) == (403, 403)
    assert saved.json()["detail"] == "the service is read-only"
    assert leftovers(calib) == ["cabinet"]
    assert not (calib / "data" / "views" / "cabinet" / "clicks.json").exists()
    assert client.get("/view-sets/cabinet/images/a.png").status_code == 200
