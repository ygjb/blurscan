#!/usr/bin/env python3
"""Render contact sheets from the corpus manifest for human review.

One sheet per (label, bucket). Each thumbnail is annotated with its filename
stem and metric scores so a reviewer can note rejects by filename.
"""

from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

THUMB = 256
PAD = 6
LABEL_H = 28
COLS = 8


def load_font() -> ImageFont.ImageFont:
    for p in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ):
        if Path(p).exists():
            return ImageFont.truetype(p, 13)
    return ImageFont.load_default()


def make_sheet(rows: list[dict], root: Path, out: Path, title: str) -> None:
    font = load_font()
    n = len(rows)
    cols = min(COLS, n) or 1
    import math

    rows_n = math.ceil(n / cols)
    cell_w = THUMB + PAD
    cell_h = THUMB + LABEL_H + PAD
    header = 36
    sheet = Image.new("RGB", (cols * cell_w + PAD, rows_n * cell_h + header + PAD), "white")
    draw = ImageDraw.Draw(sheet)
    draw.text((PAD, 10), title, fill="black", font=font)

    for i, r in enumerate(rows):
        cx = (i % cols) * cell_w + PAD
        cy = (i // cols) * cell_h + header
        img_path = root / r["label"] / r["filename"]
        try:
            im = Image.open(img_path).convert("RGB")
            im.thumbnail((THUMB, THUMB))
        except Exception:  # noqa: BLE001
            im = Image.new("RGB", (THUMB, THUMB), "gray")
        ox = cx + (THUMB - im.width) // 2
        oy = cy + (THUMB - im.height) // 2
        sheet.paste(im, (ox, oy))
        stem = Path(r["filename"]).stem[:10]
        cap = f"{stem} L{float(r['lap_var']):.0f} F{float(r['fft_ratio']):.2f}"
        draw.text((cx, cy + THUMB + 4), cap, fill="black", font=font)

    sheet.save(out, quality=85)
    print(f"wrote {out}  ({n} images)")


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("test_samples/web_corpus")
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    with (root / "manifest.csv").open() as fh:
        for r in csv.DictReader(fh):
            groups[(r["label"], r["bucket"])].append(r)

    sheets_dir = root / "contact_sheets"
    sheets_dir.mkdir(exist_ok=True)
    for (label, bucket), rows in sorted(groups.items()):
        rows.sort(key=lambda r: float(r["lap_var"]))
        make_sheet(
            rows,
            root,
            sheets_dir / f"{label}__{bucket}.jpg",
            f"{label} / {bucket}  (n={len(rows)}, sorted by Laplacian variance)",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
