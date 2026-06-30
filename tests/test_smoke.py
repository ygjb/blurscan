"""Smoke tests for the scaffolding: package imports and CLI entry point work."""

from __future__ import annotations

import blurscan
from blurscan.cli import build_parser, main


def test_version_exposed() -> None:
    assert isinstance(blurscan.__version__, str)


def test_parser_builds() -> None:
    assert build_parser().prog == "blurscan"


def test_main_no_args_prints_help() -> None:
    # No scan path -> prints help, exits 0.
    assert main([]) == 0


def test_main_with_bad_path() -> None:
    # A non-existent scan directory exits non-zero.
    assert main(["/some/path/that/does/not/exist"]) == 2
