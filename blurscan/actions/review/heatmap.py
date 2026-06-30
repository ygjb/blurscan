"""Per-tile sharpness heatmap overlay for the review detail view (DESIGN.md §4.2).

Re-scores an image with its detector to recover the per-tile scores, then blends
a JET colormap of those scores over the grayscale image so a reviewer can see
*where* sharpness is concentrated. Returns ``None`` for methods that produce no
tile grid (e.g. ``ml``).
"""

from __future__ import annotations

import cv2
import numpy as np

from blurscan.detectors import get
from blurscan.loader import load_image
from blurscan.metrics import downscale, to_grayscale
from blurscan.models import ImageResult, ScanConfig


def heatmap_jpeg(result: ImageResult, cfg: ScanConfig) -> bytes | None:
    """Render a sharpness heatmap overlay for ``result`` as JPEG bytes.

    Returns ``None`` if the detector exposes no per-tile scores.
    """
    detector = get(result.method)
    rgb = load_image(result.path, raw_full=cfg.raw_full)
    tiles = detector.score_image(rgb, cfg).tile_scores
    if tiles is None:
        return None

    spread = float(tiles.max() - tiles.min())
    norm = (tiles - tiles.min()) / spread if spread > 0 else np.zeros_like(tiles)

    small = downscale(rgb, cfg.working_size)
    h, w = small.shape[:2]
    heat = cv2.resize((norm * 255).astype(np.uint8), (w, h), interpolation=cv2.INTER_NEAREST)
    colored = cv2.cvtColor(cv2.applyColorMap(heat, cv2.COLORMAP_JET), cv2.COLOR_BGR2RGB)
    gray3 = cv2.cvtColor(to_grayscale(small), cv2.COLOR_GRAY2RGB)
    blended = (0.55 * gray3 + 0.45 * colored).astype(np.uint8)

    ok, buf = cv2.imencode(".jpg", cv2.cvtColor(blended, cv2.COLOR_RGB2BGR))
    if not ok:
        return None
    return bytes(buf.tobytes())
