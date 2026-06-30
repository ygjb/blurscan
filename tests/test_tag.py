"""Tests for the exiftool tagging action (DESIGN.md §5).

Command construction and guards run everywhere (no exiftool needed). A real
round-trip runs only where exiftool is installed (CI), and skips otherwise.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest
from numpy.typing import NDArray
from PIL import Image

from blurscan.actions import tag as tagmod
from blurscan.actions.tag import (
    ExiftoolCommand,
    ExiftoolNotFound,
    build_commands,
    ensure_exiftool,
    tag,
)
from blurscan.models import BLURRY, BORDERLINE, SHARP, ImageResult

HAVE_EXIFTOOL = shutil.which("exiftool") is not None


def _result(path: Path, cls: str, error: str | None = None) -> ImageResult:
    return ImageResult(
        path=path,
        width=1,
        height=1,
        score_max_tile=1.0,
        score_global=1.0,
        fft_ratio=0.1,
        classification=cls,
        error=error,
    )


def test_build_commands_selects_and_tags_blurry() -> None:
    results = [
        _result(Path("a.jpg"), BLURRY),
        _result(Path("b.jpg"), SHARP),
        _result(Path("c.jpg"), BORDERLINE),
        _result(Path("d.jpg"), BLURRY, error="boom"),
    ]
    cmds = build_commands(results)
    targets = [t for c in cmds for t in c.targets]
    assert targets == [Path("a.jpg")]  # sharp/borderline/errored excluded
    joined = " ".join(cmds[0].args)
    assert "-XMP:Subject+=blurscan:blurry" in joined
    assert "-XMP:Rating=1" in joined
    assert "-overwrite_original" in joined  # non-RAW tagged in place


def test_include_borderline() -> None:
    results = [_result(Path("a.jpg"), BLURRY), _result(Path("c.jpg"), BORDERLINE)]
    targets = {t for c in build_commands(results, include_borderline=True) for t in c.targets}
    assert targets == {Path("a.jpg"), Path("c.jpg")}


def test_raw_defaults_to_sidecar() -> None:
    cmds = build_commands([_result(Path("shot.nef"), BLURRY)])
    assert cmds[0].args[:2] == ["-srcfile", "%d%f.xmp"]  # sidecar, original untouched
    assert "-overwrite_original" not in cmds[0].args


def test_raw_inplace_option() -> None:
    cmds = build_commands([_result(Path("shot.nef"), BLURRY)], raw_inplace=True)
    assert "-overwrite_original" in cmds[0].args
    assert "-srcfile" not in cmds[0].args


def test_chunks_large_batches() -> None:
    results = [_result(Path(f"{i}.jpg"), BLURRY) for i in range(tagmod.CHUNK_SIZE + 5)]
    cmds = build_commands(results)
    assert len(cmds) == 2
    assert len(cmds[0].targets) == tagmod.CHUNK_SIZE
    assert len(cmds[1].targets) == 5


def test_rejects_unsafe_paths() -> None:
    with pytest.raises(ValueError, match="unsafe"):
        build_commands([_result(Path("evil\nname.jpg"), BLURRY)])


def test_argv_is_a_list_no_shell() -> None:
    cmd = ExiftoolCommand(args=["-overwrite_original"], targets=[Path("a b.jpg")])
    argv = cmd.argv("/usr/bin/exiftool")
    assert argv[0] == "/usr/bin/exiftool"
    assert argv[-1] == "a b.jpg"  # spaces preserved as one argv element, not split


def test_dry_run_does_not_execute(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(*a: object, **k: object) -> None:
        raise AssertionError("subprocess must not run during dry-run")

    monkeypatch.setattr(subprocess, "run", _boom)
    cmds = tag([_result(Path("a.jpg"), BLURRY)], dry_run=True)
    assert cmds  # plan returned, nothing executed


def test_ensure_exiftool_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _: None)
    with pytest.raises(ExiftoolNotFound):
        ensure_exiftool()


@pytest.mark.skipif(not HAVE_EXIFTOOL, reason="exiftool not installed")
def test_real_jpeg_roundtrip(tmp_path: Path) -> None:
    arr: NDArray[np.uint8] = np.zeros((8, 8, 3), dtype=np.uint8)
    p = tmp_path / "blur.jpg"
    Image.fromarray(arr, "RGB").save(p)
    tag([_result(p, BLURRY)])
    out = subprocess.run(
        ["exiftool", "-XMP:Subject", "-s3", str(p)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "blurscan:blurry" in out.stdout
