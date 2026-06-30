"""Core data models for blurscan.

See DESIGN.md §3.4. ``ImageResult`` is the per-image record produced by the
pipeline and persisted by the cache; ``ScanConfig`` captures the resolved CLI
options that parameterize a scan.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Classification labels (DESIGN.md §2.3).
SHARP = "sharp"
BORDERLINE = "borderline"
BLURRY = "blurry"

CLASSIFICATIONS = (SHARP, BORDERLINE, BLURRY)


@dataclass
class ScanConfig:
    """Resolved options for a single scan run.

    Mirrors the CLI surface in DESIGN.md §6. Defaults match the documented
    defaults so a bare ``ScanConfig(scan_path=...)`` is a sensible scan.
    """

    scan_path: Path
    threshold: float = 100.0
    adaptive_pct: float | None = None  # None = adaptive mode off
    grid: int = 4
    working_size: int = 1000
    raw_full: bool = False
    formats: tuple[str, ...] | None = None  # None = all supported extensions
    jobs: int | None = None  # None = default to CPU count
    use_cache: bool = True
    dry_run: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "scan_path": str(self.scan_path),
            "threshold": self.threshold,
            "adaptive_pct": self.adaptive_pct,
            "grid": self.grid,
            "working_size": self.working_size,
            "raw_full": self.raw_full,
            "formats": list(self.formats) if self.formats is not None else None,
            "jobs": self.jobs,
            "use_cache": self.use_cache,
            "dry_run": self.dry_run,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ScanConfig:
        formats = data.get("formats")
        return cls(
            scan_path=Path(data["scan_path"]),
            threshold=data.get("threshold", 100.0),
            adaptive_pct=data.get("adaptive_pct"),
            grid=data.get("grid", 4),
            working_size=data.get("working_size", 1000),
            raw_full=data.get("raw_full", False),
            formats=tuple(formats) if formats is not None else None,
            jobs=data.get("jobs"),
            use_cache=data.get("use_cache", True),
            dry_run=data.get("dry_run", False),
        )


@dataclass
class ImageResult:
    """The analysis result for one image.

    ``score_max_tile`` is the primary decision metric (max over tiles, DESIGN.md
    §2.1); ``score_global`` and ``fft_ratio`` are secondary signals. A non-None
    ``error`` means decode/IO failed and the score fields are not meaningful.
    """

    path: Path
    width: int
    height: int
    score_max_tile: float
    score_global: float
    fft_ratio: float
    classification: str
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "width": self.width,
            "height": self.height,
            "score_max_tile": self.score_max_tile,
            "score_global": self.score_global,
            "fft_ratio": self.fft_ratio,
            "classification": self.classification,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ImageResult:
        return cls(
            path=Path(data["path"]),
            width=int(data["width"]),
            height=int(data["height"]),
            score_max_tile=float(data["score_max_tile"]),
            score_global=float(data["score_global"]),
            fft_ratio=float(data["fft_ratio"]),
            classification=data["classification"],
            error=data.get("error"),
        )

    @classmethod
    def from_error(cls, path: Path, error: str) -> ImageResult:
        """Construct a result representing a failed load/score for ``path``."""
        return cls(
            path=path,
            width=0,
            height=0,
            score_max_tile=0.0,
            score_global=0.0,
            fft_ratio=0.0,
            classification=BLURRY,
            error=error,
        )


@dataclass
class ScanSummary:
    """Aggregate counts for a completed scan."""

    results: list[ImageResult] = field(default_factory=list)

    def count(self, classification: str) -> int:
        return sum(1 for r in self.results if r.classification == classification)
