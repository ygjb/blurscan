"""Tests for the CLI (DESIGN.md §6)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from numpy.typing import NDArray
from PIL import Image

from blurscan.cli import build_parser, main


def _checkerboard(size: int = 200, square: int = 20) -> NDArray[np.uint8]:
    idx = (np.arange(size) // square) % 2
    pattern = np.logical_xor(idx[:, None], idx[None, :]).astype(np.uint8) * 255
    return np.stack([pattern] * 3, axis=-1)


@pytest.fixture
def photos(tmp_path: Path) -> Path:
    Image.fromarray(_checkerboard(), "RGB").save(tmp_path / "sharp.png")
    import cv2

    blurred = cv2.GaussianBlur(_checkerboard(), (21, 21), 0).astype(np.uint8)
    Image.fromarray(blurred, "RGB").save(tmp_path / "blurry.png")
    return tmp_path


def test_parser_exposes_methods() -> None:
    parser = build_parser()
    ns = parser.parse_args(["x", "--method", "laplacian", "--adaptive"])
    assert ns.method == "laplacian"
    assert ns.adaptive == 10.0  # bare --adaptive -> default 10%


def test_no_args_prints_help() -> None:
    assert main([]) == 0


def test_missing_directory_errors() -> None:
    assert main(["/definitely/not/a/dir"]) == 2


def test_summary_run(photos: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main([str(photos)]) == 0
    out = capsys.readouterr().out
    assert "Scanned 2 images" in out


def test_report_run(photos: Path, capsys: pytest.CaptureFixture[str]) -> None:
    base = photos / "out"
    assert main([str(photos), "--report", str(base)]) == 0
    assert base.with_suffix(".csv").exists()
    assert base.with_suffix(".html").exists()
    assert "Wrote" in capsys.readouterr().out


def test_json_run(photos: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main([str(photos), "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert len(data) == 2
    assert {d["classification"] for d in data}  # present
    assert all("score_max_tile" in d for d in data)
