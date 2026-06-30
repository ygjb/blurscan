"""Tests for the report action and thumbnails (DESIGN.md §3.1)."""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from blurscan.actions.report import write_csv, write_html, write_report
from blurscan.models import BLURRY, SHARP, ImageResult
from blurscan.thumbs import thumbnail_bytes, thumbnail_data_uri


def _img(path: Path, size: int = 64) -> Path:
    arr: NDArray[np.uint8] = np.random.default_rng(0).integers(
        0, 256, size=(size, size, 3), dtype=np.uint8
    )
    Image.fromarray(arr, "RGB").save(path)
    return path


def _result(path: Path, score: float, cls: str) -> ImageResult:
    return ImageResult(
        path=path,
        width=64,
        height=64,
        score_max_tile=score,
        score_global=score / 2,
        fft_ratio=0.4,
        classification=cls,
    )


def test_thumbnail_bytes_and_data_uri(tmp_path: Path) -> None:
    p = _img(tmp_path / "a.png", size=512)
    data = thumbnail_bytes(p, max_edge=128)
    assert data[:3] == b"\xff\xd8\xff"  # JPEG magic
    img = Image.open(__import__("io").BytesIO(data))
    assert max(img.size) <= 128
    assert thumbnail_data_uri(p).startswith("data:image/jpeg;base64,")


def test_write_csv_roundtrip(tmp_path: Path) -> None:
    results = [
        _result(tmp_path / "sharp.png", 500.0, SHARP),
        _result(tmp_path / "blur.png", 10.0, BLURRY),
    ]
    out = write_csv(results, tmp_path / "r.csv")
    rows = list(csv.DictReader(out.open()))
    assert {r["classification"] for r in rows} == {SHARP, BLURRY}
    assert rows[0]["method"] == "laplacian"


def test_write_html_standalone_with_thumbnails(tmp_path: Path) -> None:
    p = _img(tmp_path / "pic.png")
    out = write_html([_result(p, 12.0, BLURRY)], tmp_path / "r.html", thumbnails=True)
    text = out.read_text()
    assert "<!DOCTYPE html>" in text
    assert "data:image/jpeg;base64," in text  # self-contained
    assert "blurriest-first" in text


def test_write_html_handles_error_results(tmp_path: Path) -> None:
    bad = ImageResult.from_error(tmp_path / "gone.png", "decode failed")
    out = write_html([bad], tmp_path / "e.html", thumbnails=True)
    assert "decode failed" in out.read_text()


def test_write_report_emits_both(tmp_path: Path) -> None:
    csv_path, html_path = write_report(
        [_result(_img(tmp_path / "x.png"), 12.0, BLURRY)],
        tmp_path / "report",
        thumbnails=False,
    )
    assert csv_path.exists() and csv_path.suffix == ".csv"
    assert html_path.exists() and html_path.suffix == ".html"
