"""Tests for metric primitives and the laplacian detector (DESIGN.md §2 / §8.2).

Synthetic images gate CI; the real-image checks at the bottom run only when the
local ``test_samples/`` set is present, and assert a *ranking-quality* bar
(median separation + ROC-AUC) rather than perfect threshold separation — the
data shows the laplacian method ranks well but cannot cleanly separate motion
blur (see DESIGN.md §2.0).
"""

from __future__ import annotations

from pathlib import Path
from statistics import median

import cv2
import numpy as np
from numpy.typing import NDArray

from blurscan.detectors import available, get
from blurscan.detectors.base import Detector, DetectorScore
from blurscan.loader import load_image
from blurscan.models import ScanConfig

CFG = ScanConfig(scan_path=Path("."))
LAPLACIAN = get("laplacian")


def _score(rgb: NDArray[np.uint8]) -> DetectorScore:
    return LAPLACIAN.score_image(rgb, CFG)


def _checkerboard(size: int = 400, square: int = 20) -> NDArray[np.uint8]:
    idx = (np.arange(size) // square) % 2
    pattern = np.logical_xor(idx[:, None], idx[None, :]).astype(np.uint8) * 255
    return np.stack([pattern] * 3, axis=-1)


def _blur(rgb: NDArray[np.uint8], k: int = 21) -> NDArray[np.uint8]:
    out: NDArray[np.uint8] = cv2.GaussianBlur(rgb, (k, k), 0).astype(np.uint8)
    return out


def _auc(positives: list[float], negatives: list[float]) -> float:
    """P(positive_score > negative_score), ties counted as 0.5."""
    pairs = [
        1.0 if p > n else 0.5 if p == n else 0.0 for p in positives for n in negatives
    ]
    return sum(pairs) / len(pairs)


# --- registry ---


def test_registry_lists_laplacian() -> None:
    assert "laplacian" in available()
    assert isinstance(LAPLACIAN, Detector)
    assert LAPLACIAN.name == "laplacian"


# --- synthetic (CI gate) ---


def test_sharp_scores_higher_than_blurred() -> None:
    sharp = _score(_checkerboard())
    blurred = _score(_blur(_checkerboard()))
    assert sharp.score > blurred.score
    assert sharp.extras["global"] > blurred.extras["global"]


def test_half_sharp_image_scores_high_via_max_tile() -> None:
    """A frame sharp on one half and blurred on the other must score high on the
    max-tile metric (the shallow-DoF false-positive guard)."""
    base = _checkerboard()
    half = base.copy()
    w = half.shape[1]
    half[:, w // 2 :] = _blur(base)[:, w // 2 :]

    s_sharp = _score(base)
    s_half = _score(half)
    s_blur = _score(_blur(base))

    assert s_half.score > 0.5 * s_sharp.score
    assert s_half.score > 3 * s_blur.score
    # Max-tile exceeds the global average of the same image (blurred half drags
    # the global score down).
    assert s_half.score > s_half.extras["global"]


def test_tile_scores_shape() -> None:
    scores = _score(_checkerboard())
    assert scores.tile_scores is not None
    assert scores.tile_scores.shape == (4, 4)


def test_downscale_bounds_working_size() -> None:
    big = _checkerboard(size=2000, square=40)
    cfg = ScanConfig(scan_path=Path("."), working_size=500)
    assert LAPLACIAN.score_image(big, cfg).score > LAPLACIAN.default_threshold


# --- Local real-image ranking quality (skips in CI; see conftest.py) ---

AUC_FLOOR = 0.70


def test_laplacian_ranks_real_samples(
    blurry_samples: list[Path], sharp_samples: list[Path]
) -> None:
    blurry = [_score(load_image(p)).score for p in blurry_samples]
    sharp = [_score(load_image(p)).score for p in sharp_samples]
    # Ranks sharp above blurry on the whole, even if no clean threshold exists.
    assert median(sharp) > median(blurry)
    auc = _auc(sharp, blurry)
    assert auc >= AUC_FLOOR, f"laplacian ranking AUC {auc:.3f} below floor {AUC_FLOOR}"
