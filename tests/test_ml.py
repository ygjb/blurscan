"""Tests for the learned (ml) detector (DESIGN.md §2.3).

Torch-free tests (registration, head math, error paths) run everywhere. The real
feature-extraction / scoring tests need torch and are skipped in CI (where the
`[ml]` extra is not installed and weight downloads are not wanted).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from statistics import median

import numpy as np
import pytest

from blurscan.detectors import available, get
from blurscan.detectors import ml as mlmod
from blurscan.detectors.ml import (
    HEAD_ARTIFACT,
    LogisticHead,
    MLDependencyError,
    MLModelMissing,
    train_logistic,
)
from blurscan.models import ScanConfig

HAVE_TORCH = importlib.util.find_spec("torch") is not None
CFG = ScanConfig(scan_path=Path("."))


def test_ml_registered_without_torch() -> None:
    # Registration must not require torch (lazy import).
    assert "ml" in available()
    assert get("ml").name == "ml"


def test_logistic_head_learns_separable_data() -> None:
    rng = np.random.default_rng(0)
    sharp = rng.normal(2.0, 0.5, size=(40, 4))
    blurry = rng.normal(-2.0, 0.5, size=(40, 4))
    feats = np.vstack([sharp, blurry])
    labels = np.array([1.0] * 40 + [0.0] * 40)
    head = train_logistic(feats, labels)
    assert head.predict_proba(np.full(4, 2.0)) > 0.8
    assert head.predict_proba(np.full(4, -2.0)) < 0.2


def test_logistic_head_save_load(tmp_path: Path) -> None:
    head = LogisticHead(
        weight=np.array([1.0, -1.0]),
        bias=0.5,
        mean=np.zeros(2),
        std=np.ones(2),
    )
    path = tmp_path / "head.npz"
    head.save(path)
    loaded = LogisticHead.load(path)
    sample = np.array([1.0, 0.0])
    assert loaded.predict_proba(sample) == pytest.approx(head.predict_proba(sample))


def test_model_missing_raises(tmp_path: Path) -> None:
    with pytest.raises(MLModelMissing):
        LogisticHead.load(tmp_path / "absent.npz")


def test_dependency_error_when_torch_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "torch", None)  # makes `import torch` raise
    with pytest.raises(MLDependencyError):
        mlmod._lazy_torch()


def test_artifact_is_shipped() -> None:
    assert HEAD_ARTIFACT.exists(), "trained ml_head.npz must be committed"


@pytest.mark.skipif(not HAVE_TORCH, reason="torch not installed ([ml] extra)")
def test_extract_features_shape() -> None:
    arr = (np.random.default_rng(0).random((64, 64, 3)) * 255).astype(np.uint8)
    feats = mlmod.extract_features(arr)
    assert feats.ndim == 1 and feats.shape[0] == 576


@pytest.mark.skipif(not HAVE_TORCH, reason="torch not installed ([ml] extra)")
def test_ml_ranks_real_corpus(
    blurry_samples: list[Path], sharp_samples: list[Path]
) -> None:
    from blurscan.loader import load_image

    detector = get("ml")
    sharp = [detector.score_image(load_image(p), CFG).score for p in sharp_samples[:8]]
    blurry = [detector.score_image(load_image(p), CFG).score for p in blurry_samples[:8]]
    assert median(sharp) > median(blurry)
