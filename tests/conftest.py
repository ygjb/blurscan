"""Shared test fixtures.

Discovers the labeled image corpus under ``test_samples/`` (DESIGN.md §8.1). The
corpus is **tracked in git** under ``test_samples/web_corpus/{blurry,not_blurry}``
(Creative-Commons images), so these fixtures run in CI as well as locally. A
legacy top-level ``test_samples/{blurry,not_blurry}`` layout is still honored if
present. Fixtures ``pytest.skip`` cleanly when no corpus is found.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from blurscan.loader import is_supported

SAMPLES_DIR = Path(__file__).resolve().parent.parent / "test_samples"
# Search the tracked web_corpus first, then a legacy top-level layout.
_LABEL_ROOTS = (SAMPLES_DIR / "web_corpus", SAMPLES_DIR)


def _labeled_images(label: str) -> list[Path]:
    for root in _LABEL_ROOTS:
        directory = root / label
        if directory.is_dir():
            images = sorted(
                p for p in directory.rglob("*") if p.is_file() and is_supported(p)
            )
            if images:
                return images
    return []


@pytest.fixture
def blurry_samples() -> list[Path]:
    """Images expected to be blurry; skips if the corpus is absent."""
    images = _labeled_images("blurry")
    if not images:
        pytest.skip("no labeled 'blurry' images under test_samples/")
    return images


@pytest.fixture
def sharp_samples() -> list[Path]:
    """Images expected to be sharp; skips if the corpus is absent."""
    images = _labeled_images("not_blurry")
    if not images:
        pytest.skip("no labeled 'not_blurry' images under test_samples/")
    return images
