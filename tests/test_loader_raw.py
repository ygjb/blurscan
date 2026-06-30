"""Camera RAW loader tests (DESIGN.md §3.2).

RAW files can't be synthesized at test time (rawpy decodes only), so the always-
run tests cover registration and the error path. A real preview/full round-trip
runs only if a local RAW fixture exists under ``test_samples/`` (skips in CI).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from blurscan.loader import (
    RAW_EXTENSIONS,
    ImageLoadError,
    is_supported,
    load_image,
    supported_extensions,
)

SAMPLES = Path(__file__).resolve().parent.parent / "test_samples"


def test_raw_extensions_supported() -> None:
    assert {".cr2", ".nef", ".arw", ".dng"} <= supported_extensions()
    assert is_supported("DSC0001.NEF")  # case-insensitive
    assert is_supported("img.dng")


def test_corrupt_raw_raises(tmp_path: Path) -> None:
    bad = tmp_path / "broken.dng"
    bad.write_bytes(b"not a real raw file")
    with pytest.raises(ImageLoadError):
        load_image(bad)


def _find_raw() -> Path | None:
    if not SAMPLES.is_dir():
        return None
    for p in SAMPLES.rglob("*"):
        if p.is_file() and p.suffix.lower() in RAW_EXTENSIONS:
            return p
    return None


def test_raw_preview_and_full_roundtrip() -> None:
    raw = _find_raw()
    if raw is None:
        pytest.skip("no local RAW fixture under test_samples/")
    preview = load_image(raw, raw_full=False)
    assert preview.dtype == np.uint8 and preview.ndim == 3 and preview.shape[2] == 3
    full = load_image(raw, raw_full=True)
    assert full.ndim == 3 and full.shape[2] == 3
