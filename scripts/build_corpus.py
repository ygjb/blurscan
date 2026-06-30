#!/usr/bin/env python3
"""Build a labeled blurry / not-blurry image corpus from Openverse.

Openverse (https://api.openverse.org) aggregates Creative-Commons and
public-domain images from Flickr, Wikimedia Commons, museums, etc. It needs no
API key for anonymous (rate-limited) access and returns per-image license and
attribution metadata, which we record so the corpus stays license-compliant.

Pipeline per class (blurry / not_blurry):
  1. Query a set of search terms, paginating to collect candidate records.
  2. Download each candidate (deduped by Openverse id), validate it decodes and
     meets a minimum size.
  3. Score it with the project's own blur metrics (Laplacian variance + FFT
     high-frequency ratio) and bucket it as confident / review against the
     intended label.
  4. Stage files under test_samples/web_corpus/<label>/ and write a manifest CSV
     plus an ATTRIBUTION.md credits file.

The auto-screen is intentionally conservative; the human review afterward is the
final label authority (see --help and the README written alongside the corpus).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.request import Request, urlopen

import numpy as np

# Import the project's own metric primitives so the corpus is verified by the
# same logic the detector uses.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from blurscan.loader import ImageLoadError, load_image  # noqa: E402
from blurscan.metrics import (  # noqa: E402
    downscale,
    fft_high_freq_ratio,
    laplacian,
    to_grayscale,
)

OPENVERSE = "https://api.openverse.org/v1/images/"
UA = "blurscan-corpus/0.1 (https://github.com/; research test corpus)"
WORKING_SIZE = 1024
MIN_EDGE = 640  # reject thumbnails / tiny images

# Search terms per class. Blurry terms target whole-image softness; sharp terms
# are generic high-quality categories that are screened for actual sharpness.
TERMS = {
    "blurry": [
        "blurry photo",
        "out of focus",
        "motion blur",
        "camera shake",
        "blurred",
        "defocused",
        "blurry street",
        "shaky photo",
    ],
    "not_blurry": [
        "sharp landscape",
        "macro photography",
        "portrait",
        "street photography",
        "architecture",
        "wildlife",
        "cityscape",
        "still life",
    ],
}

# Thresholds calibrated against the existing hand-labeled test_samples set.
# Confident buckets require BOTH metrics to agree; everything else -> review.
SHARP_LAP, SHARP_FFT = 150.0, 0.45
BLUR_LAP, BLUR_FFT = 80.0, 0.42


@dataclass
class Candidate:
    ov_id: str
    title: str
    creator: str
    creator_url: str
    license: str
    license_version: str
    license_url: str
    landing_url: str
    source: str
    image_url: str
    term: str
    # filled in after download
    filename: str = ""
    lap_var: float = 0.0
    fft_ratio: float = 0.0
    bucket: str = ""
    width: int = 0
    height: int = 0


def http_json(url: str, params: dict) -> dict:
    from urllib.parse import urlencode

    full = f"{url}?{urlencode(params)}"
    req = Request(full, headers={"User-Agent": UA, "Accept": "application/json"})
    for attempt in range(5):
        try:
            with urlopen(req, timeout=30) as resp:
                import json

                return json.load(resp)
        except Exception as exc:  # noqa: BLE001
            wait = 2 ** attempt
            print(f"    api retry {attempt + 1} in {wait}s ({exc})", file=sys.stderr)
            time.sleep(wait)
    raise RuntimeError(f"failed to fetch {full}")


def search(term: str, want: int) -> list[Candidate]:
    """Collect up to ``want`` candidate records for a search term."""
    out: list[Candidate] = []
    page = 1
    while len(out) < want and page <= 20:
        data = http_json(
            OPENVERSE,
            {
                "q": term,
                "page": page,
                "page_size": 20,
                "license_type": "all",  # all open licenses; recorded per-image
                "mature": "false",
            },
        )
        results = data.get("results", [])
        if not results:
            break
        for r in results:
            img_url = r.get("url")
            if not img_url:
                continue
            out.append(
                Candidate(
                    ov_id=str(r.get("id", "")),
                    title=(r.get("title") or "").strip(),
                    creator=(r.get("creator") or "").strip(),
                    creator_url=(r.get("creator_url") or "").strip(),
                    license=(r.get("license") or "").strip(),
                    license_version=(r.get("license_version") or "").strip(),
                    license_url=(r.get("license_url") or "").strip(),
                    landing_url=(r.get("foreign_landing_url") or "").strip(),
                    source=(r.get("source") or "").strip(),
                    image_url=img_url,
                    term=term,
                )
            )
        page += 1
        time.sleep(0.5)  # politeness for anonymous rate limits
    return out


def download(c: Candidate, dest_dir: Path) -> bool:
    """Download, validate, and score a candidate. Returns True if kept."""
    ext = ".jpg"
    for cand in (".jpg", ".jpeg", ".png", ".webp"):
        if c.image_url.lower().split("?")[0].endswith(cand):
            ext = cand
            break
    name = f"{hashlib.sha1(c.ov_id.encode()).hexdigest()[:16]}{ext}"
    path = dest_dir / name
    req = Request(c.image_url, headers={"User-Agent": UA})
    try:
        with urlopen(req, timeout=60) as resp:
            data = resp.read()
        if len(data) < 5000:  # too small to be useful
            return False
        path.write_bytes(data)
        rgb = load_image(path)
    except (ImageLoadError, Exception):  # noqa: BLE001
        if path.exists():
            path.unlink()
        return False

    h, w = rgb.shape[:2]
    if min(h, w) < MIN_EDGE:
        path.unlink()
        return False

    g = to_grayscale(downscale(rgb, WORKING_SIZE))
    c.lap_var = float(laplacian(g).var())
    c.fft_ratio = float(fft_high_freq_ratio(g))
    c.filename = name
    c.width, c.height = w, h
    return True


def bucket_for(label: str, c: Candidate) -> str:
    """Confidence bucket for a candidate given its intended ``label``."""
    sharp = c.lap_var >= SHARP_LAP and c.fft_ratio >= SHARP_FFT
    blur = c.lap_var <= BLUR_LAP and c.fft_ratio <= BLUR_FFT
    if label == "not_blurry":
        if sharp:
            return "confident"
        if blur:
            return "mislabeled"  # looks blurry, drop from sharp set
        return "review"
    else:  # blurry
        if blur:
            return "confident"
        if sharp:
            return "mislabeled"
        return "review"


def build(label: str, target: int, root: Path) -> list[Candidate]:
    dest = root / label
    dest.mkdir(parents=True, exist_ok=True)
    seen: set[str] = set()
    kept: list[Candidate] = []
    per_term = max(20, (target * 3) // len(TERMS[label]))
    print(f"\n=== {label}: targeting {target}, fetching ~{per_term}/term ===")
    for term in TERMS[label]:
        cands = search(term, per_term)
        print(f"  term '{term}': {len(cands)} records")
        for c in cands:
            if c.ov_id in seen:
                continue
            seen.add(c.ov_id)
            if download(c, dest):
                c.bucket = bucket_for(label, c)
                kept.append(c)
                if c.bucket == "mislabeled":
                    (dest / c.filename).unlink(missing_ok=True)
            # stop once we have plenty of confident+review keepers
            usable = [k for k in kept if k.bucket in ("confident", "review")]
            if len(usable) >= target:
                break
        usable = [k for k in kept if k.bucket in ("confident", "review")]
        if len(usable) >= target:
            break
    return [k for k in kept if k.bucket != "mislabeled"]


def write_manifest(rows: list[Candidate], root: Path) -> None:
    manifest = root / "manifest.csv"
    with manifest.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(
            [
                "label",
                "bucket",
                "filename",
                "lap_var",
                "fft_ratio",
                "width",
                "height",
                "license",
                "license_version",
                "creator",
                "source",
                "landing_url",
                "license_url",
                "image_url",
                "term",
            ]
        )
        for c in rows:
            w.writerow(
                [
                    c._label,
                    c.bucket,
                    c.filename,
                    f"{c.lap_var:.1f}",
                    f"{c.fft_ratio:.4f}",
                    c.width,
                    c.height,
                    c.license,
                    c.license_version,
                    c.creator,
                    c.source,
                    c.landing_url,
                    c.license_url,
                    c.image_url,
                    c.term,
                ]
            )
    print(f"\nwrote {manifest}")

    credits = root / "ATTRIBUTION.md"
    with credits.open("w") as fh:
        fh.write("# Corpus attribution\n\n")
        fh.write(
            "All images sourced via Openverse (https://openverse.org). "
            "Each is credited below with its Creative-Commons / public-domain "
            "license. Reuse must follow the named license.\n\n"
        )
        for c in rows:
            who = c.creator or "Unknown"
            lic = f"CC {c.license.upper()} {c.license_version}".strip()
            fh.write(
                f"- `{c._label}/{c.filename}` — \"{c.title or 'Untitled'}\" by "
                f"{who} — {lic} — {c.landing_url}\n"
            )
    print(f"wrote {credits}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--target", type=int, default=100, help="usable images per class")
    ap.add_argument(
        "--out",
        type=Path,
        default=Path("test_samples/web_corpus"),
        help="staging directory",
    )
    args = ap.parse_args()

    all_rows: list[Candidate] = []
    for label in ("blurry", "not_blurry"):
        rows = build(label, args.target, args.out)
        for c in rows:
            c._label = label  # type: ignore[attr-defined]
        all_rows.extend(rows)
        conf = sum(1 for c in rows if c.bucket == "confident")
        rev = sum(1 for c in rows if c.bucket == "review")
        print(f"  -> {label}: {conf} confident, {rev} review")

    write_manifest(all_rows, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
