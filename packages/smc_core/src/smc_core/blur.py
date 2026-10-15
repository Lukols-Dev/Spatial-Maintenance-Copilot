"""How sharp a camera frame is, measured on the printed markers in it.

A marker is a printed square of black and white modules, the same in every
frame, so the width of its edges is a measure of the frame and not of the
scene. Across an edge the intensity rises by the marker's contrast; the steepest
slope along a direction is that contrast over the number of pixels the rise
takes. A camera that moves while the frame is exposed spreads the rise along its
motion, so the width is measured in eight directions and the widest is kept:
a motion of n pixels in any direction reads as at least 0.85 n, a still
camera's edges as about three pixels.

The width is in pixels of the frame, so it compares frames of one camera at one
size, as the frames of a calibrated camera are: the same blur in a frame twice
the size is twice as wide. It does not depend on how large a marker appears,
on the exposure, or on what else is in view, unlike the variance of the
Laplacian (smc_core.video.sharpness), which grows with texture.
"""

import math
from collections.abc import Iterable

import cv2 as cv
import numpy as np

from smc_core.contracts import FrameQuality

# The directions an edge's rise is measured along, every 22.5 degrees from
# across vertical edges.
ANGLES = tuple(index * math.pi / 8 for index in range(8))
# A marker's box grows by this share of its size, plus MARGIN_PX, so the white
# paper around it is inside: the outer edge is the longest and the strongest.
PAD = 0.15
MARGIN_PX = 3
# Intensity percentiles that stand for the marker's black and its white.
DARK, LIGHT = 5.0, 95.0
# The slope percentile that stands for an edge: edges are a small share of the box.
STEEPEST = 98.0
# Below this many levels between black and white there is no edge to measure.
MIN_CONTRAST = 16.0
# Sobel's 3x3 kernel weighs the difference across two pixels by 1, 2, 1: eight
# times the slope of a linear ramp.
SOBEL_GAIN = 8.0


def edge_width(gray: np.ndarray, corners: np.ndarray) -> float | None:
    """How many pixels a marker's edges take to rise from its black to its white, at their widest.

    corners are the marker's four corners in the frame (4x2). None when the
    marker is too small or too flat in contrast to measure.
    """
    height, width = gray.shape[:2]
    low, high = corners.min(axis=0), corners.max(axis=0)
    pad = (high - low) * PAD + MARGIN_PX
    left, top = np.maximum(np.floor(low - pad), 0).astype(int)
    right, bottom = np.minimum(np.ceil(high + pad) + 1, [width, height]).astype(int)
    if right - left < 8 or bottom - top < 8:
        return None
    box = gray[top:bottom, left:right].astype(np.float32)
    dark, light = np.percentile(box, [DARK, LIGHT])
    contrast = float(light - dark)
    if contrast < MIN_CONTRAST:
        return None
    gx = cv.Sobel(box, cv.CV_32F, 1, 0, ksize=3) / SOBEL_GAIN
    gy = cv.Sobel(box, cv.CV_32F, 0, 1, ksize=3) / SOBEL_GAIN
    widest = 0.0
    for angle in ANGLES:
        slope = float(np.percentile(np.abs(gx * math.cos(angle) + gy * math.sin(angle)), STEEPEST))
        if slope <= 0:
            return None
        widest = max(widest, contrast / slope)
    return widest


def frame_quality(frame: np.ndarray, markers: Iterable[np.ndarray]) -> FrameQuality:
    """The frame's blur, as the median edge width of the markers found in it."""
    gray = frame if frame.ndim == 2 else cv.cvtColor(frame, cv.COLOR_BGR2GRAY)
    widths = [width for corners in markers if (width := edge_width(gray, corners)) is not None]
    return FrameQuality(
        markers=len(widths), edge_width_px=float(np.median(widths)) if widths else None
    )
