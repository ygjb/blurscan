"""Report action: CSV + standalone HTML output.

See DESIGN.md §3.1 / §6. Writes a machine-readable CSV (every score, so thresholds
can be recalibrated) and a self-contained HTML report (thumbnails embedded as
data URIs) sorted blurriest-first. Never touches the scanned images.
"""

from __future__ import annotations

import csv
import html
from pathlib import Path

from blurscan.models import BLURRY, BORDERLINE, ImageResult
from blurscan.thumbs import thumbnail_data_uri

CSV_FIELDS = [
    "path",
    "classification",
    "method",
    "score_max_tile",
    "score_global",
    "fft_ratio",
    "width",
    "height",
    "error",
]

_BADGE_COLORS = {BLURRY: "#d93f0b", BORDERLINE: "#fbca04", "sharp": "#2da44e"}


def write_csv(results: list[ImageResult], out_path: Path) -> Path:
    """Write one CSV row per result. Returns the path written."""
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for r in results:
            writer.writerow(
                {
                    "path": str(r.path),
                    "classification": r.classification,
                    "method": r.method,
                    "score_max_tile": f"{r.score_max_tile:.3f}",
                    "score_global": f"{r.score_global:.3f}",
                    "fft_ratio": f"{r.fft_ratio:.4f}",
                    "width": r.width,
                    "height": r.height,
                    "error": r.error or "",
                }
            )
    return out_path


def _card(r: ImageResult, thumbnails: bool, thumb_size: int) -> str:
    color = _BADGE_COLORS.get(r.classification, "#57606a")
    name = html.escape(r.path.name)
    full = html.escape(str(r.path))
    if r.error:
        media = f'<div class="err">⚠ {html.escape(r.error)}</div>'
    elif thumbnails:
        try:
            media = f'<img src="{thumbnail_data_uri(r.path, thumb_size)}" alt="{name}">'
        except Exception as exc:  # noqa: BLE001 - report is best-effort on bad files
            media = f'<div class="err">⚠ {html.escape(str(exc))}</div>'
    else:
        media = '<div class="noimg"></div>'
    return (
        f'<figure class="card" title="{full}">{media}'
        f'<figcaption><span class="badge" style="background:{color}">'
        f"{html.escape(r.classification or '?')}</span> "
        f'<span class="score">{r.score_max_tile:.1f}</span>'
        f"<div class=\"name\">{name}</div></figcaption></figure>"
    )


def write_html(
    results: list[ImageResult],
    out_path: Path,
    thumbnails: bool = True,
    thumb_size: int = 200,
) -> Path:
    """Write a self-contained HTML report, blurriest-first. Returns the path."""
    ordered = sorted(results, key=lambda r: r.score_max_tile)
    counts = {c: sum(1 for r in results if r.classification == c) for c in _BADGE_COLORS}
    summary = " · ".join(f"{c}: {n}" for c, n in counts.items())
    cards = "\n".join(_card(r, thumbnails, thumb_size) for r in ordered)
    doc = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>blurscan report</title>
<style>
 body{{font:14px system-ui,sans-serif;margin:1.5rem;background:#f6f8fa;color:#1f2328}}
 h1{{font-size:1.3rem}} .summary{{color:#57606a;margin-bottom:1rem}}
 .grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:12px}}
 .card{{margin:0;background:#fff;border:1px solid #d0d7de;border-radius:8px;overflow:hidden}}
 .card img,.noimg,.err{{width:100%;height:160px;object-fit:cover;background:#eaeef2;display:block}}
 .err{{display:flex;align-items:center;justify-content:center;color:#d93f0b;padding:6px;text-align:center}}
 figcaption{{padding:6px 8px}} .badge{{color:#fff;border-radius:6px;padding:1px 6px;font-size:12px}}
 .score{{color:#57606a}} .name{{font-size:12px;color:#57606a;margin-top:2px;word-break:break-all}}
</style></head><body>
<h1>blurscan report</h1>
<div class="summary">{len(results)} images · {summary} · sorted blurriest-first</div>
<div class="grid">
{cards}
</div></body></html>
"""
    out_path.write_text(doc, encoding="utf-8")
    return out_path


def write_report(
    results: list[ImageResult], out: Path | str, thumbnails: bool = True
) -> tuple[Path, Path]:
    """Write both CSV and HTML next to ``out`` (its .csv/.html siblings)."""
    out = Path(out)
    csv_path = write_csv(results, out.with_suffix(".csv"))
    html_path = write_html(results, out.with_suffix(".html"), thumbnails=thumbnails)
    return csv_path, html_path
