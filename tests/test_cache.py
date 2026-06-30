"""Tests for the SQLite result cache (DESIGN.md §3.3)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from numpy.typing import NDArray
from PIL import Image

import blurscan.pipeline as pipeline
from blurscan.cache import ResultCache, default_cache_path
from blurscan.models import SHARP, ImageResult, ScanConfig


def _checkerboard(size: int = 120, square: int = 12) -> NDArray[np.uint8]:
    idx = (np.arange(size) // square) % 2
    pattern = np.logical_xor(idx[:, None], idx[None, :]).astype(np.uint8) * 255
    return np.stack([pattern] * 3, axis=-1)


def _save(path: Path, size: int = 120) -> Path:
    Image.fromarray(_checkerboard(size), "RGB").save(path)
    return path


def _result(path: Path) -> ImageResult:
    return ImageResult(
        path=path,
        width=120,
        height=120,
        score_max_tile=500.0,
        score_global=200.0,
        fft_ratio=0.4,
        classification=SHARP,
        method="laplacian",
    )


def test_put_get_roundtrip(tmp_path: Path) -> None:
    img = _save(tmp_path / "a.png")
    with ResultCache(tmp_path / "c.sqlite") as cache:
        cache.put(_result(img))
        got = cache.get(img, "laplacian")
    assert got is not None and got.score_max_tile == 500.0


def test_get_miss_when_absent(tmp_path: Path) -> None:
    img = _save(tmp_path / "a.png")
    with ResultCache(tmp_path / "c.sqlite") as cache:
        assert cache.get(img, "laplacian") is None  # nothing stored
        cache.put(_result(img))
        assert cache.get(img, "motion") is None  # different method


def test_get_miss_when_file_changes(tmp_path: Path) -> None:
    img = _save(tmp_path / "a.png", size=120)
    with ResultCache(tmp_path / "c.sqlite") as cache:
        cache.put(_result(img))
        assert cache.get(img, "laplacian") is not None
        _save(img, size=200)  # different content/size
        assert cache.get(img, "laplacian") is None  # stale -> miss


def test_run_scan_serves_from_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _save(tmp_path / "x.png")
    _save(tmp_path / "y.png")
    cfg = ScanConfig(scan_path=tmp_path)  # use_cache defaults True
    pipeline.run_scan(cfg)  # populates cache
    assert default_cache_path(tmp_path).exists()

    loaded: list[Path] = []
    original = pipeline.load_image

    def _spy(path: Path, raw_full: bool = False) -> object:
        loaded.append(path)
        return original(path, raw_full=raw_full)

    monkeypatch.setattr(pipeline, "load_image", _spy)
    results = pipeline.run_scan(cfg)
    assert loaded == []  # everything served from cache, nothing re-decoded
    assert len(results) == 2


def test_no_cache_rescans(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _save(tmp_path / "x.png")
    cfg = ScanConfig(scan_path=tmp_path, use_cache=False)
    pipeline.run_scan(cfg)
    assert not default_cache_path(tmp_path).exists()  # no cache written

    loaded: list[Path] = []
    original = pipeline.load_image

    def _spy(path: Path, raw_full: bool = False) -> object:
        loaded.append(path)
        return original(path, raw_full=raw_full)

    monkeypatch.setattr(pipeline, "load_image", _spy)
    pipeline.run_scan(cfg)
    assert len(loaded) == 1  # re-decoded, no cache
