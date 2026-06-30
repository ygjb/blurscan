"""Camera RAW loader tests (DESIGN.md §3.2).

RAW files can't be synthesized at test time (rawpy decodes only), so the always-
run tests cover registration and the error path. A real preview/full round-trip
runs against the reconstructed RAW corpus cache (``scripts/fetch_corpus.py``);
skips when the cache is absent (e.g. CI).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from blurscan.loader import (
    ImageLoadError,
    is_supported,
    load_image,
    supported_extensions,
)


def test_raw_extensions_supported() -> None:
    assert {".cr2", ".nef", ".arw", ".dng"} <= supported_extensions()
    assert is_supported("DSC0001.NEF")  # case-insensitive
    assert is_supported("img.dng")


def test_corrupt_raw_raises(tmp_path: Path) -> None:
    bad = tmp_path / "broken.dng"
    bad.write_bytes(b"not a real raw file")
    with pytest.raises(ImageLoadError):
        load_image(bad)


def test_raw_preview_and_full_roundtrip(raw_corpus_files: list[Path]) -> None:
    # Exercise every reconstructed RAW fixture in both decode modes (TESTING §6).
    for raw in raw_corpus_files:
        preview = load_image(raw, raw_full=False)
        assert preview.dtype == np.uint8 and preview.ndim == 3 and preview.shape[2] == 3
        full = load_image(raw, raw_full=True)
        assert full.ndim == 3 and full.shape[2] == 3
