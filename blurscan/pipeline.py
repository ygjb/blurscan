"""Scan pipeline: walk -> load -> score -> classify -> act.

See DESIGN.md §3.3. This module covers walk -> load -> score -> classify and
returns a list of :class:`ImageResult`. Parallelism and caching are layered on in
later issues; actions consume the returned results.
"""

from __future__ import annotations

import multiprocessing
import os
from collections.abc import Iterator
from concurrent.futures import ProcessPoolExecutor
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


def _worker_count(cfg: ScanConfig) -> int:
    """Resolve worker count: ``--jobs`` if set, else the CPU count (min 1)."""
    if cfg.jobs is not None:
        return max(1, cfg.jobs)
    return os.cpu_count() or 1


def _score_one(args: tuple[Path, ScanConfig]) -> ImageResult:
    """Top-level worker for the process pool (must be importable & picklable).

    Re-resolves the detector from the registry inside the worker process rather
    than pickling it. Touches no cache/DB (the main process owns the cache).
    """
    path, cfg = args
    return score_path(path, get(cfg.method), cfg)


def _score_misses(cfg: ScanConfig, paths: list[Path]) -> dict[Path, ImageResult]:
    """Score the given paths, in parallel when more than one worker is requested."""
    workers = _worker_count(cfg)
    if workers == 1 or len(paths) <= 1:
        detector = get(cfg.method)
        return {p: score_path(p, detector, cfg) for p in paths}
    # "spawn" avoids fork-in-multithreaded-process deadlocks (OpenCV/NumPy spin
    # up threads) that Python 3.12 warns about.
    ctx = multiprocessing.get_context("spawn")
    with ProcessPoolExecutor(max_workers=workers, mp_context=ctx) as executor:
        scored = executor.map(_score_one, [(p, cfg) for p in paths])
        return {r.path: r for r in scored}


def run_scan(cfg: ScanConfig) -> list[ImageResult]:
    """Run the full scan and return one :class:`ImageResult` per image.

    Scoring is parallelized across ``--jobs`` worker processes (default: CPU
    count) and cached on disk (keyed on path+mtime+size+method) when
    ``cfg.use_cache`` is set. Cache reads/writes happen only in the main process.
    Classification is always recomputed from the run's distribution.
    """
    detector = get(cfg.method)
    paths = list(iter_image_paths(cfg))
    cache = ResultCache(default_cache_path(cfg.scan_path)) if cfg.use_cache else None
    try:
        by_path: dict[Path, ImageResult] = {}
        misses: list[Path] = []
        for path in paths:
            cached = cache.get(path, cfg.method) if cache is not None else None
            if cached is not None:
                by_path[path] = cached
            else:
                misses.append(path)
        for path, result in _score_misses(cfg, misses).items():
            by_path[path] = result
            if cache is not None and result.error is None:
                cache.put(result)
    finally:
        if cache is not None:
            cache.close()

    results = [by_path[path] for path in paths]
    classify_results(results, detector, cfg)
    return results
