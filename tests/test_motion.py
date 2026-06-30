"""Tests for the motion-blur-aware detector (DESIGN.md §2.2)."""

from __future__ import annotations

from pathlib import Path
from statistics import median

import cv2
import numpy as np
from numpy.typing import NDArray

from blurscan.detectors import available, get
from blurscan.loader import load_image
from blurscan.models import ScanConfig

CFG = ScanConfig(scan_path=Path("."))
MOTION = get("motion")
LAPLACIAN = get("laplacian")


def _checkerboard(size: int = 240, square: int = 12) -> NDArray[np.uint8]:
    idx = (np.arange(size) // square) % 2
    pattern = np.logical_xor(idx[:, None], idx[None, :]).astype(np.uint8) * 255
    return np.stack([pattern] * 3, axis=-1)


def _motion_blur(rgb: NDArray[np.uint8], length: int = 21) -> NDArray[np.uint8]:
    kernel = np.zeros((1, length), dtype=np.float64)
    kernel[0, :] = 1.0 / length  # horizontal motion
    return cv2.filter2D(rgb, -1, kernel).astype(np.uint8)


def test_registered() -> None:
    assert "motion" in available()
    assert MOTION.name == "motion"


def test_penalizes_directional_blur(tmp_path: Path) -> None:
    sharp = _checkerboard()
    blurred = _motion_blur(sharp)
    s = MOTION.score_image(sharp, CFG).score
    b = MOTION.score_image(blurred, CFG).score
    assert b < 0.2 * s  # motion blur strongly suppressed


def test_more_motion_sensitive_than_laplacian() -> None:
    """The motion detector should penalize *directional* blur at least as hard as
    the orientation-blind laplacian — that's its reason to exist."""
    sharp = _checkerboard()
    blurred = _motion_blur(sharp)
    motion_ratio = MOTION.score_image(blurred, CFG).score / MOTION.score_image(sharp, CFG).score
    lap_ratio = LAPLACIAN.score_image(blurred, CFG).score / LAPLACIAN.score_image(sharp, CFG).score
    assert motion_ratio <= lap_ratio


def test_tile_scores_present() -> None:
    scores = MOTION.score_image(_checkerboard(), CFG)
    assert scores.tile_scores is not None and scores.tile_scores.shape == (4, 4)


def test_ranks_real_corpus(blurry_samples: list[Path], sharp_samples: list[Path]) -> None:
    blurry = [MOTION.score_image(load_image(p), CFG).score for p in blurry_samples]
    sharp = [MOTION.score_image(load_image(p), CFG).score for p in sharp_samples]
    assert median(sharp) > median(blurry)
    pairs = [1.0 if s > b else 0.5 if s == b else 0.0 for s in sharp for b in blurry]
    auc = sum(pairs) / len(pairs)
    assert auc >= 0.75, f"motion ranking AUC {auc:.3f} below floor"
