from pathlib import Path

import numpy as np
import pytest
from calibrate_camera import format_report, main
from smc_core.calibration import Calibration


def test_format_report_shows_quality_numbers_and_worst_view_first() -> None:
    result: Calibration = {
        "rms": 0.4321,
        "camera_matrix": np.array([[3000.0, 0.0, 2000.0], [0.0, 3010.0, 1500.0], [0.0, 0.0, 1.0]]),
        "dist_coeffs": np.array([0.1, -0.2, 0.001, -0.002, 0.3]),
        "std_intrinsics": np.full(18, 0.5),
        "per_view_errors": np.array([0.2, 0.9, 0.5]),
    }

    report = format_report(result, ["a.jpg", "b.jpg", "c.jpg"], (4032, 3024))

    assert "views used: 3" in report
    assert "image size: 4032x3024 px" in report
    assert "RMS reprojection error: 0.432 px" in report
    assert "3000.0000 +/- 0.5000" in report
    assert report.index("b.jpg") < report.index("c.jpg") < report.index("a.jpg")


def test_main_stops_when_no_frame_shows_the_board(tmp_path: Path) -> None:
    out = tmp_path / "out.yml"

    with pytest.raises(SystemExit, match="no frame"):
        main([str(tmp_path), "--out", str(out), "--camera-id", "test"])

    assert not out.exists()
