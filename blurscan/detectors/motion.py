"""The ``motion`` detector — motion/panning-blur aware (DESIGN.md §2.2).

Motion blur is *directional*: it suppresses image gradients **along** the motion
axis while preserving them **across** it. A plain variance-of-Laplacian is
orientation-blind and so rates a panned-but-edgy subject as sharp. This detector
measures gradient energy in four orientations and scores each tile by its
**weakest** orientation — a region is only "sharp" if it has strong detail in
*every* direction. The image score is the max over tiles (sharpest region),
matching the laplacian method's shallow-DoF guard.
"""

from __future__ import annotations

import cv2
import numpy as np

from blurscan.detectors.base import DetectorScore, register
from blurscan.loader import RGBArray
from blurscan.metrics import FloatArray, downscale, tile_bounds, to_grayscale
from blurscan.models import ScanConfig


def _orientation_energies(gray: FloatArray) -> tuple[FloatArray, ...]:
    """Per-pixel squared gradient energy at 0/45/90/135 degrees."""
    gx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
    e0 = np.asarray(gx * gx, dtype=np.float64)
    e90 = np.asarray(gy * gy, dtype=np.float64)
    e45 = np.asarray(0.5 * (gx + gy) ** 2, dtype=np.float64)
    e135 = np.asarray(0.5 * (gx - gy) ** 2, dtype=np.float64)
    return e0, e45, e90, e135


def _tiled_min_orientation(energies: tuple[FloatArray, ...], grid: int) -> FloatArray:
    """For each tile, the mean energy of its weakest orientation."""
    h, w = energies[0].shape
    rows = tile_bounds(h, grid)
    cols = tile_bounds(w, grid)
    scores = np.zeros((grid, grid), dtype=np.float64)
    for i, (y0, y1) in enumerate(rows):
        for j, (x0, x1) in enumerate(cols):
            if y1 <= y0 or x1 <= x0:
                continue
            means = [float(e[y0:y1, x0:x1].mean()) for e in energies]
            scores[i, j] = min(means)
    return scores


class MotionDetector:
    """Orientation-aware detector for residual motion/panning blur."""

    name = "motion"
    # Method-specific scale: weakest-orientation gradient energy. Calibrated on the
    # CC corpus (blurry median ~850, sharp median ~5500); see PR notes.
    default_threshold = 1000.0

    def score_image(self, rgb: RGBArray, cfg: ScanConfig) -> DetectorScore:
        gray = to_grayscale(downscale(rgb, cfg.working_size)).astype(np.float64)
        energies = _orientation_energies(gray)
        tiles = _tiled_min_orientation(energies, cfg.grid)
        overall = float(np.stack(energies).mean())
        return DetectorScore(
            score=float(tiles.max()),
            extras={"global_energy": overall},
            tile_scores=tiles,
        )


register(MotionDetector())
