"""The ``laplacian`` detector — tiled max variance-of-Laplacian (default method).

See DESIGN.md §2.1. Primary score is the maximum per-tile variance-of-Laplacian
(the sharpest region), which spares shallow-DoF shots. Cleanly separates gross
out-of-focus blur; on hard content (subject motion blur) it is a strong *ranking*
signal for triage rather than a hard verdict.
"""

from __future__ import annotations

from blurscan.detectors.base import DetectorScore, register
from blurscan.loader import RGBArray
from blurscan.metrics import (
    downscale,
    fft_high_freq_ratio,
    laplacian,
    tiled_variance,
    to_grayscale,
)
from blurscan.models import ScanConfig


class LaplacianDetector:
    """Tiled max variance-of-Laplacian sharpness detector."""

    name = "laplacian"
    default_threshold = 100.0

    def score_image(self, rgb: RGBArray, cfg: ScanConfig) -> DetectorScore:
        small = downscale(rgb, cfg.working_size)
        gray = to_grayscale(small)
        lap = laplacian(gray)
        tiles = tiled_variance(lap, cfg.grid)
        return DetectorScore(
            score=float(tiles.max()),
            extras={
                "global": float(lap.var()),
                "fft_ratio": fft_high_freq_ratio(gray),
            },
            tile_scores=tiles,
        )


register(LaplacianDetector())
