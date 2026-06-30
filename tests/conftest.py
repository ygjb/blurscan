"""Shared test fixtures.

Discovers the labeled image corpus (DESIGN.md §8.1). The corpus images are **not**
committed — only manifests under ``test_samples/<corpus>/manifest.csv`` are. Run
``python scripts/fetch_corpus.py`` to reconstruct them into a gitignored cache
(``test_samples/_cache/`` by default, or ``$BLURSCAN_CORPUS_CACHE``). These
fixtures ``pytest.skip`` cleanly when the cache is absent, so the suite still runs
on a fresh clone / in CI (which does not fetch the corpus).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from blurscan.loader import is_supported

REPO = Path(__file__).resolve().parent.parent


def corpus_cache() -> Path:
    """Root of the reconstructed corpus cache (env-overridable)."""
    env = os.environ.get("BLURSCAN_CORPUS_CACHE")
    return Path(env) if env else REPO / "test_samples" / "_cache"


def _labeled_images(label: str) -> list[Path]:
    # The reconstructed cache, plus a legacy in-place layout as a fallback.
    roots = (corpus_cache() / "web_corpus", REPO / "test_samples" / "web_corpus")
    for root in roots:
        directory = root / label
        if directory.is_dir():
            images = sorted(
                p for p in directory.rglob("*") if p.is_file() and is_supported(p)
            )
            if images:
                return images
    return []


def _skip_no_corpus(label: str) -> None:
    pytest.skip(
        f"no labeled '{label}' images in the corpus cache — run "
        "`python scripts/fetch_corpus.py` to reconstruct it"
    )


@pytest.fixture
def blurry_samples() -> list[Path]:
    """Images expected to be blurry; skips if the corpus cache is absent."""
    images = _labeled_images("blurry")
    if not images:
        _skip_no_corpus("blurry")
    return images


@pytest.fixture
def sharp_samples() -> list[Path]:
    """Images expected to be sharp; skips if the corpus cache is absent."""
    images = _labeled_images("not_blurry")
    if not images:
        _skip_no_corpus("not_blurry")
    return images


@pytest.fixture
def raw_corpus_files() -> list[Path]:
    """Reconstructed RAW fixtures; skips if absent."""
    root = corpus_cache() / "raw_corpus"
    files = sorted(p for p in root.glob("*") if is_supported(p)) if root.is_dir() else []
    if not files:
        pytest.skip("no RAW corpus cache — run `python scripts/fetch_corpus.py raw_corpus`")
    return files


@pytest.fixture
def heic_corpus_files() -> list[Path]:
    """Reconstructed HEIC fixtures; skips if absent."""
    root = corpus_cache() / "heic_corpus"
    files = sorted(root.rglob("*.heic")) if root.is_dir() else []
    if not files:
        pytest.skip("no HEIC corpus cache — run `python scripts/fetch_corpus.py heic_corpus`")
    return files
