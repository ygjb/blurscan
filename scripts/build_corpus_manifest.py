#!/usr/bin/env python3
"""Analyze sources and write the committed corpus *manifests* (issue #49).

This is the maintainer-run step that decides *what* the corpus contains and
records it as ``test_samples/<corpus>/manifest.csv`` (committed). The image bytes
are never committed — end users reconstruct them into a gitignored cache with
``scripts/fetch_corpus.py``. As a side effect this script also populates that
cache (it must download/transcode to score + checksum), so after running it the
local test suite is ready.

Corpora:
  web_corpus   Re-emit the existing Openverse JPEG manifest with a sha256 per
               file (computed from the currently-committed images) so it can be
               reconstructed by URL. Run this BEFORE removing the images.
  raw_corpus   Query raw.pixls.us, pick the smallest CC0 files across the RAW
               formats blurscan supports, download once to verify both decode
               paths + record pixls' sha256.
  heic_corpus  Pick a balanced subset of the web JPEGs; the manifest stores the
               source JPEG URL + sha256 and a transcode-heic directive.

Unified manifest schema is documented in scripts/fetch_corpus.py.

Usage:
    python scripts/build_corpus_manifest.py all
    python scripts/build_corpus_manifest.py raw --count 12 --raw-max-mb 5
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from blurscan.loader import RAW_EXTENSIONS, ImageLoadError, load_image  # noqa: E402
from blurscan.metrics import downscale, fft_high_freq_ratio, laplacian, to_grayscale  # noqa: E402

from fetch_corpus import cache_root  # noqa: E402  (sibling script)

REPO = Path(__file__).resolve().parent.parent
SAMPLES = REPO / "test_samples"
UA = "blurscan-corpus/0.1 (https://github.com/ygjb/blurscan; research test corpus)"
WORKING = 1024
PIXLS_INDEX = "https://raw.pixls.us/json/getrepository.php?set=all"

COLUMNS = [
    "kind", "label", "filename", "url", "sha256", "bytes",
    "lap_var", "fft_ratio", "width", "height",
    "license", "license_url", "creator", "landing_url", "term", "title", "note",
]


def _sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _get(url: str, *, timeout: int = 120) -> bytes:
    req = Request(quote(url, safe=":/?=&%"), headers={"User-Agent": UA})
    last: Exception | None = None
    for attempt in range(4):
        try:
            with urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(2**attempt)
    raise RuntimeError(f"GET {url} failed: {last}")


def _score(path: Path, raw_full: bool = False) -> tuple[float, float, int, int]:
    rgb = load_image(path, raw_full=raw_full)
    h, w = rgb.shape[:2]
    g = to_grayscale(downscale(rgb, WORKING))
    return float(laplacian(g).var()), float(fft_high_freq_ratio(g)), w, h


def _write(name: str, rows: list[dict], blurb: str) -> None:
    out_dir = SAMPLES / name
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "manifest.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in COLUMNS})
    with (out_dir / "ATTRIBUTION.md").open("w") as fh:
        fh.write(f"# {name} attribution\n\n{blurb}\n\n")
        for r in rows:
            sub = f"{r['label']}/{r['filename']}" if r.get("label") not in ("", "raw") else r["filename"]
            who = r.get("creator") or "Unknown"
            extra = f" — {r['note']}" if r.get("note") else ""
            fh.write(f"- `{sub}` — \"{r.get('title') or 'Untitled'}\" by {who} — "
                     f"{r.get('license')} — {r.get('landing_url')}{extra}\n")
    print(f"wrote {out_dir/'manifest.csv'} ({len(rows)} rows) + ATTRIBUTION.md")


# ----------------------------------------------------------------------- web


def build_web() -> list[dict]:
    """Re-emit web_corpus manifest with sha256 from the committed images."""
    old = SAMPLES / "web_corpus" / "manifest.csv"
    if not old.exists():
        raise SystemExit("no web_corpus/manifest.csv to migrate")
    rows: list[dict] = []
    for r in csv.DictReader(old.open(newline="")):
        if "sha256" in r and r.get("kind"):  # already migrated
            rows.append(r)
            continue
        img = SAMPLES / "web_corpus" / r["label"] / r["filename"]
        if not img.exists():
            print(f"  WARN missing committed image {img}; cannot checksum", file=sys.stderr)
            continue
        data = img.read_bytes()
        lic = f"CC {r['license'].upper()} {r['license_version']}".strip()
        rows.append({
            "kind": "download", "label": r["label"], "filename": r["filename"],
            "url": r["image_url"], "sha256": _sha256(data), "bytes": len(data),
            "lap_var": r["lap_var"], "fft_ratio": r["fft_ratio"],
            "width": r["width"], "height": r["height"],
            "license": lic, "license_url": r["license_url"], "creator": r["creator"],
            "landing_url": r["landing_url"], "term": r["term"], "title": "", "note": "",
        })
    _write("web_corpus", rows,
           "Openverse-sourced Creative-Commons / public-domain JPEGs. Images are not "
           "committed; reconstruct via `scripts/fetch_corpus.py`. Reuse must follow each "
           "named license.")
    return rows


# ----------------------------------------------------------------------- raw


def _parse_pixls(blob: bytes) -> list[dict]:
    out = []
    for r in json.loads(blob)["data"]:
        make, model, variant, lic_html, file_html = r[0], r[1], r[2], r[5], r[7]
        url = re.search(r"href='([^']+)'", file_html)
        size = re.search(r"\(([\d.]+)(KB|MB|GB)\)", file_html)
        sha = re.search(r">([0-9a-f]{64})<", file_html)
        lic = re.search(r"title='([^']+)'", lic_html)
        lic_href = re.search(r"href='([^']+)'", lic_html)
        if not (url and size):
            continue
        v, unit = float(size.group(1)), size.group(2)
        out.append({
            "make": make, "model": model, "variant": variant,
            "url": url.group(1), "ext": url.group(1).rsplit(".", 1)[-1].lower(),
            "bytes": int(v * {"KB": 1024, "MB": 1024**2, "GB": 1024**3}[unit]),
            "sha256": sha.group(1) if sha else "",
            "license": lic.group(1) if lic else "",
            "license_url": lic_href.group(1) if lic_href else "",
        })
    return out


def build_raw(count: int, max_mb: float) -> list[dict]:
    print(f"fetching pixls index {PIXLS_INDEX}")
    items = _parse_pixls(_get(PIXLS_INDEX, timeout=30))
    cap = int(max_mb * 1024 * 1024)
    pool = [i for i in items if f".{i['ext']}" in RAW_EXTENSIONS
            and "Public Domain" in i["license"] and i["bytes"] <= cap]
    by_ext: dict[str, list[dict]] = {}
    for it in sorted(pool, key=lambda i: i["bytes"]):
        by_ext.setdefault(it["ext"], []).append(it)
    order = sorted(by_ext, key=lambda e: by_ext[e][0]["bytes"])
    print(f"  pool {len(pool)} CC0/supported/<= {max_mb}MB; formats {order}")

    cache = cache_root() / "raw_corpus"
    cache.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    seen: set[str] = set()
    i = 0
    while len(rows) < count and any(by_ext.values()) and i < len(order) * 50:
        ext = order[i % len(order)]
        i += 1
        if not by_ext[ext]:
            continue
        it = by_ext[ext].pop(0)
        slug = re.sub(r"[^A-Za-z0-9]+", "-", f"{it['make']}_{it['model']}_{it['variant']}").strip("-")
        name = f"{slug}.{it['ext']}"
        while name in seen:
            name = f"{slug}-{len(seen)}.{it['ext']}"
        out = cache / name
        try:
            data = _get(it["url"])
            if it["sha256"] and _sha256(data) != it["sha256"]:
                raise RuntimeError("pixls sha256 mismatch")
            out.write_bytes(data)
            lap, fft, w, h = _score(out)        # preview path
            _score(out, raw_full=True)          # gate: full demosaic must work too (§6)
        except (RuntimeError, ImageLoadError, OSError, ValueError) as exc:
            print(f"  skip {it['make']} {it['model']} .{it['ext']}: {exc}", file=sys.stderr)
            out.unlink(missing_ok=True)
            continue
        seen.add(name)
        rows.append({
            "kind": "download", "label": "raw", "filename": name, "url": it["url"],
            "sha256": it["sha256"], "bytes": it["bytes"],
            "lap_var": f"{lap:.1f}", "fft_ratio": f"{fft:.4f}", "width": w, "height": h,
            "license": "CC0 1.0",
            "license_url": it["license_url"] or "https://creativecommons.org/publicdomain/zero/1.0/",
            "creator": "",
            "landing_url": f"https://raw.pixls.us/data/{quote(it['make'])}/{quote(it['model'])}/",
            "term": f"{it['make']} {it['model']} {it['variant']}".strip(),
            "title": f"{it['make']} {it['model']} ({it['variant']})".strip(), "note": "",
        })
        print(f"  + {name} ({it['bytes']//1024}KB, {w}x{h}, lap={lap:.0f})")
    _write("raw_corpus", rows,
           "Camera RAW from raw.pixls.us, redistributed under CC0 1.0 (public domain). "
           "Smallest files across blurscan's supported RAW formats. Not committed; "
           "reconstruct via `scripts/fetch_corpus.py`.")
    return rows


# ---------------------------------------------------------------------- heic


def build_heic(count: int, web_rows: list[dict] | None) -> list[dict]:
    """Pick a balanced subset of web JPEGs; manifest = download-source + transcode."""
    import pillow_heif
    from PIL import Image

    pillow_heif.register_heif_opener()
    if web_rows is None:
        web_rows = list(csv.DictReader((SAMPLES / "web_corpus" / "manifest.csv").open(newline="")))
    cache = cache_root() / "heic_corpus"
    per = max(1, count // 2)
    rows: list[dict] = []
    for label in ("blurry", "not_blurry"):
        srcs = sorted((r for r in web_rows if r["label"] == label),
                      key=lambda r: (-int(r.get("width") or 0), r["filename"]))[:per]
        (cache / label).mkdir(parents=True, exist_ok=True)
        for r in srcs:
            sha = r.get("sha256", "")
            try:
                jpeg = _get(r["url"])
                if sha and _sha256(jpeg) != sha:
                    raise RuntimeError("source sha256 mismatch")
                name = Path(r["filename"]).with_suffix(".heic").name
                out = cache / label / name
                Image.open(io.BytesIO(jpeg)).convert("RGB").save(out, format="HEIF", quality=90)
                lap, fft, w, h = _score(out)
            except (RuntimeError, ImageLoadError, OSError, ValueError) as exc:
                print(f"  skip {r['filename']}: {exc}", file=sys.stderr)
                continue
            rows.append({
                "kind": "transcode-heic", "label": label, "filename": name, "url": r["url"],
                "sha256": sha, "bytes": "", "lap_var": f"{lap:.1f}", "fft_ratio": f"{fft:.4f}",
                "width": w, "height": h, "license": r.get("license", ""),
                "license_url": r.get("license_url", ""), "creator": r.get("creator", ""),
                "landing_url": r.get("landing_url", ""), "term": r.get("term", ""),
                "title": r.get("title", ""),
                "note": f"transcoded to HEIC from web_corpus source {r['filename']}",
            })
            print(f"  + {label}/{name} ({w}x{h}, lap={lap:.0f})")
    _write("heic_corpus", rows,
           "HEIC transcoded from the Creative-Commons web_corpus JPEGs (format change is "
           "not a CC adaptation, so source licenses carry over). The fetch script downloads "
           "each source JPEG and transcodes it locally; HEIC bytes are not committed.")
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("which", nargs="?", choices=("web", "raw", "heic", "all"), default="all")
    ap.add_argument("--count", type=int, default=12, help="files per format")
    ap.add_argument("--raw-max-mb", type=float, default=5.0)
    args = ap.parse_args()

    web_rows: list[dict] | None = None
    if args.which in ("web", "all"):
        web_rows = build_web()
    if args.which in ("raw", "all"):
        build_raw(args.count, args.raw_max_mb)
    if args.which in ("heic", "all"):
        build_heic(args.count, web_rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
