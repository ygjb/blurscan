"""The ``ml`` detector — learned classifier (DESIGN.md §2.3).

A frozen pretrained torchvision backbone (MobileNetV3-Small) extracts a feature
vector; a tiny logistic-regression head (pure numpy, trained on the labeled
corpus and shipped as ``ml_head.npz``) maps it to a sharp-probability. The score
is that probability ×100, so ``default_threshold=50`` ≈ p(sharp)=0.5.

Torch/torchvision are an **optional** dependency (``pip install blurscan[ml]``),
imported lazily so the base package and CLI work without them. ``--method ml``
raises :class:`MLDependencyError` with an install hint when they are absent, and
:class:`MLModelMissing` when the trained head artifact is not present.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from blurscan.detectors.base import DetectorScore, register
from blurscan.loader import RGBArray
from blurscan.models import ScanConfig

NDArrayF = NDArray[np.float64]

HEAD_ARTIFACT = Path(__file__).with_name("ml_head.npz")
_IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)
_INPUT_SIZE = 224


class MLDependencyError(RuntimeError):
    """Raised when torch/torchvision are required but not installed."""


class MLModelMissing(RuntimeError):
    """Raised when the trained head artifact is unavailable."""


def _lazy_torch() -> tuple[Any, Any]:
    try:
        import torch
        import torchvision
    except ImportError as exc:  # pragma: no cover - exercised via monkeypatch
        raise MLDependencyError(
            "the 'ml' method needs torch + torchvision — install with "
            "`pip install blurscan[ml]`"
        ) from exc
    return torch, torchvision


@lru_cache(maxsize=1)
def _backbone() -> Any:
    """Load and cache the frozen MobileNetV3-Small feature extractor."""
    torch, torchvision = _lazy_torch()
    weights = torchvision.models.MobileNet_V3_Small_Weights.DEFAULT
    model = torchvision.models.mobilenet_v3_small(weights=weights)
    model.eval()
    for param in model.parameters():
        param.requires_grad_(False)
    return model


def extract_features(rgb: RGBArray) -> NDArrayF:
    """Backbone feature vector for one RGB image (numpy, shape (576,))."""
    torch, _ = _lazy_torch()
    model = _backbone()
    import cv2

    resized = cv2.resize(rgb, (_INPUT_SIZE, _INPUT_SIZE), interpolation=cv2.INTER_AREA)
    arr = resized.astype(np.float32) / 255.0
    arr = (arr - _IMAGENET_MEAN) / _IMAGENET_STD
    tensor = torch.from_numpy(arr.transpose(2, 0, 1)).unsqueeze(0)
    with torch.no_grad():
        feats = model.features(tensor)
        pooled = torch.nn.functional.adaptive_avg_pool2d(feats, 1).flatten(1)
    return np.asarray(pooled.squeeze(0).cpu().numpy(), dtype=np.float64)


def _sigmoid(z: NDArrayF) -> NDArrayF:
    return 1.0 / (1.0 + np.exp(-z))


class LogisticHead:
    """A standardized logistic-regression head: p = sigmoid(w·(x-mean)/std + b)."""

    def __init__(self, weight: NDArrayF, bias: float, mean: NDArrayF, std: NDArrayF) -> None:
        self.weight = weight
        self.bias = bias
        self.mean = mean
        self.std = std

    def predict_proba(self, feature: NDArrayF) -> float:
        z = float(self.weight @ ((feature - self.mean) / self.std) + self.bias)
        return float(_sigmoid(np.array(z)))

    def save(self, path: Path) -> None:
        np.savez(path, weight=self.weight, bias=self.bias, mean=self.mean, std=self.std)

    @classmethod
    def load(cls, path: Path) -> LogisticHead:
        if not path.exists():
            raise MLModelMissing(
                f"trained ml head not found at {path}; run `python -m scripts.train_ml`"
            )
        data = np.load(path)
        return cls(
            weight=data["weight"],
            bias=float(data["bias"]),
            mean=data["mean"],
            std=data["std"],
        )


def train_logistic(
    features: NDArrayF, labels: NDArrayF, *, epochs: int = 500, lr: float = 0.1, l2: float = 1e-3
) -> LogisticHead:
    """Fit a logistic regression (numpy GD) on standardized features.

    ``labels`` are 1 for sharp, 0 for blurry.
    """
    mean = features.mean(axis=0)
    std = features.std(axis=0) + 1e-6
    x = (features - mean) / std
    n, d = x.shape
    w = np.zeros(d, dtype=np.float64)
    b = 0.0
    for _ in range(epochs):
        p = _sigmoid(x @ w + b)
        grad_w = x.T @ (p - labels) / n + l2 * w
        grad_b = float((p - labels).mean())
        w -= lr * grad_w
        b -= lr * grad_b
    return LogisticHead(weight=w, bias=b, mean=mean, std=std)


class MLDetector:
    """Learned sharpness classifier (frozen CNN features + logistic head)."""

    name = "ml"
    default_threshold = 50.0  # score = p(sharp) * 100

    def score_image(self, rgb: RGBArray, cfg: ScanConfig) -> DetectorScore:
        head = LogisticHead.load(HEAD_ARTIFACT)
        feature = extract_features(rgb)
        prob = head.predict_proba(feature)
        return DetectorScore(score=prob * 100.0, extras={"p_sharp": prob}, tile_scores=None)


register(MLDetector())
