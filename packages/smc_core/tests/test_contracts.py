import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from smc_core.contracts import Atlas, Clicks, LandmarkObservation, View, load_atlas, load_clicks

ATLAS = {
    "asset_id": "test-car",
    "version": "1",
    "frame": "rig_board_a",
    "landmarks": [
        {"id": "headlight_inner", "position_mm": [120.0, -40.0, 15.0], "sigma_mm": 1.5},
        {"id": "badge_top", "position_mm": [0.0, -90.0, 30.0], "sigma_mm": 2.0},
    ],
    "target": {
        "id": "washer_pump",
        "position_mm": [300.0, 150.0, 420.0],
        "sigma_mm": 5.0,
        "extent_mm": [60.0, 40.0, 80.0],
    },
}


def test_load_atlas_reads_a_json_file(tmp_path: Path) -> None:
    path = tmp_path / "atlas.json"
    path.write_text(json.dumps(ATLAS), encoding="utf-8")

    atlas = load_atlas(path)

    assert [landmark.id for landmark in atlas.landmarks] == ["headlight_inner", "badge_top"]
    assert atlas.target.position_mm == (300.0, 150.0, 420.0)
    assert atlas.target.extent_mm == (60.0, 40.0, 80.0)


def test_atlas_rejects_a_misspelt_key() -> None:
    misspelt = {**ATLAS, "target": {**ATLAS["target"], "sigma_mn": 5.0}}

    with pytest.raises(ValidationError, match="sigma_mn"):
        Atlas.model_validate(misspelt)


def test_atlas_rejects_duplicate_landmark_ids() -> None:
    duplicated = {**ATLAS, "landmarks": [ATLAS["landmarks"][0], ATLAS["landmarks"][0]]}

    with pytest.raises(ValidationError, match="duplicate landmark ids"):
        Atlas.model_validate(duplicated)


def test_view_rejects_a_landmark_observed_twice() -> None:
    observation = LandmarkObservation(landmark_id="badge_top", pixel=(10.0, 20.0), sigma_px=1.0)

    with pytest.raises(ValidationError, match="observed more than once"):
        View(view_id="v1", camera_id="phone", observations=[observation, observation])


def test_clicks_without_a_points_list_still_load(tmp_path: Path) -> None:
    path = tmp_path / "clicks.json"
    path.write_text('{"camera_id": "phone", "views": {"v.png": {"drone": [1, 2]}}}', "utf-8")

    clicks = load_clicks(path)

    assert clicks.points == []
    assert clicks.views == {"v.png": {"drone": (1.0, 2.0)}}


def test_clicks_keep_the_points_in_order_clicked_or_not() -> None:
    clicks = Clicks(
        camera_id="phone", points=["hinge", "drone"], views={"v.png": {"drone": (1, 2)}}
    )

    assert clicks.points == ["hinge", "drone"]
    assert list(Clicks.model_validate_json(clicks.model_dump_json()).points) == ["hinge", "drone"]


def test_clicks_reject_a_point_listed_twice() -> None:
    with pytest.raises(ValidationError, match=r"points listed more than once: \['drone'\]"):
        Clicks(camera_id="phone", points=["drone", "hinge", "drone"], views={})


def test_clicks_reject_a_clicked_point_missing_from_the_list() -> None:
    with pytest.raises(ValidationError, match=r"clicked points missing from points: \['handle'\]"):
        Clicks(camera_id="phone", points=["drone"], views={"v.png": {"handle": (1, 2)}})


def test_clicks_reject_a_pixel_that_is_not_a_number() -> None:
    with pytest.raises(ValidationError, match="finite number"):
        Clicks(camera_id="phone", views={"v.png": {"drone": (float("nan"), 2.0)}})
