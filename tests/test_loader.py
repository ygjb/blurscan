"""Tests for the image loader (DESIGN.md §3.2).

Uses synthetic images generated at test time, so these run in CI with no
committed fixtures.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from blurscan.loader import (
    ImageLoadError,
    is_supported,
    load_image,
    supported_extensions,
)


def _write(path: Path, mode: str = "RGB", size: tuple[int, int] = (32, 24)) -> Path:
    rng = np.random.default_rng(0)
    if mode == "RGB":
        data = rng.integers(0, 256, size=(size[1], size[0], 3), dtype=np.uint8)
        Image.fromarray(data, "RGB").save(path)
    else:  # grayscale "L"
        data = rng.integers(0, 256, size=(size[1], size[0]), dtype=np.uint8)
        Image.fromarray(data, "L").save(path)
    return path


@pytest.mark.parametrize("ext", [".png", ".jpg", ".tiff", ".bmp"])
def test_roundtrip_shape_and_dtype(tmp_path: Path, ext: str) -> None:
    p = _write(tmp_path / f"img{ext}")
    arr = load_image(p)
    assert arr.dtype == np.uint8
    assert arr.ndim == 3 and arr.shape[2] == 3
    assert arr.shape[0] == 24 and arr.shape[1] == 32


def test_grayscale_promoted_to_rgb(tmp_path: Path) -> None:
    p = _write(tmp_path / "gray.png", mode="L")
    arr = load_image(p)
    assert arr.shape[2] == 3  # L -> RGB


def test_unsupported_extension_raises(tmp_path: Path) -> None:
    p = tmp_path / "data.xyz"
    p.write_bytes(b"not an image")
    with pytest.raises(ImageLoadError):
        load_image(p)


def test_corrupt_file_raises(tmp_path: Path) -> None:
    p = tmp_path / "broken.png"
    p.write_bytes(b"\x89PNG\r\n\x1a\n garbage")
    with pytest.raises(ImageLoadError):
        load_image(p)


def test_registry_helpers() -> None:
    assert ".png" in supported_extensions()
    assert is_supported("a.JPG")  # case-insensitive
    assert not is_supported("a.xyz")  # unknown extension stays unsupported
