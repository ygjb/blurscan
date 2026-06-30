"""Format-aware image loading to a normalized RGB ndarray.

See DESIGN.md §3.2. ``load_image`` dispatches on file extension through a small
registry so additional decoders (HEIC via pillow-heif, RAW via rawpy) can be
registered in later issues without touching callers. Every loader returns an
``H x W x 3`` ``uint8`` RGB array; failures raise :class:`ImageLoadError`.
"""

from __future__ import annotations

import io
from collections.abc import Callable, Iterable
from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from PIL import Image, UnidentifiedImageError

RGBArray = NDArray[np.uint8]
LoaderFunc = Callable[[Path], RGBArray]

# Camera RAW extensions, decoded via rawpy (DESIGN.md §3.2). Handled separately
# from the registry because they honor the ``raw_full`` option.
RAW_EXTENSIONS = frozenset(
    {".cr2", ".cr3", ".nef", ".arw", ".dng", ".raf", ".rw2", ".orf", ".pef", ".srw"}
)


class ImageLoadError(Exception):
    """Raised when an image cannot be decoded."""


# Extension (lowercase, with dot) -> decoder. Populated below and extended by
# the HEIC issue via :func:`register_loader`.
_LOADERS: dict[str, LoaderFunc] = {}


def register_loader(extensions: Iterable[str], func: LoaderFunc) -> None:
    """Register ``func`` as the decoder for each extension (e.g. ``".heic"``)."""
    for ext in extensions:
        _LOADERS[ext.lower()] = func


def supported_extensions() -> set[str]:
    """Return the set of currently decodable extensions (registry + RAW)."""
    return set(_LOADERS) | set(RAW_EXTENSIONS)


def is_supported(path: Path | str) -> bool:
    """True if ``path``'s extension can be decoded."""
    ext = Path(path).suffix.lower()
    return ext in _LOADERS or ext in RAW_EXTENSIONS


def _load_with_pillow(path: Path) -> RGBArray:
    """Decode a Pillow-supported image to an RGB uint8 array."""
    try:
        with Image.open(path) as img:
            rgb = img.convert("RGB")
            return np.asarray(rgb, dtype=np.uint8)
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ImageLoadError(f"failed to decode {path}: {exc}") from exc


def _load_raw(path: Path, raw_full: bool) -> RGBArray:
    """Decode a camera RAW file via rawpy.

    Default fast path extracts the embedded JPEG/bitmap preview (plenty for blur
    scoring); ``raw_full`` demosaics the full sensor data instead. Falls back to
    full demosaic if no usable preview is present.
    """
    import rawpy

    try:
        if not raw_full:
            with rawpy.imread(str(path)) as raw:
                try:
                    thumb = raw.extract_thumb()
                except (rawpy.LibRawNoThumbnailError, rawpy.LibRawUnsupportedThumbnailError):
                    thumb = None
            if thumb is not None:
                if thumb.format == rawpy.ThumbFormat.JPEG:
                    with Image.open(io.BytesIO(thumb.data)) as img:
                        return np.asarray(img.convert("RGB"), dtype=np.uint8)
                if thumb.format == rawpy.ThumbFormat.BITMAP:
                    return np.asarray(thumb.data, dtype=np.uint8)
        # Full demosaic (explicit --raw-full, or no preview available).
        with rawpy.imread(str(path)) as raw:
            return np.asarray(raw.postprocess(use_camera_wb=True), dtype=np.uint8)
    except (rawpy.LibRawError, OSError, ValueError) as exc:
        raise ImageLoadError(f"failed to decode RAW {path}: {exc}") from exc


def load_image(path: Path | str, raw_full: bool = False) -> RGBArray:
    """Load ``path`` as an ``H x W x 3`` uint8 RGB array.

    ``raw_full`` only affects RAW files (preview vs. full demosaic). Raises
    :class:`ImageLoadError` for unsupported extensions or decode failures.
    """
    path = Path(path)
    ext = path.suffix.lower()
    if ext in RAW_EXTENSIONS:
        arr = _load_raw(path, raw_full)
    else:
        loader = _LOADERS.get(ext)
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


def _register_heif() -> None:
    """Register the HEIF/HEIC opener so Pillow can decode iPhone images."""
    import pillow_heif

    pillow_heif.register_heif_opener()
    register_loader((".heic", ".heif"), _load_with_pillow)


_register_heif()
