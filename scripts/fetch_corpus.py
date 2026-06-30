#!/usr/bin/env python3
"""Reconstruct the test corpora from committed manifests into a local cache.

The image files themselves are **not** stored in git — only manifests under
``test_samples/<corpus>/manifest.csv``. This script reads those manifests and
materializes the images into a gitignored cache so the local test suite can run.
CI does not run this (and the corpus-backed tests skip when the cache is absent).

Cache location: ``test_samples/_cache/`` by default, or ``$BLURSCAN_CORPUS_CACHE``.

Manifest schema (CSV, one row per file):
    kind      "download" | "transcode-heic"
    corpus    web_corpus | raw_corpus | heic_corpus
    label     blurry | not_blurry | raw   (sub-dir; "" for flat)
    filename  destination file name
    url       source URL (the image to download; for transcode, the source JPEG)
    sha256    checksum of the *downloaded source* (verifies the download)
    bytes,lap_var,fft_ratio,width,height,license,license_url,creator,landing_url,term,title,note

For ``download`` rows the cached file is the downloaded bytes (sha256 verified).
For ``transcode-heic`` rows the source JPEG is downloaded + verified, then
transcoded to HEIC (HEIC bytes are libheif-version dependent, so the cached
target is validated by decoding rather than by checksum).

Usage:
    python scripts/fetch_corpus.py                 # all corpora
    python scripts/fetch_corpus.py raw_corpus      # one corpus
    python scripts/fetch_corpus.py --force         # ignore existing cache
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import os
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen

REPO = Path(__file__).resolve().parent.parent
SAMPLES = REPO / "test_samples"
CORPORA = ("web_corpus", "raw_corpus", "heic_corpus")
UA = "blurscan-corpus/0.1 (https://github.com/ygjb/blurscan; research test corpus)"


def cache_root() -> Path:
    env = os.environ.get("BLURSCAN_CORPUS_CACHE")
    return Path(env) if env else SAMPLES / "_cache"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _download(url: str, *, timeout: int = 120) -> bytes:
    from urllib.parse import quote

    safe = quote(url, safe=":/?=&%")
    req = Request(safe, headers={"User-Agent": UA})
    last: Exception | None = None
    for attempt in range(4):
        try:
            with urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except Exception as exc:  # noqa: BLE001 - retry transient network errors
            last = exc
            wait = 2**attempt
            print(f"    retry {attempt + 1}/4 in {wait}s ({exc})", file=sys.stderr)
            time.sleep(wait)
    raise RuntimeError(f"failed to download {url}: {last}")


def _dest(root: Path, row: dict[str, str]) -> Path:
    label = (row.get("label") or "").strip()
    sub = root / label if label and label != "raw" else root
    return sub / row["filename"]


def _ok_download(path: Path, sha: str) -> bool:
    return path.exists() and bool(sha) and _sha256(path.read_bytes()) == sha


def _ok_decode(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        from blurscan.loader import load_image

        load_image(path)
        return True
    except Exception:  # noqa: BLE001
        return False


def fetch_corpus(name: str, *, force: bool) -> tuple[int, int, int]:
    """Returns (fetched, skipped, failed)."""
    manifest = SAMPLES / name / "manifest.csv"
    if not manifest.exists():
        print(f"  no manifest at {manifest}, skipping {name}")
        return (0, 0, 0)
    dest_root = cache_root() / name
    rows = list(csv.DictReader(manifest.open(newline="")))
    fetched = skipped = failed = 0
    print(f"\n=== {name}: {len(rows)} files -> {dest_root} ===")
    for row in rows:
        target = _dest(dest_root, row)
        kind = (row.get("kind") or "download").strip()
        sha = (row.get("sha256") or "").strip()
        try:
            if kind == "transcode-heic":
                if not force and _ok_decode(target):
                    skipped += 1
                    continue
                src = _download(row["url"])
                if sha and _sha256(src) != sha:
                    raise RuntimeError("source sha256 mismatch")
                target.parent.mkdir(parents=True, exist_ok=True)
                _transcode_heic(src, target)
                if not _ok_decode(target):
                    raise RuntimeError("transcoded HEIC failed to decode")
            else:  # download
                if not force and _ok_download(target, sha):
                    skipped += 1
                    continue
                data = _download(row["url"])
                if sha and _sha256(data) != sha:
                    raise RuntimeError(f"sha256 mismatch ({_sha256(data)[:10]} != {sha[:10]})")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            fetched += 1
            print(f"  + {target.relative_to(cache_root())}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"  ! {row.get('filename')}: {exc}", file=sys.stderr)
            target.unlink(missing_ok=True)
    print(f"  {name}: {fetched} fetched, {skipped} cached, {failed} failed")
    return (fetched, skipped, failed)


def _transcode_heic(jpeg_bytes: bytes, target: Path) -> None:
    import io

    import pillow_heif
    from PIL import Image

    pillow_heif.register_heif_opener()
    img = Image.open(io.BytesIO(jpeg_bytes)).convert("RGB")
    img.save(target, format="HEIF", quality=90)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("corpora", nargs="*", choices=[*CORPORA, []], default=list(CORPORA))
    ap.add_argument("--force", action="store_true", help="re-fetch even if cached")
    args = ap.parse_args()
    names = args.corpora or list(CORPORA)

    print(f"corpus cache: {cache_root()}")
    total_failed = 0
    for name in names:
        _, _, failed = fetch_corpus(name, force=args.force)
        total_failed += failed
    if total_failed:
        print(f"\n{total_failed} file(s) failed — see errors above", file=sys.stderr)
        return 1
    print("\ncorpus ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
