"""Tests for classification (DESIGN.md §2.5)."""

from __future__ import annotations

from pathlib import Path

from blurscan.classifier import (
    BORDERLINE_MARGIN,
    classify_one,
    classify_scores,
    resolve_threshold,
)
from blurscan.models import BLURRY, BORDERLINE, SHARP, ScanConfig

DEFAULT = 100.0


def _cfg(**kw: object) -> ScanConfig:
    return ScanConfig(scan_path=Path("."), **kw)  # type: ignore[arg-type]


def test_resolve_threshold_uses_method_default_when_unset() -> None:
    assert resolve_threshold(_cfg(), DEFAULT) == DEFAULT


def test_resolve_threshold_honors_explicit() -> None:
    assert resolve_threshold(_cfg(threshold=42.0), DEFAULT) == 42.0


def test_bands() -> None:
    upper = DEFAULT * (1.0 + BORDERLINE_MARGIN)  # 125
    cfg = _cfg()
    assert classify_one(DEFAULT - 1, cfg, DEFAULT) == BLURRY
    assert classify_one(DEFAULT, cfg, DEFAULT) == BORDERLINE  # at floor -> borderline
    assert classify_one(upper - 1, cfg, DEFAULT) == BORDERLINE
    assert classify_one(upper, cfg, DEFAULT) == SHARP


def test_adaptive_marks_bottom_pct_as_borderline() -> None:
    # All well above the floor -> all SHARP without adaptive.
    scores = [200.0, 300.0, 400.0, 500.0, 600.0, 700.0, 800.0, 900.0, 1000.0, 1100.0]
    base = classify_scores(scores, _cfg(), DEFAULT)
    assert set(base) == {SHARP}

    adaptive = classify_scores(scores, _cfg(adaptive_pct=20.0), DEFAULT)
    # Bottom 20% (the two lowest: 200, 300) become borderline.
    assert adaptive[0] == BORDERLINE
    assert adaptive[1] == BORDERLINE
    assert adaptive[2] == SHARP


def test_adaptive_never_upgrades_blurry() -> None:
    scores = [10.0, 20.0, 1000.0]  # two below floor
    adaptive = classify_scores(scores, _cfg(adaptive_pct=50.0), DEFAULT)
    assert adaptive[0] == BLURRY  # stays blurry, not bumped to borderline
    assert adaptive[1] == BLURRY


def test_empty_scores() -> None:
    assert classify_scores([], _cfg(adaptive_pct=10.0), DEFAULT) == []
