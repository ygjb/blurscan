"""Train the `ml` detector's logistic head on the labeled corpus.

Extracts MobileNetV3-Small features for every labeled image, fits the numpy
logistic head, evaluates a held-out split, and writes the artifact next to the
detector (`blurscan/detectors/ml_head.npz`).

Usage:
    python -m scripts.train_ml [CORPUS_DIR]
Requires the `[ml]` extra (torch + torchvision).
"""

from __future__ import annotations

import sys
from pathlib import Path
from statistics import median

import numpy as np

from blurscan.detectors.ml import HEAD_ARTIFACT, extract_features, train_logistic
from blurscan.loader import is_supported, load_image


def _labeled(corpus: Path) -> tuple[list[Path], list[int]]:
    paths: list[Path] = []
    labels: list[int] = []
    for label_name, label in (("not_blurry", 1), ("blurry", 0)):
        directory = corpus / label_name
        for p in sorted(directory.rglob("*")):
            if p.is_file() and is_supported(p):
                paths.append(p)
                labels.append(label)
    return paths, labels


def _auc(pos: list[float], neg: list[float]) -> float:
    pairs = [1.0 if p > n else 0.5 if p == n else 0.0 for p in pos for n in neg]
    return sum(pairs) / len(pairs)


def main() -> int:
    corpus = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("test_samples/web_corpus")
    paths, labels = _labeled(corpus)
    if not paths:
        print(f"no labeled images under {corpus}", file=sys.stderr)
        return 1
    print(f"extracting features for {len(paths)} images …")
    feats = np.stack([extract_features(load_image(p)) for p in paths])
    y = np.array(labels, dtype=np.float64)

    rng = np.random.default_rng(0)
    idx = rng.permutation(len(paths))
    split = int(0.8 * len(paths))
    tr, te = idx[:split], idx[split:]

    head = train_logistic(feats[tr], y[tr])
    sharp = [head.predict_proba(feats[i]) for i in te if y[i] == 1]
    blurry = [head.predict_proba(feats[i]) for i in te if y[i] == 0]
    print(f"held-out: sharp median p={median(sharp):.3f} blurry median p={median(blurry):.3f}")
    print(f"held-out AUC = {_auc(sharp, blurry):.3f}")

    # Retrain on all data for the shipped artifact.
    train_logistic(feats, y).save(HEAD_ARTIFACT)
    print(f"wrote {HEAD_ARTIFACT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
