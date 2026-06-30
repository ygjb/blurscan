"""Scan pipeline: walk -> load -> score -> classify -> act.

See DESIGN.md §3.3. This module covers walk -> load -> score -> classify and
returns a list of :class:`ImageResult`. Parallelism and caching are layered on in
later issues; actions consume the returned results.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from blurscan.cache import ResultCache, default_cache_path
from blurscan.classifier import classify_scores
from blurscan.detectors import get
from blurscan.detectors.base import Detector
from blurscan.loader import ImageLoadError, is_supported, load_image
from blurscan.models import ImageResult, ScanConfig


def iter_image_paths(cfg: ScanConfig) -> Iterator[Path]:
    """Yield supported image paths under ``cfg.scan_path`` (recursive, sorted)."""
    for path in sorted(cfg.scan_path.rglob("*")):
        if not path.is_file():
            continue
        ext = path.suffix.lower()
        if cfg.formats is not None and ext not in cfg.formats:
            continue
        if not is_supported(path):
            continue
        yield path


def score_path(path: Path, detector: Detector, cfg: ScanConfig) -> ImageResult:
    """Load and score a single image. Decode failures become error results."""
    try:
        rgb = load_image(path, raw_full=cfg.raw_full)
    except ImageLoadError as exc:
        return ImageResult.from_error(path, str(exc), method=detector.name)
    ds = detector.score_image(rgb, cfg)
    h, w = rgb.shape[:2]
    return ImageResult(
        path=path,
        width=int(w),
        height=int(h),
        score_max_tile=ds.score,
        score_global=ds.extras.get("global", 0.0),
        fft_ratio=ds.extras.get("fft_ratio", 0.0),
        classification="",  # assigned below, once the run's distribution is known
        method=detector.name,
    )


def classify_results(
    results: list[ImageResult], detector: Detector, cfg: ScanConfig
) -> None:
    """Assign classifications in place using the run's score distribution.

    Failed loads keep their ``from_error`` classification (blurry); successful
    results are classified together so adaptive mode sees the full distribution.
    """
    ok = [r for r in results if r.error is None]
    classes = classify_scores(
        [r.score_max_tile for r in ok], cfg, detector.default_threshold
    )
    for result, classification in zip(ok, classes, strict=True):
        result.classification = classification


def _score_all(
    cfg: ScanConfig, detector: Detector, cache: ResultCache | None
) -> list[ImageResult]:
    results: list[ImageResult] = []
    for path in iter_image_paths(cfg):
        cached = cache.get(path, cfg.method) if cache is not None else None
        if cached is not None:
            results.append(cached)
            continue
        result = score_path(path, detector, cfg)
        if cache is not None and result.error is None:
            cache.put(result)
        results.append(result)
    return results


def run_scan(cfg: ScanConfig) -> list[ImageResult]:
    """Run the full scan and return one :class:`ImageResult` per image.

    Scoring results are cached on disk (keyed on path+mtime+size+method) when
    ``cfg.use_cache`` is set; classification is always recomputed from the run's
    distribution.
    """
    detector = get(cfg.method)
    if cfg.use_cache:
        with ResultCache(default_cache_path(cfg.scan_path)) as cache:
            results = _score_all(cfg, detector, cache)
    else:
        results = _score_all(cfg, detector, None)
    classify_results(results, detector, cfg)
    return results
