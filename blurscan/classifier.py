"""Classify sharpness scores into sharp/borderline/blurry.

See DESIGN.md §2.5. Thresholds do not transfer across methods, so the floor is
resolved from the detector's ``default_threshold`` unless ``--threshold`` is set.
A borderline band sits just above the floor; adaptive mode additionally surfaces
the bottom ``PCT``% of the run's score distribution for review — the primary mode
for methods that rank better than they cleanly separate.
"""

from __future__ import annotations

from blurscan.models import BLURRY, BORDERLINE, SHARP, ScanConfig

# Width of the borderline band above the floor, as a fraction of the floor.
BORDERLINE_MARGIN = 0.25


def resolve_threshold(cfg: ScanConfig, default_threshold: float) -> float:
    """The active floor: explicit ``--threshold`` if set, else the method default."""
    return default_threshold if cfg.threshold is None else cfg.threshold


def classify_scores(
    scores: list[float], cfg: ScanConfig, default_threshold: float
) -> list[str]:
    """Classify a run's primary scores into sharp/borderline/blurry.

    Operates on the whole list because adaptive mode is relative to the run's
    distribution.
    """
    floor = resolve_threshold(cfg, default_threshold)
    upper = floor * (1.0 + BORDERLINE_MARGIN)

    classes: list[str] = []
    for score in scores:
        if score < floor:
            classes.append(BLURRY)
        elif score < upper:
            classes.append(BORDERLINE)
        else:
            classes.append(SHARP)

    if cfg.adaptive_pct is not None and scores:
        k = max(1, int(len(scores) * cfg.adaptive_pct / 100.0))
        lowest_first = sorted(range(len(scores)), key=lambda i: scores[i])
        for i in lowest_first[:k]:
            # Surface the bottom slice for review, but never upgrade a blurry call.
            if classes[i] == SHARP:
                classes[i] = BORDERLINE
    return classes


def classify_one(score: float, cfg: ScanConfig, default_threshold: float) -> str:
    """Classify a single score (no adaptive context)."""
    return classify_scores([score], cfg, default_threshold)[0]
