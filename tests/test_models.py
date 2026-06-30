"""Tests for the core data models (DESIGN.md §3.4)."""

from __future__ import annotations

from pathlib import Path

from blurscan.models import (
    BLURRY,
    SHARP,
    ImageResult,
    ScanConfig,
    ScanSummary,
)


def _sample_result() -> ImageResult:
    return ImageResult(
        path=Path("/photos/a.jpg"),
        width=4000,
        height=3000,
        score_max_tile=250.5,
        score_global=120.0,
        fft_ratio=0.42,
        classification=SHARP,
    )


def test_image_result_roundtrip() -> None:
    r = _sample_result()
    restored = ImageResult.from_dict(r.to_dict())
    assert restored == r
    assert isinstance(restored.path, Path)


def test_image_result_from_error() -> None:
    r = ImageResult.from_error(Path("/photos/bad.heic"), "decode failed")
    assert r.error == "decode failed"
    assert r.classification == BLURRY
    assert ImageResult.from_dict(r.to_dict()) == r


def test_scan_config_defaults() -> None:
    cfg = ScanConfig(scan_path=Path("/photos"))
    assert cfg.threshold is None  # resolved from the detector's default
    assert cfg.grid == 4
    assert cfg.working_size == 1000
    assert cfg.adaptive_pct is None
    assert cfg.use_cache is True


def test_scan_config_roundtrip_with_formats() -> None:
    cfg = ScanConfig(scan_path=Path("/photos"), formats=(".jpg", ".png"), adaptive_pct=10.0)
    restored = ScanConfig.from_dict(cfg.to_dict())
    assert restored == cfg
    assert restored.formats == (".jpg", ".png")


def test_scan_summary_counts() -> None:
    summary = ScanSummary(results=[_sample_result(), ImageResult.from_error(Path("x"), "e")])
    assert summary.count(SHARP) == 1
    assert summary.count(BLURRY) == 1
