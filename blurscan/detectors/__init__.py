"""Pluggable detection methods, selected by ``--method`` (DESIGN.md §2, §3.5).

Public API re-exported from :mod:`blurscan.detectors.base`. Importing this
package registers the built-in detectors as a side effect.
"""

from __future__ import annotations

# Import built-in detectors for their registration side effects.
from blurscan.detectors import laplacian as _laplacian  # noqa: F401  (registers "laplacian")
from blurscan.detectors import ml as _ml  # noqa: F401  (registers "ml"; torch lazy)
from blurscan.detectors import motion as _motion  # noqa: F401  (registers "motion")
from blurscan.detectors.base import (
    Detector,
    DetectorScore,
    available,
    get,
    register,
)

__all__ = ["Detector", "DetectorScore", "available", "get", "register"]
