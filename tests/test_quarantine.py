"""Tests for the quarantine action (DESIGN.md §6)."""

from __future__ import annotations

from pathlib import Path

from blurscan.actions.quarantine import flagged_results, quarantine
from blurscan.models import BLURRY, BORDERLINE, SHARP, ImageResult


def _result(path: Path, cls: str, error: str | None = None) -> ImageResult:
    return ImageResult(
        path=path,
        width=10,
        height=10,
        score_max_tile=1.0,
        score_global=1.0,
        fft_ratio=0.1,
        classification=cls,
        error=error,
    )


def _touch(p: Path, data: bytes = b"x") -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return p


def test_flagged_selection(tmp_path: Path) -> None:
    results = [
        _result(tmp_path / "a.jpg", BLURRY),
        _result(tmp_path / "b.jpg", BORDERLINE),
        _result(tmp_path / "c.jpg", SHARP),
        _result(tmp_path / "d.jpg", BLURRY, error="decode failed"),
    ]
    assert {r.path.name for r in flagged_results(results)} == {"a.jpg"}
    assert {r.path.name for r in flagged_results(results, include_borderline=True)} == {
        "a.jpg",
        "b.jpg",
    }


def test_copy_preserves_originals(tmp_path: Path) -> None:
    src = _touch(tmp_path / "blur.jpg")
    dest = tmp_path / "quar"
    actions = quarantine([_result(src, BLURRY)], dest)
    assert src.exists()  # copy keeps original
    assert (dest / "blur.jpg").exists()
    assert actions[0].dst == dest / "blur.jpg"


def test_filter_results_false_honors_explicit_selection(tmp_path: Path) -> None:
    # The review UI stages images explicitly; filter_results=False must act on
    # exactly what it is given, including borderline/sharp/errored items that the
    # default classification filter would drop.
    border = _touch(tmp_path / "border.jpg")
    sharp = _touch(tmp_path / "sharp.jpg")
    dest = tmp_path / "quar"
    given = [_result(border, BORDERLINE), _result(sharp, SHARP)]

    assert flagged_results(given) == []  # default filter would quarantine nothing
    actions = quarantine(given, dest, filter_results=False)
    assert {a.dst.name for a in actions} == {"border.jpg", "sharp.jpg"}
    assert (dest / "border.jpg").exists() and (dest / "sharp.jpg").exists()


def test_move_removes_originals(tmp_path: Path) -> None:
    src = _touch(tmp_path / "blur.jpg")
    dest = tmp_path / "quar"
    quarantine([_result(src, BLURRY)], dest, move=True)
    assert not src.exists()
    assert (dest / "blur.jpg").exists()


def test_dry_run_changes_nothing(tmp_path: Path) -> None:
    src = _touch(tmp_path / "blur.jpg")
    dest = tmp_path / "quar"
    actions = quarantine([_result(src, BLURRY)], dest, move=True, dry_run=True)
    assert src.exists()  # untouched
    assert not dest.exists()  # not even created
    assert actions[0].src == src and actions[0].dst == dest / "blur.jpg"


def test_collision_safe_names(tmp_path: Path) -> None:
    a = _touch(tmp_path / "a" / "img.jpg")
    b = _touch(tmp_path / "b" / "img.jpg")  # same basename, different dir
    dest = tmp_path / "quar"
    actions = quarantine([_result(a, BLURRY), _result(b, BLURRY)], dest)
    names = sorted(p.name for p in dest.iterdir())
    assert names == ["img.jpg", "img_1.jpg"]
    assert len({a.dst for a in actions}) == 2  # no two map to the same target


def test_dry_run_collision_planning(tmp_path: Path) -> None:
    a = _touch(tmp_path / "a" / "img.jpg")
    b = _touch(tmp_path / "b" / "img.jpg")
    dest = tmp_path / "quar"
    actions = quarantine([_result(a, BLURRY), _result(b, BLURRY)], dest, dry_run=True)
    assert {act.dst.name for act in actions} == {"img.jpg", "img_1.jpg"}
