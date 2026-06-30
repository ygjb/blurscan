"""Integrity checks for the committed corpus manifests (issue #49).

The corpus images are not committed — only ``test_samples/<corpus>/manifest.csv``,
from which ``scripts/fetch_corpus.py`` reconstructs a local cache. These tests run
**without network or cache** so a fresh clone / CI still validates the manifests.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

SAMPLES = Path(__file__).resolve().parent.parent / "test_samples"
CORPORA = ("web_corpus", "raw_corpus", "heic_corpus")
REQUIRED = {"kind", "label", "filename", "url", "sha256"}
VALID_KINDS = {"download", "transcode-heic"}


@pytest.mark.parametrize("corpus", CORPORA)
def test_manifest_present_and_well_formed(corpus: str) -> None:
    manifest = SAMPLES / corpus / "manifest.csv"
    assert manifest.exists(), f"missing {manifest}"
    rows = list(csv.DictReader(manifest.open(newline="")))
    assert rows, f"{corpus} manifest is empty"
    assert REQUIRED <= set(rows[0].keys()), f"{corpus} missing columns {REQUIRED - set(rows[0])}"

    names: set[str] = set()
    for r in rows:
        assert r["kind"] in VALID_KINDS, f"bad kind {r['kind']!r}"
        assert r["filename"], "empty filename"
        assert r["url"].startswith("http"), f"bad url {r['url']!r}"
        # download rows must carry a checksum so the fetch can verify integrity;
        # transcode rows checksum their *source*, which is also recorded here.
        assert len(r["sha256"]) == 64, f"{r['filename']} sha256 not a 64-hex digest"
        key = f"{r['label']}/{r['filename']}"
        assert key not in names, f"duplicate manifest entry {key}"
        names.add(key)


def test_attribution_files_present() -> None:
    for corpus in CORPORA:
        assert (SAMPLES / corpus / "ATTRIBUTION.md").exists(), f"{corpus} missing ATTRIBUTION.md"


def test_raw_formats_supported_by_loader() -> None:
    from blurscan.loader import RAW_EXTENSIONS

    rows = list(csv.DictReader((SAMPLES / "raw_corpus" / "manifest.csv").open(newline="")))
    for r in rows:
        ext = "." + r["filename"].rsplit(".", 1)[-1].lower()
        assert ext in RAW_EXTENSIONS, f"{r['filename']} ext not loader-supported"


def test_heic_rows_are_transcodes() -> None:
    rows = list(csv.DictReader((SAMPLES / "heic_corpus" / "manifest.csv").open(newline="")))
    assert rows
    for r in rows:
        assert r["kind"] == "transcode-heic"
        assert r["filename"].endswith(".heic")
        assert r["label"] in {"blurry", "not_blurry"}
