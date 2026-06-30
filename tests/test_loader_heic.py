"""HEIC/HEIF loader tests (DESIGN.md §3.2).

Uses a synthetic HEIC encoded at test time (no committed fixture), so this runs
in CI. Skips only if the local libheif build can't encode.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from numpy.typing import NDArray
from PIL import Image

from blurscan.loader import is_supported, load_image, supported_extensions


def test_heic_extensions_registered() -> None:
    assert {".heic", ".heif"} <= supported_extensions()
    assert is_supported("photo.HEIC")  # case-insensitive


def test_heic_roundtrip(tmp_path: Path) -> None:
    import pillow_heif

    pillow_heif.register_heif_opener()
    arr: NDArray[np.uint8] = np.random.default_rng(0).integers(
        0, 256, size=(40, 60, 3), dtype=np.uint8
    )
    path = tmp_path / "sample.heic"
    try:
        Image.fromarray(arr, "RGB").save(path)
    except Exception as exc:  # noqa: BLE001 - encoder may be unavailable in some builds
        pytest.skip(f"libheif cannot encode here: {exc}")

    loaded = load_image(path)
    assert loaded.dtype == np.uint8
    assert loaded.shape == (40, 60, 3)


def test_heic_corpus_decodes(heic_corpus_files: list[Path]) -> None:
    # Every reconstructed HEIC fixture must decode to RGB (skips if cache absent).
    for heic in heic_corpus_files:
        rgb = load_image(heic)
        assert rgb.dtype == np.uint8 and rgb.ndim == 3 and rgb.shape[2] == 3
