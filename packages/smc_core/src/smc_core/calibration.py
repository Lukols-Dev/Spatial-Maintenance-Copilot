from collections.abc import Iterable, Sequence
from datetime import datetime
from typing import TypedDict, cast

import cv2 as cv
import numpy as np


def create_board(
    squares_x: int,
    squares_y: int,
    square_mm: float,
    marker_mm: float,
    dictionary_id: int,
    marker_ids: list[int],
) -> cv.aruco.CharucoBoard:
    """Model of the printed ChArUco board. Draws nothing.

    Lengths are in millimetres, so everything computed from this board later
    (poses, distances) comes out in millimetres too.
    """

    dictionary = cv.aruco.getPredefinedDictionary(dictionary_id)
    return cv.aruco.CharucoBoard(
        (squares_x, squares_y),
        square_mm,
        marker_mm,
        dictionary,
        np.array(marker_ids, dtype=np.int32),
    )


def detect_board(
    detector: cv.aruco.CharucoDetector, frame: np.ndarray
) -> tuple[np.ndarray, np.ndarray, Sequence[np.ndarray], np.ndarray]:
    """Find the ChArUco board in one frame.

    Returns (charuco_corners, charuco_ids, marker_corners, marker_ids):
      charuco_corners  (N, 2) pixel positions of chessboard corners
      charuco_ids      (N,)   which corner of the board each one is
      marker_corners   corners of the detected ArUco markers
      marker_ids       (M,)   IDs of the detected markers

    OpenCV returns None when nothing is found. Here that becomes an empty array,
    so len() works on every result and callers need no None checks.
    """

    # The stubs declare every output as always present, so without the cast the
    # None checks below would be flagged as unreachable.
    charuco_corners, charuco_ids, marker_corners, marker_ids = cast(
        tuple[np.ndarray | None, np.ndarray | None, Sequence[np.ndarray], np.ndarray | None],
        detector.detectBoard(frame),
    )

    if charuco_corners is None or charuco_ids is None:
        charuco_corners = np.empty((0, 2), np.float32)
        charuco_ids = np.empty((0,), np.int32)
    if marker_ids is None:
        marker_ids = np.empty((0,), np.int32)

    return charuco_corners, charuco_ids, marker_corners, marker_ids


def collect_correspondences[Label](
    detector: cv.aruco.CharucoDetector,
    board: cv.aruco.CharucoBoard,
    frames: Iterable[tuple[Label, np.ndarray]],
    min_corners: int = 4,
) -> tuple[list[np.ndarray], list[np.ndarray], list[Label], tuple[int, int] | None]:
    """Pair board points in millimetres with image points in pixels, frame by frame.

    frames: (label, image) pairs. Each label comes back in `used`, in the same
    order as the views, so a view in the calibration result can be traced to
    the frame it came from.

    Returns (object_points, image_points, used, image_size):
      object_points  one (N, 3) array per accepted frame, millimetres on the board
      image_points   one (N, 2) array per accepted frame, pixels in the image
      used           labels of the accepted frames
      image_size     (width, height), needed by the calibration
    """
    object_points: list[np.ndarray] = []
    image_points: list[np.ndarray] = []
    used: list[Label] = []
    image_size: tuple[int, int] | None = None

    for label, frame in frames:
        charuco_corners, charuco_ids, _, _ = detect_board(detector, frame)

        if len(charuco_ids) < min_corners:
            continue

        # The stubs type detectedCorners as a sequence of arrays, but for ChArUco
        # corners the binding takes the single (N, 2) array from detect_board.
        # An ndarray is not a Sequence, so the cast has to go through object.
        corners = cast(Sequence[np.ndarray], cast(object, charuco_corners))
        obj, img = board.matchImagePoints(corners, charuco_ids)

        if np.linalg.matrix_rank(obj[:, :2] - obj[:, :2].mean(axis=0)) < 2:
            continue

        object_points.append(obj)
        image_points.append(img)
        used.append(label)
        image_size = (frame.shape[1], frame.shape[0])
    return object_points, image_points, used, image_size


class Calibration(TypedDict):
    """Result of `calibrate`, one key per quantity.

    A plain dict would type every value as Any. The TypedDict gives each key its
    own type and keeps dict access unchanged.
    """

    rms: float
    camera_matrix: np.ndarray
    dist_coeffs: np.ndarray
    std_intrinsics: np.ndarray
    per_view_errors: np.ndarray


def calibrate(
    object_points: list[np.ndarray],
    image_points: list[np.ndarray],
    image_size: tuple[int, int],
    fix_k3: bool = False,
) -> Calibration:
    """Camera intrinsics from point pairs collected over many views.

    Returns a dict with:
      rms              overall RMS reprojection error, pixels
      camera_matrix    3x3: fx, fy (focal length) and cx, cy (principal point), pixels
      dist_coeffs      k1, k2, p1, p2, k3
      std_intrinsics   standard deviation of each parameter, in the order
                       fx, fy, cx, cy, k1, k2, p1, p2, k3, then unused models
      per_view_errors  RMS reprojection error of each view, same order as the input

    fix_k3 keeps k3 at zero. Use it when the data cannot pin k3 down, which
    shows as a standard deviation larger than the value itself.
    """
    flags = cv.CALIB_FIX_K3 if fix_k3 else 0

    (
        rms,
        camera_matrix,
        dist_coeffs,
        _rvecs,
        _tvecs,
        std_intrinsics,
        _std_extrinsics,
        per_view_errors,
    ) = cv.calibrateCameraExtended(
        object_points,
        image_points,
        image_size,
        np.zeros((3, 3), np.float64),
        np.zeros(5, np.float64),
        flags=flags,
    )

    return {
        "rms": rms,
        "camera_matrix": camera_matrix,
        "dist_coeffs": dist_coeffs.ravel(),
        "std_intrinsics": std_intrinsics.ravel(),
        "per_view_errors": per_view_errors.ravel(),
    }


def undistort_frame(
    frame: np.ndarray,
    camera_matrix: np.ndarray,
    dist_coeffs: np.ndarray,
    alpha: float = 1.0,
) -> np.ndarray:
    """Remove lens distortion from one frame.

    alpha = 1 keeps every source pixel, so the black border shows the shape of
    the distortion. alpha = 0 crops to valid pixels only.
    """
    image_size = (frame.shape[1], frame.shape[0])
    new_matrix, _ = cv.getOptimalNewCameraMatrix(
        camera_matrix, dist_coeffs, image_size, alpha, image_size
    )

    return cv.undistort(frame, camera_matrix, dist_coeffs, None, new_matrix)


def save_calibration(
    path: str, result: Calibration, image_size: tuple[int, int], camera_id: str
) -> None:
    """Save calibrate() output; the format follows the extension (.yml/.xml/.json)."""

    fs = cv.FileStorage(path, cv.FileStorage_WRITE)
    fs.write("calibration_time", datetime.now().isoformat(timespec="seconds"))
    fs.write("opencv_version", cv.__version__)
    fs.write("camera_id", camera_id)
    fs.write("image_width", image_size[0])
    fs.write("image_height", image_size[1])
    fs.write("nr_of_frames", len(result["per_view_errors"]))
    fs.write("camera_matrix", result["camera_matrix"])
    fs.write("distortion_coefficients", result["dist_coeffs"])
    fs.write("avg_reprojection_error", result["rms"])
    fs.writeComment("std devs, order: fx fy cx cy k1 k2 p1 p2 k3")
    fs.write("std_intrinsics", result["std_intrinsics"][:9])
    fs.release()


class Intrinsics(TypedDict):
    """A calibration read back by `load_calibration`.

    image_size is (width, height): the only frame size the intrinsics hold for.
    """

    camera_id: str
    image_size: tuple[int, int]
    camera_matrix: np.ndarray
    dist_coeffs: np.ndarray
    rms: float
    std_intrinsics: np.ndarray


class CalibrationRecord(TypedDict):
    """A calibration file read whole: the intrinsics and how they were made.

    frames, calibrated_at and opencv_version are None when the file lacks them.
    They describe the calibration; the intrinsics alone are enough to use it.
    """

    intrinsics: Intrinsics
    frames: int | None
    calibrated_at: str | None  # as written in the file
    opencv_version: str | None


def load_calibration_record(path: str) -> CalibrationRecord:
    """Read a file written by `save_calibration`, with what it says about itself."""

    try:
        fs = cv.FileStorage(path, cv.FileStorage_READ)
    except (cv.error, SystemError) as error:
        # A file that does not parse makes the binding raise SystemError, with
        # OpenCV's parse error as its cause.
        raise ValueError(f"cannot parse calibration: {path}") from error
    if not fs.isOpened():
        raise OSError(f"cannot read calibration: {path}")

    def node(key: str) -> cv.FileNode:
        found = fs.getNode(key)
        if found.empty():
            raise ValueError(f"{path} has no {key}; was it written by save_calibration?")
        return found

    def text(key: str) -> str | None:
        found = fs.getNode(key)
        return (found.string() or None) if found.isString() else None

    try:
        frames = fs.getNode("nr_of_frames")
        return {
            "intrinsics": {
                "camera_id": node("camera_id").string(),
                "image_size": (int(node("image_width").real()), int(node("image_height").real())),
                "camera_matrix": node("camera_matrix").mat(),
                "dist_coeffs": node("distortion_coefficients").mat().ravel(),
                "rms": node("avg_reprojection_error").real(),
                "std_intrinsics": node("std_intrinsics").mat().ravel(),
            },
            "frames": int(frames.real()) if frames.isInt() else None,
            "calibrated_at": text("calibration_time"),
            "opencv_version": text("opencv_version"),
        }
    finally:
        fs.release()


def load_calibration(path: str) -> Intrinsics:
    """Read a file written by `save_calibration`."""
    return load_calibration_record(path)["intrinsics"]


def check_frame_size(intrinsics: Intrinsics, frame: np.ndarray) -> None:
    """Fail unless the frame has the size the intrinsics were calibrated for.

    A frame of another size still gives a pose, just a wrong one, so the
    mismatch has to be caught here. A frame turned on its side is the likely
    case: image folders are read in the sensor grid, videos as a player shows
    them.
    """
    width, height = intrinsics["image_size"]
    frame_width, frame_height = frame.shape[1], frame.shape[0]
    if (frame_width, frame_height) == (width, height):
        return

    hint = ""
    if (frame_width, frame_height) == (height, width):
        hint = " The frame is rotated by 90 degrees relative to the calibration."
    raise ValueError(
        f"frame is {frame_width}x{frame_height} px, but {intrinsics['camera_id']} "
        f"was calibrated at {width}x{height} px.{hint}"
    )
