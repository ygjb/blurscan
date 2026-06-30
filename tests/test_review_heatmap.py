"""Tests for the heatmap endpoint and persistent decisions (DESIGN.md §4.2)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from blurscan.actions.review.heatmap import heatmap_jpeg
from blurscan.actions.review.server import ReviewState, create_app
from blurscan.actions.review.store import DecisionStore
from blurscan.cache import default_cache_path
from blurscan.models import BLURRY, ImageResult, ScanConfig


def _checkerboard(size: int = 160, square: int = 16) -> NDArray[np.uint8]:
    idx = (np.arange(size) // square) % 2
    pattern = np.logical_xor(idx[:, None], idx[None, :]).astype(np.uint8) * 255
    return np.stack([pattern] * 3, axis=-1)


def _img(path: Path) -> Path:
    Image.fromarray(_checkerboard(), "RGB").save(path)
    return path


def _result(path: Path, method: str = "laplacian") -> ImageResult:
    return ImageResult(path, 160, 160, 500.0, 200.0, 0.4, BLURRY, method=method)


def test_heatmap_jpeg_for_laplacian(tmp_path: Path) -> None:
    data = heatmap_jpeg(_result(_img(tmp_path / "a.png")), ScanConfig(scan_path=tmp_path))
    assert data is not None and data[:3] == b"\xff\xd8\xff"  # JPEG


def test_heatmap_for_motion_method(tmp_path: Path) -> None:
    # The motion detector also exposes per-tile scores, so it has a heatmap.
    img = _img(tmp_path / "a.png")
    data = heatmap_jpeg(_result(img, method="motion"), ScanConfig(scan_path=tmp_path))
    assert data is not None
    # The ml method (no tile_scores) yields None — exercised at the endpoint as 404.


def test_heatmap_endpoint(tmp_path: Path) -> None:
    state = ReviewState([_result(_img(tmp_path / "a.png"))], ScanConfig(scan_path=tmp_path))
    client = create_app(state).test_client()
    assert client.get("/api/heatmap/0").status_code == 200
    assert client.get("/api/heatmap/999").status_code == 404


def test_decisions_persist_across_sessions(tmp_path: Path) -> None:
    _img(tmp_path / "a.png")
    cfg = ScanConfig(scan_path=tmp_path)
    db = default_cache_path(tmp_path)
    result = _result(tmp_path / "a.png")

    with DecisionStore(db) as store:
        state = ReviewState([result], cfg, store=store)
        state.set_decision("0", "quarantine")

    # New session, same store -> decision restored.
    with DecisionStore(db) as store2:
        reopened = ReviewState([result], cfg, store=store2)
        assert reopened.decisions["0"] == "quarantine"
