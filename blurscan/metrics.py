"""Shared image-metric primitives used by detectors.

See DESIGN.md §2 / §3.5. These are the building blocks (downscale, grayscale,
Laplacian, tiled variance, FFT ratio) that the pluggable detectors in
``blurscan.detectors`` compose into a sharpness score. Scoring policy lives in
the detectors, not here.
"""

from __future__ import annotations

import cv2
import numpy as np
from numpy.typing import NDArray

from blurscan.loader import RGBArray

FloatArray = NDArray[np.float64]


def downscale(rgb: RGBArray, working_size: int) -> RGBArray:
    """Downscale so the longest edge is ``working_size`` px. Never upscales."""
    h, w = rgb.shape[:2]
    longest = max(h, w)
    if longest <= working_size:
        return rgb
    scale = working_size / longest
    new_size = (max(1, round(w * scale)), max(1, round(h * scale)))
    resized = cv2.resize(rgb, new_size, interpolation=cv2.INTER_AREA)
    return resized.astype(np.uint8)


def to_grayscale(rgb: RGBArray) -> NDArray[np.uint8]:
    """Convert an RGB array to single-channel grayscale."""
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    return gray.astype(np.uint8)


def laplacian(gray: NDArray[np.uint8]) -> FloatArray:
    """Laplacian response of a grayscale image as float64."""
    return cv2.Laplacian(gray, cv2.CV_64F).astype(np.float64)


def tile_bounds(length: int, n: int) -> list[tuple[int, int]]:
    """Split ``[0, length)`` into ``n`` contiguous (start, end) tile bounds."""
    edges = np.linspace(0, length, n + 1).astype(int)
    return [(int(edges[i]), int(edges[i + 1])) for i in range(n)]


def tiled_variance(values: FloatArray, grid: int) -> FloatArray:
    """Variance of ``values`` within each tile of a ``grid x grid`` split."""
    h, w = values.shape
    rows = tile_bounds(h, grid)
    cols = tile_bounds(w, grid)
    scores = np.zeros((grid, grid), dtype=np.float64)
    for i, (y0, y1) in enumerate(rows):
        for j, (x0, x1) in enumerate(cols):
            tile = values[y0:y1, x0:x1]
            scores[i, j] = float(tile.var()) if tile.size else 0.0
    return scores


def fft_high_freq_ratio(gray: NDArray[np.uint8], cutoff_frac: float = 0.25) -> float:
    """Fraction of spectral magnitude outside a central low-frequency window.

    Higher means more high-frequency energy (edges/detail) -> sharper.
    """
    f = np.fft.fftshift(np.fft.fft2(gray.astype(np.float64)))
    mag = np.abs(f)
    total = float(mag.sum())
    if total == 0.0:
        return 0.0
    h, w = gray.shape
    cy, cx = h // 2, w // 2
    ry = int(h * cutoff_frac / 2)
    rx = int(w * cutoff_frac / 2)
    low = float(mag[cy - ry : cy + ry + 1, cx - rx : cx + rx + 1].sum())
    return (total - low) / total
