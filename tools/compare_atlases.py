"""How well two atlases of one asset agree: the landmarks they share, one build laid onto the other.

Two builds from different sessions sit in two frames, each set by where the rig
board lay. Their shared landmarks are laid onto each other by the rigid motion
that fits them best (Kabsch), and what is left over is how far the builds
disagree, point by point, beside the sigmas the atlases give. The best fit
that may also scale says whether one build is larger than the other.

Markers moved between the sessions do not belong in the fit: --markers names
the ones that stayed, by their number.

    uv run tools/compare_atlases.py eval/datasets/cabinet-aruco-2026-10-15/atlas.json \\
        data/atlas/cabinet-aruco.json --markers 50 51 52 53 54 55 56
"""

import argparse
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from smc_core.contracts import Atlas, load_atlas

# The fewest shared points a rigid fit is worth making from.
MIN_POINTS = 4


@dataclass(frozen=True)
class Comparison:
    """The shared points after the fit: how far each lies from its twin, against both sigmas."""

    ids: list[str]
    residuals_mm: np.ndarray
    sigma_mm: np.ndarray  # sqrt(sigma_a^2 + sigma_b^2) per coordinate
    rotation_deg: float
    translation_mm: float
    scale: float  # the second build's size against the first's


def align(source: np.ndarray, target: np.ndarray) -> tuple[np.ndarray, np.ndarray, float]:
    """The rotation and translation that carry source onto target best, and the scale a similarity fit would add.

    Least squares over the points (Kabsch, with Umeyama's scale); the rotation
    is a proper one, never a reflection.
    """
    source_centre, target_centre = source.mean(axis=0), target.mean(axis=0)
    centred = source - source_centre
    covariance = centred.T @ (target - target_centre)
    u, singular, vt = np.linalg.svd(covariance)
    sign = np.diag([1.0, 1.0, float(np.sign(np.linalg.det(vt.T @ u.T)))])
    rotation = vt.T @ sign @ u.T
    scale = float(np.trace(np.diag(singular) @ sign) / np.sum(centred**2))
    return rotation, target_centre - rotation @ source_centre, scale


def shared_points(first: Atlas, second: Atlas, markers: Sequence[int] | None) -> list[str]:
    """The landmark ids both atlases have; with markers, only those markers' corners."""
    ids = {landmark.id for landmark in first.landmarks} & {
        landmark.id for landmark in second.landmarks
    }
    if markers is not None:
        prefixes = tuple(f"m{marker}_" for marker in markers)
        ids = {point for point in ids if point.startswith(prefixes)}
    return sorted(ids)


def compare(first: Atlas, second: Atlas, markers: Sequence[int] | None = None) -> Comparison:
    """The second build laid onto the first over their shared landmarks; ValueError when too few."""
    ids = shared_points(first, second, markers)
    if len(ids) < MIN_POINTS:
        raise ValueError(f"the atlases share {len(ids)} landmarks; a fit needs {MIN_POINTS}")
    a = {landmark.id: landmark for landmark in first.landmarks}
    b = {landmark.id: landmark for landmark in second.landmarks}
    source = np.array([b[point].position_mm for point in ids])
    target = np.array([a[point].position_mm for point in ids])
    rotation, translation, scale = align(source, target)
    moved = source @ rotation.T + translation
    angle = np.degrees(np.arccos(np.clip((np.trace(rotation) - 1) / 2, -1.0, 1.0)))
    return Comparison(
        ids=ids,
        residuals_mm=np.linalg.norm(moved - target, axis=1),
        sigma_mm=np.array([np.hypot(a[point].sigma_mm, b[point].sigma_mm) for point in ids]),
        rotation_deg=float(angle),
        translation_mm=float(np.linalg.norm(translation)),
        scale=1.0 / scale,
    )


def format_comparison(comparison: Comparison) -> str:
    """One row a marker: how far its corners lie from their twins, beside their sigma."""
    groups: dict[str, list[int]] = {}
    for index, point in enumerate(comparison.ids):
        groups.setdefault(point.rsplit("_", 1)[0], []).append(index)
    lines = [f"  {'marker':8s} {'corners':>7s} {'mean mm':>8s} {'max mm':>7s} {'sigma mm':>9s}"]
    for name, indices in sorted(groups.items()):
        residuals = comparison.residuals_mm[indices]
        lines.append(
            f"  {name:8s} {len(indices):7d} {residuals.mean():8.2f} {residuals.max():7.2f} "
            f"{float(np.mean(comparison.sigma_mm[indices])):9.2f}"
        )
    rms = float(np.sqrt(np.mean(comparison.residuals_mm**2)))
    lines += [
        f"  {len(comparison.ids)} shared points: RMS {rms:.2f} mm after the fit",
        f"  the frames differ by {comparison.rotation_deg:.1f}° and {comparison.translation_mm:.0f} mm",
        f"  the second build is {comparison.scale:.4f} times the size of the first "
        f"({(comparison.scale - 1) * 1000:+.1f} mm a metre)",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("first", type=Path, help="an atlas file")
    parser.add_argument("second", type=Path, help="another build of the same asset")
    parser.add_argument(
        "--markers", type=int, nargs="+", help="the markers that stayed; default: every shared id"
    )
    args = parser.parse_args(argv)

    try:
        comparison = compare(load_atlas(args.first), load_atlas(args.second), args.markers)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    print(format_comparison(comparison))


if __name__ == "__main__":
    main()
