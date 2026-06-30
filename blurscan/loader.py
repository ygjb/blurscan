"""Format-aware image loading to a normalized RGB ndarray.

See DESIGN.md §3.2. ``load_image`` dispatches on file extension through a small
registry so additional decoders (HEIC via pillow-heif, RAW via rawpy) can be
registered in later issues without touching callers. Every loader returns an
``H x W x 3`` ``uint8`` RGB array; failures raise :class:`ImageLoadError`.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from PIL import Image, UnidentifiedImageError

RGBArray = NDArray[np.uint8]
LoaderFunc = Callable[[Path], RGBArray]


class ImageLoadError(Exception):
    """Raised when an image cannot be decoded."""


# Extension (lowercase, with dot) -> decoder. Populated below and extended by
# the HEIC/RAW issues via :func:`register_loader`.
_LOADERS: dict[str, LoaderFunc] = {}


def register_loader(extensions: Iterable[str], func: LoaderFunc) -> None:
    """Register ``func`` as the decoder for each extension (e.g. ``".heic"``)."""
    for ext in extensions:
        _LOADERS[ext.lower()] = func


def supported_extensions() -> set[str]:
    """Return the set of currently registered, decodable extensions."""
    return set(_LOADERS)


def is_supported(path: Path | str) -> bool:
    """True if ``path``'s extension has a registered decoder."""
    return Path(path).suffix.lower() in _LOADERS


def _load_with_pillow(path: Path) -> RGBArray:
    """Decode a Pillow-supported image to an RGB uint8 array."""
    try:
        with Image.open(path) as img:
            rgb = img.convert("RGB")
            return np.asarray(rgb, dtype=np.uint8)
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ImageLoadError(f"failed to decode {path}: {exc}") from exc


def load_image(path: Path | str) -> RGBArray:
    """Load ``path`` as an ``H x W x 3`` uint8 RGB array.

    Raises :class:`ImageLoadError` for unsupported extensions or decode failures.
    """
    path = Path(path)
    loader = _LOADERS.get(path.suffix.lower())
    if loader is None:
        raise ImageLoadError(f"unsupported image extension: {path.suffix!r} ({path})")
    arr = loader(path)
    if arr.ndim != 3 or arr.shape[2] != 3:
        raise ImageLoadError(f"decoder returned non-RGB array for {path}: shape {arr.shape}")
    return arr


# Standard raster formats handled by Pillow out of the box (DESIGN.md §3.2).
register_loader(
    (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"),
    _load_with_pillow,
)
