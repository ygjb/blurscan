"""Detector protocol, score type, and registry.

See DESIGN.md §2 / §3.5. A detector turns an RGB image into a comparable
sharpness score (higher = sharper). Detectors self-register here so ``--method``
resolves a name to an implementation without callers knowing the concrete types.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from blurscan.loader import RGBArray
from blurscan.metrics import FloatArray
from blurscan.models import ScanConfig


@dataclass
class DetectorScore:
    """The output of a detector for one image.

    ``score`` is the primary signal (higher = sharper); ``extras`` holds
    method-specific secondary signals; ``tile_scores`` (if present) drives the
    review heatmap (DESIGN.md §4.2).
    """

    score: float
    extras: dict[str, float] = field(default_factory=dict)
    tile_scores: FloatArray | None = None


@runtime_checkable
class Detector(Protocol):
    """Common interface implemented by every detection method."""

    name: str
    default_threshold: float

    def score_image(self, rgb: RGBArray, cfg: ScanConfig) -> DetectorScore: ...


_REGISTRY: dict[str, Detector] = {}


def register(detector: Detector) -> None:
    """Register ``detector`` under its ``name`` (last registration wins)."""
    _REGISTRY[detector.name] = detector


def get(name: str) -> Detector:
    """Resolve a ``--method`` name to its detector, or raise ``KeyError``."""
    try:
        return _REGISTRY[name]
    except KeyError:
        raise KeyError(
            f"unknown detection method {name!r}; available: {available()}"
        ) from None


def available() -> list[str]:
    """Sorted list of registered method names (for CLI choices / --help)."""
    return sorted(_REGISTRY)
