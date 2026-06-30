"""Tests for parallel scoring in the pipeline (DESIGN.md §3.3)."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from numpy.typing import NDArray
from PIL import Image

from blurscan.models import ScanConfig
from blurscan.pipeline import _worker_count, run_scan


def _checkerboard(size: int = 160, square: int = 16) -> NDArray[np.uint8]:
    idx = (np.arange(size) // square) % 2
    pattern = np.logical_xor(idx[:, None], idx[None, :]).astype(np.uint8) * 255
    return np.stack([pattern] * 3, axis=-1)


def _populate(root: Path, n: int = 6) -> None:
    sharp = _checkerboard()
    blurred = cv2.GaussianBlur(sharp, (21, 21), 0).astype(np.uint8)
    for i in range(n):
        arr = sharp if i % 2 == 0 else blurred
        Image.fromarray(arr, "RGB").save(root / f"img{i}.png")


def _scores(results: list) -> dict[str, tuple[float, str]]:
    return {r.path.name: (round(r.score_max_tile, 3), r.classification) for r in results}


def test_worker_count_resolution() -> None:
    assert _worker_count(ScanConfig(scan_path=Path("."), jobs=4)) == 4
    assert _worker_count(ScanConfig(scan_path=Path("."), jobs=0)) == 1  # clamped
    assert _worker_count(ScanConfig(scan_path=Path("."))) >= 1  # cpu count


def test_parallel_matches_serial(tmp_path: Path) -> None:
    _populate(tmp_path, n=6)
    serial = run_scan(ScanConfig(scan_path=tmp_path, jobs=1, use_cache=False))
    parallel = run_scan(ScanConfig(scan_path=tmp_path, jobs=3, use_cache=False))
    assert _scores(serial) == _scores(parallel)


def test_parallel_with_cache(tmp_path: Path) -> None:
    _populate(tmp_path, n=4)
    cfg = ScanConfig(scan_path=tmp_path, jobs=2)  # cache on
    first = run_scan(cfg)
    second = run_scan(cfg)  # served from cache
    assert _scores(first) == _scores(second)
    assert len(first) == 4
