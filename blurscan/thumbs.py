"""Thumbnail generation.

See DESIGN.md §3.1. Produces small JPEG thumbnails via the shared loader (so all
supported formats work) for embedding in the standalone HTML report and, later,
for serving from the web review UI.
"""

from __future__ import annotations

import base64
import io
from pathlib import Path

from PIL import Image

from blurscan.loader import load_image


def thumbnail_bytes(path: Path | str, max_edge: int = 256, quality: int = 80) -> bytes:
    """Return JPEG bytes of a thumbnail with the longest edge ``max_edge`` px."""
    rgb = load_image(path)
    img = Image.fromarray(rgb, "RGB")
    img.thumbnail((max_edge, max_edge))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def thumbnail_data_uri(path: Path | str, max_edge: int = 256) -> str:
    """Return a self-contained ``data:image/jpeg;base64,...`` URI for ``path``."""
    encoded = base64.b64encode(thumbnail_bytes(path, max_edge)).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"
