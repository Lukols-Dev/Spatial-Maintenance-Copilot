"""PUT /boards/{id}/measurement: a caliper reading written into calib/rig.yaml in place."""

import stat
from datetime import date
from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient
from workspace_builder import RIG_YAML, write_rig

MEASUREMENT = {
    "square_measured_mm": 25.02,
    "measurement_uncertainty_mm": 0.02,
    "marker_measured_mm": 18.01,
    "substrate": "A4 print on foam board",
    "measured_on": "2026-10-06",
}


def measure(client: TestClient, board: str = "rig_board_a", **changes: Any) -> Any:
    return client.put(f"/boards/{board}/measurement", json={**MEASUREMENT, **changes})


def test_a_measurement_changes_only_the_values_of_that_board(
    calib: Path, client: TestClient
) -> None:
    response = measure(client)

    assert response.status_code == 200, response.text
    assert response.json() == {
        "id": "rig_board_a",
        "squares_x": 4,
        "squares_y": 6,
        "marker_ids": [20, 31],
        "square_nominal_mm": 25.0,
        "marker_nominal_mm": 18.0,
        "square_measured_mm": 25.02,
        "marker_measured_mm": 18.01,
        "measurement_uncertainty_mm": 0.02,
        "substrate": "A4 print on foam board",
        "measured_on": "2026-10-06",
        "measured": True,
    }
    board_a = RIG_YAML.index("  rig_board_a:")
    expected = RIG_YAML[:board_a] + RIG_YAML[board_a:].replace(
        """\
    square_measured_mm: null
    marker_measured_mm: null
    measurement_uncertainty_mm: null
    substrate: null
    measured_on: null
""",
        """\
    square_measured_mm: 25.02
    marker_measured_mm: 18.01
    measurement_uncertainty_mm: 0.02
    substrate: "A4 print on foam board"
    measured_on: 2026-10-06
""",
        1,
    )
    assert (calib / "calib" / "rig.yaml").read_text() == expected


def test_the_measured_board_is_what_the_workspace_lists(calib: Path, client: TestClient) -> None:
    board = measure(client, board="rig_board_b").json()

    listed = client.get("/workspace").json()["rig"]["boards"]

    assert listed[2] == board
    assert listed[1]["measured"] is False


def test_the_date_defaults_to_today_and_a_blank_substrate_to_null(
    calib: Path, client: TestClient
) -> None:
    body = {"square_measured_mm": 24.9, "measurement_uncertainty_mm": 0.1, "substrate": "  "}

    response = client.put("/boards/rig_board_a/measurement", json=body)

    assert response.json()["measured_on"] == date.today().isoformat()
    assert response.json()["substrate"] is None
    assert response.json()["marker_measured_mm"] is None


@pytest.mark.parametrize(
    "substrate",
    ['glued "flat" to the side', "C:\\boards\\a", "line one\nline two", "Łódź, 25 µm ✓"],
)
def test_any_substrate_text_reads_back_the_same(
    calib: Path, client: TestClient, substrate: str
) -> None:
    measure(client, substrate=substrate)

    text = (calib / "calib" / "rig.yaml").read_text(encoding="utf-8")
    board_a = text[text.index("  rig_board_a:") :]
    line = next(line for line in board_a.splitlines() if line.startswith("    substrate:"))
    assert line.startswith('    substrate: "') and line.endswith('"')
    assert yaml.safe_load(text)["boards"]["rig_board_a"]["substrate"] == substrate
    assert client.get("/workspace").json()["rig"]["boards"][1]["substrate"] == substrate


def test_missing_keys_are_added_after_the_last_key_of_the_board(
    root: Path, client: TestClient
) -> None:
    old_rig = """\
dictionary: DICT_5X5_100
boards:
  rig_board_a:
    squares_x: 4
    squares_y: 6
    ids: [20, 31] # inclusive range
    square_nominal_mm: 25.0
    marker_nominal_mm: 18.0
    square_measured_mm: null   # caliper, one square

  # the second board sits on the left side
  rig_board_b:
    squares_x: 4
    squares_y: 6
    ids: [35, 46]
    square_nominal_mm: 25.0
    marker_nominal_mm: 18.0
"""
    write_rig(root, old_rig)

    response = measure(client)

    assert response.status_code == 200, response.text
    assert (root / "calib" / "rig.yaml").read_text() == old_rig.replace(
        """\
    square_measured_mm: null   # caliper, one square
""",
        """\
    square_measured_mm: 25.02   # caliper, one square
    marker_measured_mm: 18.01
    measurement_uncertainty_mm: 0.02
    substrate: "A4 print on foam board"
    measured_on: 2026-10-06
""",
    )


def test_windows_line_endings_and_a_last_line_without_one_are_kept(
    root: Path, client: TestClient
) -> None:
    rig = RIG_YAML.removesuffix("\n").replace("\n", "\r\n")
    write_rig(root, rig)

    measure(client, board="rig_board_b")

    board_b = rig.index("  rig_board_b:")
    unmeasured = (
        "    square_measured_mm: null\r\n    marker_measured_mm: null\r\n"
        "    measurement_uncertainty_mm: null\r\n    substrate: null\r\n    measured_on: null"
    )
    measured = (
        "    square_measured_mm: 25.02\r\n    marker_measured_mm: 18.01\r\n"
        '    measurement_uncertainty_mm: 0.02\r\n    substrate: "A4 print on foam board"\r\n'
        "    measured_on: 2026-10-06"
    )
    expected = rig[:board_b] + rig[board_b:].replace(unmeasured, measured)
    assert (root / "calib" / "rig.yaml").read_bytes().decode() == expected


def test_the_file_keeps_its_permissions(calib: Path, client: TestClient) -> None:
    rig = calib / "calib" / "rig.yaml"
    rig.chmod(0o640)

    measure(client)

    assert stat.S_IMODE(rig.stat().st_mode) == 0o640
    assert not [path.name for path in rig.parent.iterdir() if path.name.startswith(".")]


@pytest.mark.parametrize("square", [100.08, 19.0, 31.5])
def test_an_implausible_square_is_refused_with_both_values(
    calib: Path, client: TestClient, square: float
) -> None:
    before = (calib / "calib" / "rig.yaml").read_bytes()

    response = measure(client, square_measured_mm=square)

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert f"{square:g} mm" in detail
    assert "nominal square of 25 mm (expected 20 to 31.25 mm for one square)" in detail
    assert (calib / "calib" / "rig.yaml").read_bytes() == before


@pytest.mark.parametrize(
    "changes",
    [
        {"marker_measured_mm": 25.02},
        {"square_measured_mm": -25.0},
        {"measurement_uncertainty_mm": -0.1},
        {"substrate": "x" * 201},
        {"measured_on": "6 October"},
        {"caliper": "digital"},
    ],
)
def test_an_invalid_measurement_is_refused(
    calib: Path, client: TestClient, changes: dict[str, Any]
) -> None:
    assert measure(client, **changes).status_code == 422


def test_a_value_that_is_not_a_number_is_refused(calib: Path, client: TestClient) -> None:
    body = '{"square_measured_mm": NaN, "measurement_uncertainty_mm": Infinity}'

    response = client.put(
        "/boards/rig_board_a/measurement",
        content=body,
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 422
    assert [problem["loc"] for problem in response.json()["detail"]] == [
        ["body", "square_measured_mm"],
        ["body", "measurement_uncertainty_mm"],
    ]


def test_an_unknown_board_is_not_found(calib: Path, client: TestClient) -> None:
    response = measure(client, board="rig_board_z")

    assert response.status_code == 404
    assert response.json()["detail"] == "no board named 'rig_board_z' in calib/rig.yaml"


def test_without_a_rig_file_nothing_is_measured(root: Path, client: TestClient) -> None:
    response = measure(client)

    assert response.status_code == 404
    assert response.json()["detail"] == "calib/rig.yaml not found"


@pytest.mark.parametrize(
    ("unmeasured", "layout", "reason"),
    [
        ("    square_measured_mm: null\n", "    square_measured_mm: &m null\n", "cannot replace"),
        (
            "    substrate: null\n",
            "    substrate: >\n      glued to\n      the side\n",
            "several lines",
        ),
        (
            "    measured_on: null\n",
            "    measured_on: null\n    square_measured_mm: null\n",
            "not load",
        ),
    ],
)
def test_a_layout_the_editor_cannot_handle_leaves_the_file_untouched(
    root: Path, client: TestClient, unmeasured: str, layout: str, reason: str
) -> None:
    board_a = RIG_YAML.index("  rig_board_a:")
    rig = RIG_YAML[:board_a] + RIG_YAML[board_a:].replace(unmeasured, layout, 1)
    write_rig(root, rig)

    response = measure(client)

    assert response.status_code == 500
    assert response.json()["detail"].startswith("cannot edit calib/rig.yaml in place:")
    assert reason in response.json()["detail"]
    assert (root / "calib" / "rig.yaml").read_text() == rig


def test_a_read_only_service_refuses_and_leaves_the_file(
    calib: Path, client: TestClient, read_only: None
) -> None:
    response = measure(client)

    assert response.status_code == 403
    assert (calib / "calib" / "rig.yaml").read_text() == RIG_YAML
