#!/usr/bin/env python3
"""Apply human-review decisions to the staged corpus.

Reviewer workflow:
  1. Open test_samples/web_corpus/contact_sheets/*.jpg
  2. List the filename stems (the short id under each thumb) to DROP in
     test_samples/web_corpus/rejects.txt, one per line (# comments allowed).
  3. Run: python scripts/finalize_corpus.py
     -> deletes rejected images, rewrites manifest.csv / ATTRIBUTION.md, and
        reports final per-class counts.

Pass --promote to also copy the surviving images into the canonical
test_samples/<label>/ dirs alongside the existing hand-labeled set.
"""

from __future__ import annotations

import argparse
import csv
import shutil
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, default=Path("test_samples/web_corpus"))
    ap.add_argument("--promote", action="store_true", help="copy keepers into test_samples/<label>/")
    args = ap.parse_args()
    root: Path = args.root

    rejects: set[str] = set()
    rfile = root / "rejects.txt"
    if rfile.exists():
        for line in rfile.read_text().splitlines():
            line = line.split("#")[0].strip()
            if line:
                rejects.add(Path(line).stem)

    rows = list(csv.DictReader((root / "manifest.csv").open()))
    kept, dropped = [], 0
    for r in rows:
        if Path(r["filename"]).stem in rejects:
            (root / r["label"] / r["filename"]).unlink(missing_ok=True)
            dropped += 1
        else:
            kept.append(r)

    # rewrite manifest
    with (root / "manifest.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(kept)

    # rewrite attribution
    with (root / "ATTRIBUTION.md").open("w") as fh:
        fh.write("# Corpus attribution\n\nAll images via Openverse (https://openverse.org).\n\n")
        for r in kept:
            lic = f"CC {r['license'].upper()} {r['license_version']}".strip()
            fh.write(f"- `{r['label']}/{r['filename']}` by {r['creator'] or 'Unknown'} — {lic} — {r['landing_url']}\n")

    counts: dict[str, int] = {}
    for r in kept:
        counts[r["label"]] = counts.get(r["label"], 0) + 1
    print(f"dropped {dropped}, kept {len(kept)}")
    for label, n in sorted(counts.items()):
        print(f"  {label}: {n}")

    if args.promote:
        for r in kept:
            src = root / r["label"] / r["filename"]
            dst = Path("test_samples") / r["label"] / f"web_{r['filename']}"
            shutil.copy2(src, dst)
        print("promoted keepers into test_samples/<label>/ (prefixed web_)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
