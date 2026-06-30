"""Shared test fixtures.

Discovers the user's local labeled image set under ``test_samples/`` (DESIGN.md
§8.1). That directory is gitignored and absent in CI, so fixtures that depend on
it ``pytest.skip`` cleanly — the synthetic-image tests are the CI gate.

Layout:
    test_samples/blurry/      -> images expected to classify as blurry
    test_samples/not_blurry/  -> images expected to classify as sharp
"""

from __future__ import annotations

from pathlib import Path

import pytest

from blurscan.loader import is_supported

SAMPLES_DIR = Path(__file__).resolve().parent.parent / "test_samples"


def _labeled_images(subdir: str) -> list[Path]:
    root = SAMPLES_DIR / subdir
    if not root.is_dir():
        return []
    return sorted(p for p in root.rglob("*") if p.is_file() and is_supported(p))


@pytest.fixture
def blurry_samples() -> list[Path]:
    """Images expected to be blurry; skips if none are present locally."""
    images = _labeled_images("blurry")
    if not images:
        pytest.skip("no images in test_samples/blurry (local-only fixture)")
    return images


@pytest.fixture
def sharp_samples() -> list[Path]:
    """Images expected to be sharp; skips if none are present locally."""
    images = _labeled_images("not_blurry")
    if not images:
        pytest.skip("no images in test_samples/not_blurry (local-only fixture)")
    return images
