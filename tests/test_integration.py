"""End-to-end CLI integration tests (DESIGN.md §8).

Exercises the whole pipeline — walk → score → classify → report/quarantine —
through the public CLI on a synthetic mixed directory, so the pieces are tested
together, not just in isolation.
"""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
import pytest
from numpy.typing import NDArray
from PIL import Image

from blurscan.cli import main


def _checkerboard(size: int = 200, square: int = 20) -> NDArray[np.uint8]:
    idx = (np.arange(size) // square) % 2
    pattern = np.logical_xor(idx[:, None], idx[None, :]).astype(np.uint8) * 255
    return np.stack([pattern] * 3, axis=-1)


@pytest.fixture
def mixed_dir(tmp_path: Path) -> Path:
    sharp = _checkerboard()
    blurred = cv2.GaussianBlur(sharp, (21, 21), 0).astype(np.uint8)
    for i in range(3):
        Image.fromarray(sharp, "RGB").save(tmp_path / f"sharp{i}.png")
        Image.fromarray(blurred, "RGB").save(tmp_path / f"blur{i}.png")
    return tmp_path


def test_report_and_dry_run_copy(mixed_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    base = mixed_dir / "out"
    quar = mixed_dir / "quar"
    code = main([str(mixed_dir), "--report", str(base), "--copy", str(quar), "--dry-run"])
    assert code == 0
    out = capsys.readouterr().out
    assert "Scanned 6 images" in out
    assert base.with_suffix(".csv").exists()
    assert base.with_suffix(".html").exists()
    assert "[dry-run] would copy" in out
    assert not quar.exists()  # dry-run created nothing


def test_json_output_is_valid(mixed_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main([str(mixed_dir), "--json", "--no-cache"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert len(data) == 6
    assert {d["method"] for d in data} == {"laplacian"}


def test_methods_run_end_to_end(mixed_dir: Path) -> None:
    for method in ("laplacian", "motion"):  # ml needs torch (skipped in CI)
        assert main([str(mixed_dir), "--method", method, "--no-cache"]) == 0


def test_real_quarantine_moves_files(mixed_dir: Path) -> None:
    quar = mixed_dir / "quarantine"
    assert main([str(mixed_dir), "--move", str(quar), "--no-cache"]) == 0
    # The blurred frames should have been moved out.
    assert quar.is_dir()
    moved = list(quar.glob("*.png"))
    assert len(moved) >= 1
