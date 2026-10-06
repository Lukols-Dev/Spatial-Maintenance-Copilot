from pathlib import Path

import cv2 as cv
import numpy as np
import pytest
from smc_core.calibration import (
    Calibration,
    Intrinsics,
    calibrate,
    check_frame_size,
    create_board,
    detect_board,
    load_calibration,
    load_calibration_record,
    save_calibration,
)

# A portrait 1080x1920 camera, roughly the phone the project is calibrated on.
CAMERA_MATRIX = np.array([[1675.0, 0.0, 531.6], [0.0, 1677.4, 956.2], [0.0, 0.0, 1.0]])


@pytest.fixture
def board() -> cv.aruco.CharucoBoard:
    """The printed calibration board: 5x7 squares of 30 mm, markers 21.6 mm."""
    return create_board(5, 7, 30.0, 21.6, cv.aruco.DICT_5X5_100, list(range(17)))


@pytest.fixture
def intrinsics() -> Intrinsics:
    return {
        "camera_id": "phone-1x-portrait",
        "image_size": (1080, 1920),
        "camera_matrix": CAMERA_MATRIX,
        "dist_coeffs": np.zeros(5),
        "rms": 0.5,
        "std_intrinsics": np.zeros(9),
    }


def synthetic_views(
    board: cv.aruco.CharucoBoard, view_count: int = 10
) -> tuple[list[np.ndarray], list[np.ndarray]]:
    """Board corners as a distortion-free CAMERA_MATRIX sees them from tilted poses."""
    corners = board.getChessboardCorners()
    rng = np.random.default_rng(0)
    object_points, image_points = [], []
    for _ in range(view_count):
        rvec = rng.uniform(-0.5, 0.5, 3)
        tvec = np.array([rng.uniform(-100, 0), rng.uniform(-150, 0), rng.uniform(400, 700)])
        projected, _ = cv.projectPoints(corners, rvec, tvec, CAMERA_MATRIX, np.zeros(5))
        object_points.append(corners)
        image_points.append(projected.reshape(-1, 2).astype(np.float32))
    return object_points, image_points


def test_create_board_matches_printed_board(board: cv.aruco.CharucoBoard) -> None:
    assert board.getChessboardSize() == (5, 7)
    assert len(board.getIds()) == 17

    corners = board.getChessboardCorners()
    assert corners.shape == (24, 3)
    np.testing.assert_allclose(corners[0], [30.0, 30.0, 0.0])
    np.testing.assert_allclose(corners[-1], [120.0, 180.0, 0.0])


def test_detect_board_finds_every_corner(board: cv.aruco.CharucoBoard) -> None:
    # 100 px per square plus a 40 px white margin: a marker touching the image
    # edge cannot be decoded.
    image = board.generateImage((580, 780), marginSize=40)
    detector = cv.aruco.CharucoDetector(board)

    charuco_corners, charuco_ids, _, marker_ids = detect_board(detector, image)

    assert charuco_corners.shape == (24, 2)
    assert sorted(charuco_ids.tolist()) == list(range(24))
    assert len(marker_ids) == 17


def test_detect_board_returns_empty_arrays_when_nothing_found(
    board: cv.aruco.CharucoBoard,
) -> None:
    blank = np.full((780, 580), 255, np.uint8)
    detector = cv.aruco.CharucoDetector(board)

    charuco_corners, charuco_ids, _, marker_ids = detect_board(detector, blank)

    assert charuco_corners.shape == (0, 2)
    assert len(charuco_ids) == 0
    assert len(marker_ids) == 0


def test_calibrate_recovers_the_camera_that_took_the_views(board: cv.aruco.CharucoBoard) -> None:
    object_points, image_points = synthetic_views(board)

    result = calibrate(object_points, image_points, (1080, 1920))

    np.testing.assert_allclose(result["camera_matrix"], CAMERA_MATRIX, atol=0.5)
    np.testing.assert_allclose(result["dist_coeffs"], 0.0, atol=1e-3)
    assert result["rms"] < 0.01
    assert len(result["per_view_errors"]) == 10


def test_calibrate_holds_k3_at_zero_when_told_to(board: cv.aruco.CharucoBoard) -> None:
    object_points, image_points = synthetic_views(board)

    result = calibrate(object_points, image_points, (1080, 1920), fix_k3=True)

    assert result["dist_coeffs"][4] == 0.0
    assert result["std_intrinsics"][8] == 0.0


def test_load_calibration_reads_what_save_calibration_wrote(tmp_path: Path) -> None:
    result: Calibration = {
        "rms": 0.42,
        "camera_matrix": CAMERA_MATRIX,
        "dist_coeffs": np.array([0.14, -0.15, 0.0002, -0.004, -0.21]),
        "std_intrinsics": np.arange(18, dtype=np.float64),
        "per_view_errors": np.array([0.3, 0.5]),
    }
    path = str(tmp_path / "camera.yml")
    save_calibration(path, result, (1080, 1920), "phone-1x-portrait")

    loaded = load_calibration(path)

    assert loaded["camera_id"] == "phone-1x-portrait"
    assert loaded["image_size"] == (1080, 1920)
    np.testing.assert_allclose(loaded["camera_matrix"], CAMERA_MATRIX)
    np.testing.assert_allclose(loaded["dist_coeffs"], result["dist_coeffs"])
    assert loaded["rms"] == pytest.approx(0.42)
    np.testing.assert_allclose(loaded["std_intrinsics"], np.arange(9))


def test_load_calibration_fails_on_a_missing_file(tmp_path: Path) -> None:
    with pytest.raises(OSError, match="cannot read calibration"):
        load_calibration(str(tmp_path / "missing.yml"))


def test_check_frame_size_accepts_the_calibrated_size(intrinsics: Intrinsics) -> None:
    check_frame_size(intrinsics, np.zeros((1920, 1080, 3), np.uint8))


def test_check_frame_size_spots_a_rotated_frame(intrinsics: Intrinsics) -> None:
    with pytest.raises(ValueError, match="rotated by 90 degrees"):
        check_frame_size(intrinsics, np.zeros((1080, 1920, 3), np.uint8))


def test_check_frame_size_rejects_another_resolution(intrinsics: Intrinsics) -> None:
    with pytest.raises(ValueError, match=r"1280x720 px, but phone-1x-portrait was calibrated"):
        check_frame_size(intrinsics, np.zeros((720, 1280, 3), np.uint8))


def test_load_calibration_record_tells_how_the_calibration_was_made(tmp_path: Path) -> None:
    result: Calibration = {
        "rms": 0.42,
        "camera_matrix": CAMERA_MATRIX,
        "dist_coeffs": np.zeros(5),
        "std_intrinsics": np.zeros(18),
        "per_view_errors": np.array([0.3, 0.5, 0.4]),
    }
    path = str(tmp_path / "camera.yml")
    save_calibration(path, result, (1080, 1920), "phone-1x-portrait")

    record = load_calibration_record(path)

    assert record["intrinsics"]["camera_id"] == "phone-1x-portrait"
    assert record["frames"] == 3
    assert record["opencv_version"] == cv.__version__
    assert record["calibrated_at"] is not None and record["calibrated_at"].startswith("20")


def test_load_calibration_record_leaves_out_what_the_file_does_not_say(tmp_path: Path) -> None:
    path = tmp_path / "camera.yml"
    path.write_text(
        "%YAML:1.0\n---\ncamera_id: phone\nimage_width: 1080\nimage_height: 1920\n"
        "camera_matrix: !!opencv-matrix\n   rows: 3\n   cols: 3\n   dt: d\n"
        "   data: [ 1675., 0., 531.6, 0., 1677.4, 956.2, 0., 0., 1. ]\n"
        "distortion_coefficients: !!opencv-matrix\n   rows: 1\n   cols: 5\n   dt: d\n"
        "   data: [ 0., 0., 0., 0., 0. ]\n"
        "avg_reprojection_error: 0.5\n"
        "std_intrinsics: !!opencv-matrix\n   rows: 1\n   cols: 9\n   dt: d\n"
        "   data: [ 0., 0., 0., 0., 0., 0., 0., 0., 0. ]\n",
        encoding="utf-8",
    )

    record = load_calibration_record(str(path))

    assert record["intrinsics"]["image_size"] == (1080, 1920)
    assert (record["frames"], record["calibrated_at"], record["opencv_version"]) == (None,) * 3


def test_load_calibration_fails_on_a_file_that_does_not_parse(tmp_path: Path) -> None:
    path = tmp_path / "camera.yml"
    path.write_text("camera_matrix: [1, 2\n  oops: {", encoding="utf-8")

    with pytest.raises(ValueError, match="cannot parse calibration"):
        load_calibration(str(path))
