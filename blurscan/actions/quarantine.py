"""Quarantine action: copy/move flagged images.

See DESIGN.md §6. Copies (reversible, default) or moves flagged images into a
quarantine directory with collision-safe names. Honors dry-run by planning the
moves without touching the filesystem. Never alters image pixels.
"""

from __future__ import annotations

import shutil
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from blurscan.models import BLURRY, BORDERLINE, ImageResult


@dataclass
class QuarantineAction:
    """A planned or performed move of one image into quarantine."""

    src: Path
    dst: Path


def _unique_target(dest: Path, name: str, reserved: set[Path]) -> Path:
    """Pick a target path in ``dest`` that collides with neither existing files
    nor already-reserved targets (so dry-run plans stay collision-free too)."""
    candidate = dest / name
    if not candidate.exists() and candidate not in reserved:
        return candidate
    stem, suffix = Path(name).stem, Path(name).suffix
    i = 1
    while True:
        candidate = dest / f"{stem}_{i}{suffix}"
        if not candidate.exists() and candidate not in reserved:
            return candidate
        i += 1


def flagged_results(
    results: Iterable[ImageResult], include_borderline: bool = False
) -> list[ImageResult]:
    """Results eligible for quarantine: blurry (and optionally borderline), no errors."""
    classes = {BLURRY} | ({BORDERLINE} if include_borderline else set())
    return [r for r in results if r.error is None and r.classification in classes]


def quarantine(
    results: Iterable[ImageResult],
    dest: Path | str,
    *,
    move: bool = False,
    dry_run: bool = False,
    include_borderline: bool = False,
    filter_results: bool = True,
) -> list[QuarantineAction]:
    """Copy/move flagged images into ``dest``. Returns the actions (planned if dry-run).

    ``filter_results`` (default True) applies the blurry/borderline classification
    filter to ``results``. Pass ``filter_results=False`` to act on exactly the given
    results — used by the review UI, where the user has already chosen each image
    explicitly and that decision is authoritative.
    """
    dest = Path(dest)
    targets = flagged_results(results, include_borderline) if filter_results else list(results)
    if targets and not dry_run:
        dest.mkdir(parents=True, exist_ok=True)

    reserved: set[Path] = set()
    actions: list[QuarantineAction] = []
    for r in targets:
        target = _unique_target(dest, r.path.name, reserved)
        reserved.add(target)
        actions.append(QuarantineAction(src=r.path, dst=target))
        if not dry_run:
            if move:
                shutil.move(str(r.path), str(target))
            else:
                shutil.copy2(str(r.path), str(target))
    return actions
