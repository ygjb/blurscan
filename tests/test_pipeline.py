"""Tests for the serial scan pipeline (DESIGN.md §3.3)."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from numpy.typing import NDArray
from PIL import Image

from blurscan.models import BLURRY, SHARP, ScanConfig
from blurscan.pipeline import iter_image_paths, run_scan


def _checkerboard(size: int = 400, square: int = 20) -> NDArray[np.uint8]:
    idx = (np.arange(size) // square) % 2
    pattern = np.logical_xor(idx[:, None], idx[None, :]).astype(np.uint8) * 255
    return np.stack([pattern] * 3, axis=-1)


def _save(path: Path, arr: NDArray[np.uint8]) -> None:
    Image.fromarray(arr, "RGB").save(path)


def _populate(root: Path) -> None:
    sharp = _checkerboard()
    blurred = cv2.GaussianBlur(sharp, (21, 21), 0).astype(np.uint8)
    _save(root / "sharp.png", sharp)
    (root / "sub").mkdir()
    _save(root / "sub" / "blurred.png", blurred)


def test_run_scan_classifies(tmp_path: Path) -> None:
    _populate(tmp_path)
    results = {p.path.name: p for p in run_scan(ScanConfig(scan_path=tmp_path))}
    assert results["sharp.png"].classification == SHARP
    assert results["blurred.png"].classification == BLURRY
    assert results["sharp.png"].method == "laplacian"
    assert results["sharp.png"].width == 400


def test_run_scan_records_decode_errors(tmp_path: Path) -> None:
    _save(tmp_path / "ok.png", _checkerboard())
    (tmp_path / "broken.png").write_bytes(b"\x89PNG\r\n\x1a\n not a real png")
    results = {p.path.name: p for p in run_scan(ScanConfig(scan_path=tmp_path))}
    broken = results["broken.png"]
    assert broken.error is not None
    assert broken.classification == BLURRY  # errors recorded, not fatal


def test_iter_image_paths_recurses_and_filters(tmp_path: Path) -> None:
    _populate(tmp_path)
    (tmp_path / "notes.txt").write_text("ignore me")
    paths = list(iter_image_paths(ScanConfig(scan_path=tmp_path)))
    names = {p.name for p in paths}
    assert names == {"sharp.png", "blurred.png"}  # .txt skipped, sub/ recursed


def test_iter_image_paths_respects_formats(tmp_path: Path) -> None:
    _save(tmp_path / "a.png", _checkerboard())
    _save(tmp_path / "b.bmp", _checkerboard())
    cfg = ScanConfig(scan_path=tmp_path, formats=(".bmp",))
    names = {p.name for p in iter_image_paths(cfg)}
    assert names == {"b.bmp"}
