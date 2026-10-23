"""Two builds of one atlas laid onto each other: what is left over is how far they disagree."""

from pathlib import Path

import numpy as np
import pytest
from compare_atlases import align, compare, main
from smc_core.contracts import Atlas, Landmark
from smc_core.testing import scene_atlas


def moved(
    atlas: Atlas, turn_deg: float, shift: tuple[float, float, float], scale: float = 1.0
) -> Atlas:
    """The same atlas in another board frame: turned about z, shifted, and scaled."""
    angle = np.radians(turn_deg)
    rotation = np.array(
        [[np.cos(angle), -np.sin(angle), 0.0], [np.sin(angle), np.cos(angle), 0.0], [0, 0, 1]]
    )
    landmarks = []
    for landmark in atlas.landmarks:
        x, y, z = scale * rotation @ np.array(landmark.position_mm) + np.array(shift)
        landmarks.append(landmark.model_copy(update={"position_mm": (x, y, z)}))
    return atlas.model_copy(update={"landmarks": landmarks})


def test_a_rigid_motion_is_found_and_undone() -> None:
    rng = np.random.default_rng(0)
    source = rng.normal(0, 200, (6, 3))
    angle = np.radians(25.0)
    rotation = np.array(
        [[np.cos(angle), 0.0, np.sin(angle)], [0, 1, 0], [-np.sin(angle), 0, np.cos(angle)]]
    )

    found, translation, scale = align(source, source @ rotation.T + [10.0, -20.0, 30.0])

    np.testing.assert_allclose(found, rotation, atol=1e-9)
    np.testing.assert_allclose(translation, [10.0, -20.0, 30.0], atol=1e-9)
    assert scale == pytest.approx(1.0)


def test_two_builds_one_moved_off_the_other_agree_after_the_fit() -> None:
    first = scene_atlas()

    comparison = compare(first, moved(first, 30.0, (500.0, -200.0, 10.0)))

    assert comparison.residuals_mm.max() < 1e-6
    assert comparison.rotation_deg == pytest.approx(30.0)
    assert comparison.translation_mm == pytest.approx(np.linalg.norm([500.0, -200.0, 10.0]))
    assert comparison.scale == pytest.approx(1.0)


def test_a_build_one_percent_larger_shows_in_its_scale_and_its_residuals() -> None:
    first = scene_atlas()

    comparison = compare(first, moved(first, 0.0, (0.0, 0.0, 0.0), scale=1.01))

    assert comparison.scale == pytest.approx(1.01)
    assert comparison.residuals_mm.max() > 1.0


def test_only_the_listed_markers_are_fitted_and_too_few_are_refused() -> None:
    corners = [
        Landmark(
            id=f"m{marker}_{corner}",
            position_mm=(marker * 10.0 + corner, corner * 5.0, marker * 1.0),
            sigma_mm=0.5,
        )
        for marker in (50, 51, 52)
        for corner in range(4)
    ]
    first = scene_atlas().model_copy(update={"landmarks": corners})

    assert compare(first, first, [50, 51]).ids == [
        f"m{marker}_{corner}" for marker in (50, 51) for corner in range(4)
    ]
    with pytest.raises(ValueError, match="share 0 landmarks"):
        compare(first, first, [53])


def test_the_printout_has_a_row_a_landmark_and_the_fit(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    first = scene_atlas()
    (tmp_path / "a.json").write_text(first.model_dump_json())
    (tmp_path / "b.json").write_text(moved(first, 10.0, (5.0, 5.0, 5.0)).model_dump_json())

    main([str(tmp_path / "a.json"), str(tmp_path / "b.json")])

    printed = capsys.readouterr().out
    assert f"{len(first.landmarks)} shared points: RMS 0.00 mm after the fit" in printed
    assert "the frames differ by 10.0°" in printed
